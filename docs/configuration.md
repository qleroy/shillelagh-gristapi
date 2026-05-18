# Configuration

## Configuration parameters

| Key | Type | Default | URI param | Notes |
|---|---|---|---|---|
| `grist_cfg.server` | string | *required* | `server` | Base URL of your Grist instance |
| `grist_cfg.org_id` | int | *required* | `org_id` | Numeric organization ID |
| `grist_cfg.api_key` | string | *required* | `api_key` | Personal API token from Grist |
| `grist_cfg.verify` | bool or string | `True` | — | `false` to skip TLS verification (self-signed certs), or path to a CA bundle |
| `cache_cfg.enabled` | bool | `True` | `enabled` | Enable caching (metadata + records) |
| `cache_cfg.metadata_ttl` | seconds | `300` | `metadata_ttl` | Schema cache TTL |
| `cache_cfg.records_ttl` | seconds | `60` | `records_ttl` | Row cache TTL |
| `cache_cfg.maxsize` | int | `1024` | `maxsize` | Max cache entries |
| `cache_cfg.backend` | enum | `"sqlite"` | `backend` | `"sqlite"` or `"memory"` |
| `cache_cfg.filename` | string | `"grist_cache.sqlite"` | `filename` | Cache file name (no directories) |
| `cachepath` | path | `~/.cache/gristapi` | `cachepath` | Directory for the cache file |

## 1) Shillelagh CLI

Add credentials to `~/.config/shillelagh/shillelagh.yaml`:

```yaml
gristapi:
  grist_cfg:
    server: https://docs.getgrist.com
    org_id: 123
    api_key: XXXXXXXXXX
  cache_cfg:
    enabled: true
    metadata_ttl: 300
    records_ttl: 60
    backend: sqlite
    filename: grist_cache.sqlite
  cachepath: ~/.cache/gristapi
```

Run a query:

```bash
shillelagh 'SELECT id, name FROM "grist://"'
```

Override per query:

```bash
shillelagh 'SELECT * FROM "grist://<DOC>/<TABLE>?records_ttl=0&backend=memory"'
```

## 2) Python

Pass configuration via `adapter_kwargs` when creating the connection:

```python
from shillelagh.backends.apsw.db import connect
import os

conn = connect(
    ":memory:",
    adapter_kwargs={
        "gristapi": {
            "grist_cfg": {
                "server": os.environ["GRIST_SERVER"],
                "org_id": int(os.environ["GRIST_ORG_ID"]),
                "api_key": os.environ["GRIST_API_KEY"],
            },
            "cache_cfg": {
                "enabled": True,
                "metadata_ttl": 300,
                "records_ttl": 60,
                "maxsize": 1024,
                "backend": "sqlite",
                "filename": "grist_cache.sqlite",
            },
            "cachepath": "~/.cache/gristapi",
        }
    },
)
cursor = conn.cursor()
```

Override per query:

```python
cursor.execute('SELECT * FROM "grist://<DOC>/<TABLE>?records_ttl=10"')
```

## 3) Apache Superset

See [superset.md](superset.md) for a full walkthrough. In brief:

**SQLAlchemy URI**

```
shillelagh+safe://
```

**Engine Parameters** (Advanced → Other → "Engine parameters")

```json
{
  "connect_args": {
    "adapters": ["gristapi"],
    "adapter_kwargs": {
      "gristapi": {
        "grist_cfg": {
          "server": "https://docs.getgrist.com",
          "org_id": 123,
          "api_key": "XXXXXXX"
        },
        "cache_cfg": {
          "enabled": true,
          "metadata_ttl": 300,
          "records_ttl": 60,
          "backend": "sqlite",
          "filename": "grist_cache.sqlite"
        },
        "cachepath": "/app/cache/gristapi"
      }
    }
  }
}
```

## Precedence

1. **URI query parameters** (highest) — override per query
2. **`adapter_kwargs["gristapi"]`** — set at connection time
3. **Built-in defaults** (lowest)

## Quick recipes

**1) Disable caching completely**

```python
"cache_cfg": {"enabled": False, "backend": "memory"}
```

**2) Keep metadata longer, refresh rows frequently**

```python
"cache_cfg": {"metadata_ttl": 3600, "records_ttl": 15}
```

**3) Use a project-local cache file**

```python
"cache_cfg": {"backend": "sqlite", "filename": "grist_cache.sqlite"},
"cachepath": ".",
```

**4) Force freshness for a single query via URI**

```sql
SELECT * FROM "grist://<DOC>/<TABLE>?records_ttl=0&metadata_ttl=0";
```

## Troubleshooting

- **"cachepath doesn't work"**
  Ensure it's a writable directory. The adapter expands `~`, creates the directory, tests writability, and falls back to `/tmp/gristapi` if needed. Check logs for the chosen path.

- **Permission errors in Docker/Kubernetes**
  Mount a writable volume and point `cachepath` there:
  ```
  -v $(pwd)/.cache:/cache
  ```
  and set `"cachepath": "/cache"`.

- **URI quoting**
  In SQLite/SQLAlchemy, use double quotes around the `grist://` string:
  `SELECT * FROM "grist://<DOC>/<TABLE>"`

- **Performance**
  Increase `records_ttl` for dashboards with repeated queries. Use `=` or `IN` filters and `ORDER BY` to maximize pushdown to the Grist `/records` endpoint.
