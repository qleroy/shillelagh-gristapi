# shillelagh-gristapi

A **[Shillelagh](https://github.com/betodealmeida/shillelagh) adapter** for the [Grist REST API](https://support.getgrist.com/api/).  
It lets you query Grist documents and tables with **SQL** via SQLite/SQLAlchemy,  
ideal for BI tools like [Apache Superset](https://superset.apache.org/).

---

## ✨ Features

- Query Grist documents, tables, and records as if they were **SQL tables**
- Supports core SQL operations:
  - `SELECT` statements on Grist tables
  - Filter pushdown for `=` condition
  - Server-side sorting and `LIMIT`
- Built-in discovery helpers:
  - `grist://` → list all documents
  - `grist://<doc_id>` → list tables in a document
  - `grist://<doc_id>/<table_id>` → query rows in a table
- Flexible usage:
  - **CLI**: via the `shillelagh` shell or `python -m shillelagh_gristapi ...`
  - **Python**: connect directly with the `connect()` API
  - **Superset**: drop-in integration for dashboards
- **Enforces Grist access rules**:  
  Your Grist permissions carry over automatically.  
  If you can only see certain tables, columns, or rows in Grist,  
  you’ll see exactly the same restrictions through this adapter.

---

## 🚀 Installation

```bash
pip install shillelagh-gristapi
# CLI
pip install 'shillelagh[console]'
```

Or from source:

```bash
git clone https://github.com/qleroy/shillelagh-gristapi.git
cd shillelagh-gristapi
pip install -e .[dev]
```

---

## ⚙️ Configuration
You need a Grist API key. 
- Fin doou `API_KEY` in your profile settings. See [Grist docs](https://support.getgrist.com/rest-api/).
- Find your `ORG_ID`  with the [orgs endpoint](https://support.getgrist.com/api/#tag/orgs/operation/listOrgs), e.g. curl -H "Authorization: Bearer <replace-with-your-apy-key> "<replace-with-your-server>/api/orgs/" | jq '.[]|.id',

```yaml
gristapi:
  api_key: ${API_KEY} 
  org_id: ${ORG_ID} 
  server: ${SERVER} # e.g. https://docs.getgrist.com
```

---

## 🧑‍💻 Usage

### 🖥️ CLI

Default configuration in `~/.config/shillelagh/shillelagh.yaml`:

```bash
$ shillelagh
# List document ids
# https://support.getgrist.com/api/#tag/workspaces/operation/listWorkspaces
SELECT * FROM 'grist://';

# List table ids
# https://support.getgrist.com/api/#tag/tables/operation/listTables
SELECT * FROM 'grist://<replace-with-a-doc-id>';

# Fetch records
# https://support.getgrist.com/api/#tag/records
SELECT * FROM 'grist://<replace-with-a-doc-id>/<replace-with-a-table-id>';
```

### 🐍 Python

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
                "metadata_ttl": 10,
                "records_ttl": 10,
                "maxsize": 2,
                "backend": "sqlite",
                "filename": "grist_cache",
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

### 📊 Apache Superset

- Install `shillelagh` + this adapter in your Superset image;
- Add a Shillelagh database with URI
```
shillelagh+safe://
```
- Configure the engine parameters
```json
{
  "connect_args":
    {
      "adapters":
        ["gristapi"],
      "adapter_kwargs":
        {
          "gristapi":{
            "api_key": "<REPLACE_WITH_YOUR_API_KEY>",
            "org_id": "<REPLACE_WITH_YOUR_ORD_ID>",
            "server": "<REPLACE_WITH_YOUR_SERVER_URL>",
          }
        }
    }
}
```
- Create a virtual dataset using a Grist URI, e.g.:
```sql
select * from 'grist://<doc-id>/<table-id>'
```

| SqlAlchemy URI | Engine parameters |
| --- | --- |
| ![screenshot base](images/screenshot_base.png)| ![screenshot parametres](images/screenshot_parametres.png) | 

| SQL Lab |
| -- |
|![screenshot sql lab](images/screenshot_sqllab.png)|

--- 

## 📄 License
MIT — see (LICENSE)[/LICENSE].