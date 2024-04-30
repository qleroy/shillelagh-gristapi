from requests_cache import BaseCache, SQLiteCache

_REQUEST_CACHE_BACKEND = None

def setup_request_cache_backend(backend: BaseCache):
    global _REQUEST_CACHE_BACKEND
    _REQUEST_CACHE_BACKEND = backend

def request_cache_backend():
    global _REQUEST_CACHE_BACKEND
    if _REQUEST_CACHE_BACKEND is None:
        _REQUEST_CACHE_BACKEND = SQLiteCache()

    return _REQUEST_CACHE_BACKEND