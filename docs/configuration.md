# ⚙️ Configuration

| Key                              | Type    | Default             | Environment / Context        | URI Param       | Notes                                            |
|----------------------------------|---------|---------------------|------------------------------|------------------|--------------------------------------------------|
| `grist_cfg.server`              | string  | *required*          | `GRIST_SERVER` env var       | `server`         | Base URL of Grist instance (e.g., `https://docs.getgrist.com`) |
| `grist_cfg.org_id`              | int     | *required*          | `GRIST_ORG_ID` env var       | `org_id`         | Numeric ID of your Grist organization/workspace |
| `grist_cfg.api_key`             | string  | *required*          | `GRIST_API_KEY` env var      | `api_key`        | Your personal API key from Grist                  |
| `cache_cfg.enabled`             | bool    | `False`             |                              | `cache`          | Enable query caching (metadata + records)         |
| `cache_cfg.metadata_ttl`        | seconds | `300`               |                              | `metadata_ttl`   | Duration until schema metadata is refreshed       |
| `cache_cfg.records_ttl`         | seconds | `60`                |                              | `records_ttl`    | Duration until row-data is refreshed               |
| `cache_cfg.backend`             | enum    | `sqlite`            |                              | `backend`        | `sqlite` or `memory`                              |
| `cache_cfg.filename`            | path    | `cache.sqlite`      |                              | `filename`       | Only for `sqlite` backend: name/path of DB file   |
| `cachepath`                     | path    | `~/.cache/gristapi` | `CACHEPATH` env var          | `cachepath`      | Base directory for cache files                    |


## 1) Shillelagh **CLI** → `~/.config/shillelagh/gristapi.yaml`

Use a YAML file for defaults. The CLI will pick it up automatically.

**`~/.config/shillelagh/gristapi.yaml`**

```yaml
gristapi:
  grist_cfg:
    org_id: 123
    api_key: XXXXXXXXXX
    server: https://docs.getgrist.com
  cache_cfg:
    enabled: true
    metadata_ttl: 300
    records_ttl: 60
    backend: sqlite
    filename: cache.sqlite
  cachepath: ~/.cache/gristapi
```

**Run a query**

```bash
shillelagh 'SELECT id,name FROM "grist://"'  # lists docs
```

You can still override per query:

```bash
shillelagh 'SELECT * FROM "grist://<DOC>/<TABLE>?records_ttl=0&backend=memory"'
```

---

## 2) **Python** → `adapter_kwargs`

Pass config directly when creating the connection.

```python
from shillelagh.backends.apsw.db import connect
import os

# ---------------------------------------------------------------------
# Example: Initialize a Shillelagh connection using the GristAPIAdapter
# ---------------------------------------------------------------------
#
# This creates a SQLite-like virtual database backed by the Grist REST API.
# Every Grist resource (orgs, workspaces, docs, tables, columns, records)
# can be queried as a "virtual table" via the `grist://` URI scheme.
#
# Example query patterns:
#   - SELECT * FROM "grist://__orgs__"
#   - SELECT * FROM "grist://__workspaces__"
#   - SELECT * FROM "grist://__docs__"
#   - SELECT * FROM "grist://<doc_id>"
#   - SELECT * FROM "grist://<doc_id>/<table_id>"
#   - SELECT * FROM "grist://<doc_id>/<table_id>/__columns__"
#
# The connection below demonstrates how to pass credentials, cache settings,
# and runtime parameters to the adapter via `adapter_kwargs`.

connection = connect(
    ":memory:",   # in-memory SQLite connection managed by Shillelagh

    # Each adapter can receive its own config via the "adapter_kwargs" mapping.
    adapter_kwargs={
        "gristapi": {

            # -----------------------------------------------------------------
            # grist_cfg — authentication and base configuration
            # -----------------------------------------------------------------
            # Required keys:
            #   - server:   Base URL of your Grist instance (e.g. https://grist.example.com)
            #   - org_id:   Numeric organization ID
            #   - api_key:  API token generated in your Grist profile
            #
            # You can also provide these directly in environment variables for security.
            "grist_cfg": {
                "api_key": os.environ["GRIST_API_KEY"],
                "org_id": os.environ["GRIST_ORG_ID"],
                "server": os.environ["GRIST_SERVER"],
            },

            # -----------------------------------------------------------------
            # cache_cfg — metadata & record cache configuration
            # -----------------------------------------------------------------
            # Enables local caching of both schema metadata and record data.
            #
            #   enabled       : Enable caching (True/False)
            #   metadata_ttl  : Time-to-live for metadata in seconds
            #   records_ttl   : Time-to-live for record data in seconds
            #   maxsize       : Max number of entries kept in cache
            #   backend       : "sqlite" for persistent caching, "memory" for ephemeral
            #   filename      : Cache file name (if backend = "sqlite")
            #
            # A small TTL is great for development; larger TTLs improve performance
            # for repeated queries in production.
            "cache_cfg": {
                "enabled": True,
                "metadata_ttl": 3600,
                "records_ttl": 60,
                "maxsize": 4096,
                "backend": "sqlite",
                "filename": "cache.sqlite",
            },

            # -----------------------------------------------------------------
            # cachepath — directory to store the cache file
            # -----------------------------------------------------------------
            # Default is ~/.cache/gristapi/, but you can override it here.
            # The adapter will automatically create the directory if needed.
            "cachepath": ".",
        },
    },
)

# ---------------------------------------------------------------------
# Example queries
# ---------------------------------------------------------------------
#
# You can now query Grist data using SQL:
#
#   cursor = connection.cursor()
#   for row in cursor.execute('SELECT id, name FROM "grist://__orgs__"'):
#       print(row)
#
#   # List tables in a document
#   doc_id = "doc_abcdef123456"
#   for row in cursor.execute(f'SELECT id FROM "grist://{doc_id}"'):
#       print(row)
#
#   # Fetch rows from a specific table
#   table_id = "MyTable"
#   for row in cursor.execute(f'SELECT * FROM "grist://{doc_id}/{table_id}" LIMIT 5'):
#       print(row)
#
# ---------------------------------------------------------------------
# Notes:
# ---------------------------------------------------------------------
# - All resources are read-only by design.
# - Query filters, LIMIT, and single-column ORDER BY are pushed down
#   to Grist's `/records` endpoint when possible.
# - The adapter automatically translates Grist column types to
#   appropriate Shillelagh field classes (String, Integer, Boolean, etc.).
# - If caching is enabled, repeated queries avoid hitting the API
#   until TTLs expire.
#
# For more examples and schema details, see:
#   https://github.com/qleroy/shillelagh-gristapi

```

Per-query overrides still work:

```python
cursor = connection.cursor()
cursor.execute('SELECT * FROM "grist://<DOC>/<TABLE>?records_ttl=10"')
```

---

## 3) **Apache Superset** → Database "Engine Parameters"

Create a database using the Shillelagh SQLite dialect, then put adapter config in **Engine Parameters** (JSON).

**SQLAlchemy URI**

```
shillelagh+safe://
```

**Engine Parameters** (Advanced → Other → "Engine parameters")

```json
{
  "connect_args": {
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
          "filename": "cache.sqlite"
        },
        "cachepath": "/app/cache/gristapi"
      }
    }
  }
}
```

**Example table SQL in Superset**

```
SELECT * FROM "grist://<DOC_ID>/<TABLE_ID>"
```

---

## Precedence & overrides (all environments)

* **Per-query URI params** override adapter settings:

  ```
  "grist://<DOC>/<TABLE>?records_ttl=0&backend=memory"
  ```
* Otherwise, the environment’s config source applies:

  * CLI → YAML file
  * Python → `adapter_kwargs`
  * Superset → Engine Parameters JSON

---

## Required credentials (`grist_cfg`)

| Key       | Type | Example                     | Notes                           |
| --------- | ---- | --------------------------- | ------------------------------- |
| `server`  | str  | `https://grist.example.com` | Base URL of your Grist instance |
| `org_id`  | int  | `123`                       | Organization ID                 |
| `api_key` | str  | `grist_...`                 | Personal API token              |

---

## Caching (`cache_cfg`) + `cachepath`

The adapter can cache **metadata** (schemas) and **records** locally to speed up repeated queries.

| Key            | Type  | Default             | Meaning                               |
| -------------- | ----- | ------------------- | ------------------------------------- |
| `enabled`      | bool  | `True`              | Turn caching on/off                   |
| `metadata_ttl` | int s | `300`               | Schema cache TTL                      |
| `records_ttl`  | int s | `60`                | Row cache TTL                         |
| `maxsize`      | int   | `1024`              | Max cache entries                     |
| `backend`      | str   | `"sqlite"`          | `"sqlite"` (persistent) or `"memory"` |
| `filename`     | str   | `"cache.sqlite"`    | Cache file name (no dirs)             |
| `cachepath`    | str   | `~/.cache/gristapi` | Directory for the cache file          |

**URI override (per query)**

```sql
-- This query uses a 10s records TTL and memory cache just for this call:
SELECT * FROM "grist://<DOC>/<TABLE>?records_ttl=10&backend=memory";
```

> If `backend="memory"`, the cache file path is **ignored** (as expected).

---

## Defaults (if you don’t set anything)

* `backend="sqlite"`, `filename="cache.sqlite"`, `cachepath="~/.cache/gristapi"`
* `enabled=True`, `metadata_ttl=300`, `records_ttl=60`, `maxsize=1024`

On first use the adapter will create the cache directory (or fall back to `/tmp/gristapi` if the directory isn’t writable).

---

## Precedence & merging rules

* **URI query params** override everything (ideal for dashboards or ad-hoc tuning).
* Otherwise, values come from **`adapter_kwargs["gristapi"]`**:

  * Auth in `grist_cfg`
  * Cache knobs in `cache_cfg`
  * `cachepath` alongside `cache_cfg`
* Anything not supplied uses **defaults** above.

---

## Quick recipes

**1) Disable caching completely**

```python
"cache_cfg": {"enabled": False, "backend": "memory"}
```

**2) Keep metadata longer, but refresh rows frequently**

```python
"cache_cfg": {"metadata_ttl": 3600, "records_ttl": 15}
```

**3) Use a project-local cache file (repo root)**

```python
"cache_cfg": {"backend": "sqlite", "filename": "grist_cache.sqlite"},
"cachepath": ".",
```

**4) Force per-query freshness (ignore cache) via URI**

```sql
SELECT * FROM "grist://<DOC>/<TABLE>?records_ttl=0&metadata_ttl=0";
```

---

## Troubleshooting

* **"cachepath doesn’t work"**
  Ensure it’s a directory you can write to. The adapter expands `~`, creates the directory, tests writability, and falls back to `/tmp/gristapi` if needed. Check logs for the chosen path.

* **Permission errors in Docker/K8s**
  Mount a writable volume and point `cachepath` there, e.g. `-v $(pwd)/.cache:/cache` and `"cachepath": "/cache"`.

* **URI quoting**
  In SQLite/SQLAlchemy, use **double quotes** around the `grist://...` string:
  `SELECT * FROM "grist://<DOC>/<TABLE>"`

* **Performance**
  Increase `records_ttl` for dashboards with the same queries; use `IN`/`=` filters and single-column `ORDER BY` to maximize pushdown to `/records`.

---

## What can be overridden via the URI?

You can override **any** of these per query:

```
server, org_id, api_key,
enabled, metadata_ttl, records_ttl, maxsize, backend, filename, cachepath
```

**Example**

```sql
SELECT *
FROM "grist://<DOC>/<TABLE>?server=https://grist.example.com&org_id=123&records_ttl=5&backend=memory";
```

> Only use URI overrides for quick experiments; for production, prefer `adapter_kwargs`.