"""Tests for MemoryCache and SQLiteCache."""
import time

import pytest

from shillelagh_gristapi.cache import MemoryCache, SQLiteCache

KEY_A = ("ns", ("a",))
KEY_B = ("ns", ("b",))
VALUE = [{"x": 1}]


# ---------------------------------------------------------------------------
# MemoryCache
# ---------------------------------------------------------------------------


class TestMemoryCache:
    def test_miss_returns_none(self):
        cache = MemoryCache(maxsize=10)
        assert cache.get(KEY_A) is None

    def test_set_and_get(self):
        cache = MemoryCache(maxsize=10)
        cache.set(KEY_A, VALUE, ttl=60)
        assert cache.get(KEY_A) == VALUE

    def test_ttl_expiry(self, monkeypatch):
        cache = MemoryCache(maxsize=10)
        now = time.time()
        monkeypatch.setattr(time, "time", lambda: now)
        cache.set(KEY_A, VALUE, ttl=10)

        # still valid
        assert cache.get(KEY_A) == VALUE

        # after TTL expires
        monkeypatch.setattr(time, "time", lambda: now + 11)
        assert cache.get(KEY_A) is None

    def test_ttl_zero_not_stored(self):
        cache = MemoryCache(maxsize=10)
        cache.set(KEY_A, VALUE, ttl=0)
        assert cache.get(KEY_A) is None

    def test_lru_eviction(self):
        cache = MemoryCache(maxsize=2)
        cache.set(KEY_A, "a", ttl=60)
        cache.set(KEY_B, "b", ttl=60)
        # access KEY_A so KEY_B becomes the LRU
        cache.get(KEY_A)
        key_c = ("ns", ("c",))
        cache.set(key_c, "c", ttl=60)
        # KEY_B should have been evicted
        assert cache.get(KEY_B) is None
        assert cache.get(KEY_A) == "a"
        assert cache.get(key_c) == "c"

    def test_clear(self):
        cache = MemoryCache(maxsize=10)
        cache.set(KEY_A, VALUE, ttl=60)
        cache.clear()
        assert cache.get(KEY_A) is None

    def test_stats(self):
        cache = MemoryCache(maxsize=10)
        cache.set(KEY_A, VALUE, ttl=60)
        cache.get(KEY_A)  # hit
        cache.get(KEY_B)  # miss
        stats = cache.stats()
        assert stats["backend"] == "memory"
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["size"] == 1
        assert stats["maxsize"] == 10

    def test_non_json_serializable_not_stored(self):
        cache = MemoryCache(maxsize=10)
        cache.set(KEY_A, object(), ttl=60)
        assert cache.get(KEY_A) is None

    def test_overwrite_existing_key(self):
        cache = MemoryCache(maxsize=10)
        cache.set(KEY_A, "first", ttl=60)
        cache.set(KEY_A, "second", ttl=60)
        assert cache.get(KEY_A) == "second"


# ---------------------------------------------------------------------------
# SQLiteCache
# ---------------------------------------------------------------------------


class TestSQLiteCache:
    @pytest.fixture
    def cache(self, tmp_path):
        return SQLiteCache(str(tmp_path / "test.sqlite"), maxsize=10)

    def test_miss_returns_none(self, cache):
        assert cache.get(KEY_A) is None

    def test_set_and_get(self, cache):
        cache.set(KEY_A, VALUE, ttl=60)
        assert cache.get(KEY_A) == VALUE

    def test_ttl_expiry(self, cache, monkeypatch):
        now = time.time()
        monkeypatch.setattr(time, "time", lambda: now)
        cache.set(KEY_A, VALUE, ttl=10)
        assert cache.get(KEY_A) == VALUE

        monkeypatch.setattr(time, "time", lambda: now + 11)
        assert cache.get(KEY_A) is None

    def test_ttl_zero_not_stored(self, cache):
        cache.set(KEY_A, VALUE, ttl=0)
        assert cache.get(KEY_A) is None

    def test_lru_eviction(self, tmp_path):
        cache = SQLiteCache(str(tmp_path / "lru.sqlite"), maxsize=2)
        cache.set(KEY_A, "a", ttl=60)
        cache.set(KEY_B, "b", ttl=60)
        # touch KEY_A so it's more recent
        cache.get(KEY_A)
        key_c = ("ns", ("c",))
        cache.set(key_c, "c", ttl=60)
        # KEY_B is the least recently used → evicted
        assert cache.get(KEY_B) is None
        assert cache.get(KEY_A) == "a"
        assert cache.get(key_c) == "c"

    def test_clear(self, cache):
        cache.set(KEY_A, VALUE, ttl=60)
        cache.clear()
        assert cache.get(KEY_A) is None

    def test_stats(self, cache):
        cache.set(KEY_A, VALUE, ttl=60)
        cache.get(KEY_A)  # hit
        cache.get(KEY_B)  # miss
        stats = cache.stats()
        assert stats["backend"] == "sqlite"
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["size"] == 1

    def test_non_json_serializable_not_stored(self, cache):
        cache.set(KEY_A, object(), ttl=60)
        assert cache.get(KEY_A) is None

    def test_overwrite_existing_key(self, cache):
        cache.set(KEY_A, "first", ttl=60)
        cache.set(KEY_A, "second", ttl=60)
        assert cache.get(KEY_A) == "second"

    def test_creates_parent_directory(self, tmp_path):
        nested = tmp_path / "a" / "b" / "cache.sqlite"
        cache = SQLiteCache(str(nested), maxsize=5)
        cache.set(KEY_A, "x", ttl=60)
        assert cache.get(KEY_A) == "x"
