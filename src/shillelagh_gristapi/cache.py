import os
import json
import time
import logging
from typing import Tuple, Any, Optional
from collections import OrderedDict
import threading
import sqlite3
from json import JSONDecodeError

logger = logging.getLogger(__name__)


def _key_to_text(key: Tuple[str, Tuple[Any, ...]]) -> str:
    """Stable, portable representation for DB primary key."""
    name, parts = key
    return json.dumps([name, parts], ensure_ascii=False, sort_keys=False)


# -----------------
# In-memory cache
# -----------------


class MemoryCache:
    """In-process TTL + LRU cache."""

    def __init__(self, maxsize: int):
        self._data: "OrderedDict[Tuple[str, Tuple[Any, ...]], Tuple[float, Any]]" = (
            OrderedDict()
        )
        self._maxsize = maxsize
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
            self._hits = 0
            self._misses = 0

    def get(self, key: Tuple[str, Tuple[Any, ...]]) -> Optional[Any]:
        now = time.time()
        with self._lock:
            item = self._data.get(key)
            if not item:
                self._misses += 1
                return None
            expires_at, value = item
            if expires_at < now:
                self._data.pop(key, None)
                self._misses += 1
                return None
            self._data.move_to_end(key, last=True)
            self._hits += 1
            return value

    def set(self, key: Tuple[str, Tuple[Any, ...]], value: Any, ttl: int) -> None:
        if ttl <= 0:
            return
        expires_at = time.time() + ttl
        try:
            # probe JSON serializability early for parity with SQLite backend
            json.dumps(value)
        except TypeError:
            logger.debug(
                "MemoryCache: value for key %s not JSON-serializable; skipping cache",
                key,
            )
            return

        with self._lock:
            self._data[key] = (expires_at, value)
            self._data.move_to_end(key, last=True)
            while len(self._data) > self._maxsize:
                self._data.popitem(last=False)

    def stats(self) -> dict:
        with self._lock:
            return {
                "backend": "memory",
                "size": len(self._data),
                "hits": self._hits,
                "misses": self._misses,
                "maxsize": self._maxsize,
            }


# -----------------
# SQLite cache
# -----------------


class SQLiteCache:
    """SQLite-backed TTL + LRU cache. Values stored as JSON text."""

    def __init__(self, path: str, maxsize: int):
        self._path = os.path.expanduser(path)
        parent = os.path.dirname(self._path) or "."
        os.makedirs(parent, exist_ok=True)
        self._maxsize = maxsize
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

        try:
            self._conn = sqlite3.connect(
                self._path, timeout=30, isolation_level=None
            )  # autocommit
            self._conn.execute("PRAGMA journal_mode=WAL;")
            self._conn.execute("PRAGMA synchronous=NORMAL;")
            self._init_schema()
            logger.debug(
                "SQLiteCache ready at %s (maxsize=%d)", self._path, self._maxsize
            )
        except sqlite3.Error as e:
            logger.error("SQLiteCache init failed at %s: %s", self._path, e)
            raise

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            except Exception:
                pass

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    # --- internal exec with retry/backoff ---

    def _exec(
        self,
        sql: str,
        params: tuple = (),
        fetchone=False,
        fetchall=False,
        retries: int = 4,
    ):
        delay = 0.05
        for attempt in range(retries + 1):
            try:
                cur = self._conn.execute(sql, params)
                if fetchone:
                    return cur.fetchone()
                if fetchall:
                    return cur.fetchall()
                return None
            except sqlite3.OperationalError as e:
                msg = str(e).lower()
                if "locked" in msg or "busy" in msg:
                    if attempt < retries:
                        time.sleep(delay)
                        delay *= 2
                        continue
                logger.error(
                    "SQLite operational error on '%s': %s", sql.strip().split()[0], e
                )
                raise
            except sqlite3.Error as e:
                logger.error("SQLite error on '%s': %s", sql.strip().split()[0], e)
                raise

    def _init_schema(self) -> None:
        self._exec(
            """
            CREATE TABLE IF NOT EXISTS cache (
                key_text    TEXT PRIMARY KEY,
                expires_at  REAL NOT NULL,
                last_access REAL NOT NULL,
                value_json  TEXT NOT NULL
            )
            """
        )
        # cleanup expired
        now = time.time()
        self._exec("DELETE FROM cache WHERE expires_at < ?", (now,))
        self._prune_if_needed()

    def clear(self) -> None:
        with self._lock:
            self._exec("DELETE FROM cache")

    def get(self, key: Tuple[str, Tuple[Any, ...]]) -> Optional[Any]:
        key_text = _key_to_text(key)
        now = time.time()
        with self._lock:
            row = self._exec(
                "SELECT expires_at, value_json FROM cache WHERE key_text = ?",
                (key_text,),
                fetchone=True,
            )
            if not row:
                self._misses += 1
                return None
            expires_at, value_json = row
            if expires_at < now:
                self._exec("DELETE FROM cache WHERE key_text = ?", (key_text,))
                self._misses += 1
                return None
            # LRU touch
            self._exec(
                "UPDATE cache SET last_access = ? WHERE key_text = ?", (now, key_text)
            )
            try:
                value = json.loads(value_json)
            except JSONDecodeError:
                # Corrupt row -> treat as miss and delete
                logger.warning(
                    "SQLiteCache: corrupted JSON for key %s; deleting row", key_text
                )
                self._exec("DELETE FROM cache WHERE key_text = ?", (key_text,))
                self._misses += 1
                return None
            self._hits += 1
            return value

    def set(self, key: Tuple[str, Tuple[Any, ...]], value: Any, ttl: int) -> None:
        if ttl <= 0:
            return
        key_text = _key_to_text(key)
        now = time.time()
        expires_at = now + ttl
        try:
            value_json = json.dumps(value, ensure_ascii=False)
        except TypeError:
            logger.debug(
                "SQLiteCache: value for key %s not JSON-serializable; skipping cache",
                key,
            )
            return

        with self._lock:
            self._exec(
                """
                INSERT INTO cache (key_text, expires_at, last_access, value_json)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(key_text) DO UPDATE SET
                    expires_at=excluded.expires_at,
                    last_access=excluded.last_access,
                    value_json=excluded.value_json
                """,
                (key_text, expires_at, now, value_json),
            )
            self._prune_if_needed()

    def _prune_if_needed(self) -> None:
        # enforce maxsize via LRU (oldest last_access evicted first)
        count_row = self._exec("SELECT COUNT(*) FROM cache", fetchone=True)
        count = int(count_row[0]) if count_row else 0
        if count <= self._maxsize:
            return
        to_delete = count - self._maxsize
        self._exec(
            """
            DELETE FROM cache
            WHERE key_text IN (
                SELECT key_text FROM cache
                ORDER BY last_access ASC
                LIMIT ?
            )
            """,
            (to_delete,),
        )

    def stats(self) -> dict:
        size_row = self._exec("SELECT COUNT(*) FROM cache", fetchone=True)
        size = int(size_row[0]) if size_row else 0
        return {
            "backend": "sqlite",
            "path": self._path,
            "size": size,
            "hits": self._hits,
            "misses": self._misses,
            "maxsize": self._maxsize,
        }
