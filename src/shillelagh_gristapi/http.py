from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Iterator, Mapping, Tuple, Optional
import json
import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .cache import MemoryCache
from .cache import SQLiteCache


logger = logging.getLogger(__name__)
DEFAULT_TIMEOUT = 10  # seconds
DEFAULT_USER_AGENT = "shillelagh-gristapi/dev"


@dataclass(frozen=True, slots=True)
class CacheConfig:
    enabled: bool = True
    metadata_ttl: int = 300  # seconds for orgs/workspaces/tables/columns
    records_ttl: int = 60  # seconds for /records (0 = disabled)
    maxsize: int = 1024  # max distinct cached entries
    backend: str = "memory"  # "memory" or "sqlite"
    path: Optional[str] = None  # required if backend == "sqlite"


def _retry_adapter(timeout: int = DEFAULT_TIMEOUT) -> HTTPAdapter:
    retry = Retry(
        total=5,
        backoff_factor=0.5,
        status_forcelist={429, 500, 502, 503, 504},
        allowed_methods={"GET", "POST", "PATCH", "DELETE"},
        respect_retry_after_header=True,
        raise_on_status=False,
    )

    class TimeoutAdapter(HTTPAdapter):
        def send(self, request, **kwargs):  # type: ignore[override]
            kwargs.setdefault("timeout", timeout)
            return super().send(request, **kwargs)

    return TimeoutAdapter(max_retries=retry)


@dataclass(frozen=True, slots=True)
class ClientConfig:
    server: str
    api_key: str
    cache: CacheConfig
    user_agent: str = DEFAULT_USER_AGENT


def _freeze(value: Any) -> Any:
    """Make nested structures hashable (for cache keys)."""
    if isinstance(value, Mapping):
        return tuple(sorted((k, _freeze(v)) for k, v in value.items()))
    if isinstance(value, (list, tuple, set)):
        return tuple(_freeze(v) for v in value)
    return value


class GristClient:
    """
    Tiny HTTP client wrapper for Grist REST calls.
    Docs: https://support.getgrist.com/api/
    """

    def __init__(self, cfg: ClientConfig):
        server = cfg.server.rstrip("/")
        self.cfg = ClientConfig(
            server=server,
            api_key=cfg.api_key,
            user_agent=cfg.user_agent,
            cache=cfg.cache,
        )
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {cfg.api_key}",
                "Accept": "application/json",
                "User-Agent": cfg.user_agent or DEFAULT_USER_AGENT,
            }
        )
        adapter = _retry_adapter()
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        # pick cache backend
        if cfg.cache.enabled:
            if cfg.cache.backend == "sqlite":
                if not cfg.cache.path:
                    raise ValueError(
                        "CacheConfig.path is required when backend='sqlite'"
                    )
                self._cache_backend = SQLiteCache(cfg.cache.path, cfg.cache.maxsize)
            else:
                self._cache_backend = MemoryCache(cfg.cache.maxsize)
        else:
            self._cache_backend = None

    def _make_key(self, name: str, *parts: Any) -> Tuple[str, Tuple[Any, ...]]:
        logger.debug("Making cache key for %s with parts %r", name, parts)
        return (name, tuple(_freeze(p) for p in parts))

    def clear_cache(self) -> None:
        if self._cache_backend:
            self._cache_backend.clear()

    def _cache_get(self, key: Tuple[str, Tuple[Any, ...]]) -> Optional[Any]:
        logger.debug("Cache get %s", key)
        if not self._cache_backend:
            return None
        return self._cache_backend.get(key)

    def _cache_set(
        self, key: Tuple[str, Tuple[Any, ...]], value: Any, ttl: int
    ) -> None:
        logger.debug("Cache set %s with %s", key, ttl)
        if not self._cache_backend:
            return
        self._cache_backend.set(key, value, ttl)

    # --- helpers ---
    def _url(self, path: str) -> str:
        return f"{self.cfg.server}{path}"

    # --- API methods ---
    def list_orgs(
        self,
        *,
        timeout: Optional[float] = None,
    ) -> Iterable[Dict[str, Any]]:
        """
        Retrieve organizations accessible to the current user.

        Args:
            timeout: Optional request timeout.

        Yields:
            Organization metadata dictionaries.
        """
        key = self._make_key("list_orgs")
        cached = self._cache_get(key)
        if cached is not None:
            return cached

        url = self._url("/api/orgs")
        response = self.session.get(url, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        self._cache_set(key, data, self.cfg.cache.metadata_ttl)
        return data

    def list_workspaces(
        self,
        org_id: int,
        *,
        timeout: Optional[float] = None,
    ) -> Iterable[Dict[str, Any]]:
        """
        Retrieve all workspaces for a given organization.

        Args:
            org_id: Organization ID.
            timeout: Optional request timeout.

        Returns:
            A list of workspace metadata dictionaries.
        """
        key = self._make_key("list_workspaces", org_id)
        cached = self._cache_get(key)
        if cached is not None:
            return cached

        url = self._url(f"/api/orgs/{org_id}/workspaces")
        response = self.session.get(url, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        self._cache_set(key, data, self.cfg.cache.metadata_ttl)
        return data

    def list_docs(
        self,
        org_id: int,
        ws_id: Optional[int] = None,
        *,
        timeout: Optional[float] = None,
    ) -> Iterable[Dict[str, Any]]:
        """
        List documents within workspaces of a given organization.

        Args:
            org_id: Organization ID to list docs from.
            ws_id: Optional workspace ID to filter results.
            timeout: Optional timeout for workspace retrieval.

        Yields:
            Dict containing workspace and document metadata.
        """
        # Cache at the flattened docs level for convenience
        key = self._make_key("list_docs", org_id, ws_id)
        cached = self._cache_get(key)
        if cached is not None:
            return cached

        workspaces = self.list_workspaces(org_id, timeout=timeout)
        docs = []
        for ws in workspaces:
            if ws_id is not None and int(ws_id) != ws.get("id"):
                continue
            for doc in ws.get("docs", []) or []:
                docs.append(
                    {
                        "workspace_id": ws["id"],
                        "workspace_name": ws["name"],
                        "workspace_access": ws["access"],
                        "org_domain": ws["orgDomain"],
                        "doc_id": doc["id"],
                        "doc_name": doc["name"],
                        "doc_created_at": doc["createdAt"],
                        "doc_updated_at": doc["updatedAt"],
                    }
                )
        self._cache_set(key, docs, self.cfg.cache.metadata_ttl)
        return docs

    def list_tables(
        self,
        doc_id: str,
        *,
        timeout: Optional[float] = None,
    ) -> Iterable[Dict[str, Any]]:
        """
        Retrieve tables for a given document.

        Args:
            doc_id: Document ID.
            timeout: Optional request timeout.

        Yields:
            Table metadata dictionaries.
        """
        key = self._make_key("list_tables", doc_id)
        cached = self._cache_get(key)
        if cached is not None:
            return cached

        url = self._url(f"/api/docs/{doc_id}/tables")
        response = self.session.get(url, timeout=timeout)
        response.raise_for_status()
        data = response.json()["tables"]
        self._cache_set(key, data, self.cfg.cache.metadata_ttl)
        return data

    def list_columns(
        self,
        doc_id: str,
        table_id: str,
        hidden: bool = True,
        *,
        timeout: Optional[float] = None,
    ) -> Iterable[Dict[str, Any]]:
        """
        Retrieve columns for a given table in a document.

        Args:
            doc_id: Document ID.
            table_id: Table ID (name).
            timeout: Optional request timeout.

        Yields:
            Column metadata dictionaries.
        """
        key = self._make_key("list_columns", doc_id, table_id)
        cached = self._cache_get(key)
        if cached is not None:
            return cached

        q = dict()
        if hidden:
            q["hidden"] = "true"
        else:
            q["hidden"] = "false"
        url = self._url(f"/api/docs/{doc_id}/tables/{table_id}/columns")
        response = self.session.get(url, params=q, timeout=timeout)
        response.raise_for_status()
        data = response.json()["columns"]
        self._cache_set(key, data, self.cfg.cache.metadata_ttl)
        return data

    def iter_records(
        self,
        doc_id: str,
        table_id: str,
        hidden: bool = True,
        *,
        params: Optional[Mapping[str, Any]] = None,
        include_id: bool = True,
        timeout: Optional[float] = None,
    ) -> Iterator[Mapping[str, Any]]:
        """
        Yield rows from the /records endpoint using a single request.

        This function intentionally avoids any paging/cursor logic. The Grist
        /records API supports filter, sort, limit, and hidden; it does not provide
        a cursor/offset. We therefore fetch all rows (limit=0, unless caller sets
        a positive limit) and yield them in the server's returned order.

        Args:
            doc_id: Grist doc ID.
            table_id: Grist table ID (name).
            params: Optional dict of /records params:
                - filter: dict or JSON string mapping column -> list of allowed values.
                - sort:   e.g. "id", "pet,-age", "manualSort",
                        or options like "pet,-age:naturalSort;emptyFirst".
                - limit:  int. If omitted, defaults to 0 (no limit) to fetch all rows.
                - hidden: bool. If True, include hidden columns (often needed for manualSort).
            batch_size: Unused (kept for API compatibility).
            include_id: If True, include the row id as `_id` in each yielded row.
            timeout: Optional request timeout (seconds).

        Yields:
            Dict representing each row's fields; includes `_id` when include_id=True.
        """
        # Build query params safely
        q: Dict[str, Any] = {}
        if params:
            q.update(params)

        # Default to stable ascending id ordering
        q.setdefault("sort", "id")

        # Normalize `filter` to a JSON string if caller passed a dict-like
        filt = q.get("filter")
        if isinstance(filt, Mapping):
            q["filter"] = json.dumps(dict(filt))  # ensure plain dict before dumps

        # If sorting by manualSort, hidden columns are often required
        if "manualSort" in str(q.get("sort", "")) and "hidden" not in q:
            q["hidden"] = True

        # Unless caller explicitly set a limit, fetch all rows
        q.setdefault("limit", 0)  # 0 = no limit per Grist API

        # ---- cache key for records (disabled by default) ----
        key = self._make_key("iter_records", doc_id, table_id, q)
        cached = self._cache_get(key) if self.cfg.cache.records_ttl > 0 else None
        if cached is not None:
            for row in cached:
                yield dict(row)
            return

        if hidden:
            q["hidden"] = "true"
        else:
            q["hidden"] = "false"
        url = self._url(f"/api/docs/{doc_id}/tables/{table_id}/records")
        response = self.session.get(url, params=q, timeout=timeout)
        response.raise_for_status()

        payload = response.json() or {}
        records = payload.get("records", []) or []

        # Yield rows in the order provided by the server (sorted by 'id' by default)
        rows: list[Dict[str, Any]] = []
        for rec in records:
            rid = rec.get("id")
            fields = rec.get("fields", {}) or {}
            row = dict(fields)
            if include_id:
                row["id"] = rid
            rows.append(row)

        # cache whole row-set if enabled
        if self.cfg.cache.records_ttl > 0:
            self._cache_set(key, rows, self.cfg.cache.records_ttl)

        for row in rows:
            yield row
