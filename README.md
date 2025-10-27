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
  - **CLI**: via the `shillelagh` shell,
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

- Find your `API_KEY` in your profile settings. See [Grist docs](https://support.getgrist.com/rest-api/#authentication).
- Find your `ORG_ID` with the orgs endpoint, e.g. `curl -H "Authorization: Bearer "/api/orgs/" | jq '.[]|.id'`.
- `SERVER` is the base URL of your Grist deployment, e.g. docs.getgrist.com.

The adapter reads settings from:

1. **URI query parameters**
2. **`adapter_kwargs["gristapi"]`**
3. **Built-in defaults**

Minimal setup requires:

```python
"grist_cfg": {
  "server": "https://docs.getgrist.com",
  "org_id": 123,
  "api_key": "XXXXXXXXX",
}
```

Optional caching:

```python
"cache_cfg": {
  "enabled": True,
  "metadata_ttl": 300,
  "records_ttl": 60,
  "backend": "sqlite",
  "filename": "cache.sqlite",
},
"cachepath": "~/.cache/gristapi"
```

Override any parameter per query:

```sql
SELECT * FROM "grist://<DOC_ID>/<TABLE_ID>?records_ttl=30&backend=memory";
```

➡️ See [config.md](docs/configuration.md) for full details, examples, defaults, and troubleshooting.

---

## 🧑‍💻 Usage

The GristAPIAdapter exposes the [Grist REST API](https://support.getgrist.com/api/)
as virtual SQL tables using [Shillelagh](https://github.com/betodealmeida/shillelagh).
This allows you to explore and query your Grist data directly from Python (or any tool that speaks SQLite)
without writing any HTTP calls or parsing JSON manually.

### 🖥️ CLI

Default configuration in `~/.config/shillelagh/shillelagh.yaml`:

```bash
$ shillelagh
-- ---------------------------------------------------------------------
-- 🌐 Explore your Grist instance via SQL
-- ---------------------------------------------------------------------
-- Each URI corresponds to a Grist REST endpoint exposed as a virtual table.
-- You can use standard SQL (SELECT, WHERE, LIMIT, ORDER BY) from Shillelagh.

-- 1️⃣  List all accessible documents
-- Equivalent to: GET /api/orgs/{orgId}/workspaces/{workspaceId}/docs
-- API reference: https://support.getgrist.com/api/#tag/workspaces/operation/listWorkspaces
SELECT * FROM "grist://";

-- 2️⃣  List tables inside a specific document
-- Replace <DOC_ID> with your actual document ID (e.g. "doc_abcdef123456").
-- Equivalent to: GET /api/docs/{docId}/tables
-- API reference: https://support.getgrist.com/api/#tag/tables/operation/listTables
SELECT * FROM "grist://<DOC_ID>";

-- 3️⃣  Fetch all records from a specific table
-- Replace <DOC_ID> and <TABLE_ID> with your actual IDs.
-- Equivalent to: GET /api/docs/{docId}/tables/{tableId}/records
-- API reference: https://support.getgrist.com/api/#tag/records
SELECT * FROM "grist://<DOC_ID>/<TABLE_ID>";

-- 4️⃣  Example: filtered and limited query (pushdown supported)
-- WHERE clauses on equality are pushed down to Grist's /records endpoint.
SELECT id, Name
FROM "grist://doc_abcdef123456/Employees"
WHERE Department = 'Finance'
ORDER BY id
LIMIT 10;

```

### 🐍 Python

```python
from shillelagh.backends.apsw.db import connect
import os

connection = connect(
    ":memory:"
    adapter_kwargs={
        "gristapi": {
            "grist_cfg": {
                "api_key": os.environ["GRIST_API_KEY"],
                "org_id": os.environ["GRIST_ORG_ID"],
                "server": os.environ["GRIST_SERVER"],
            },
        },
    },
)
cursor = connection.cursor()

# List document ids
# https://support.getgrist.com/api/#tag/workspaces/operation/listWorkspaces
query_docs = "SELECT * FROM 'grist://';"
cursor.execute(query_docs).fetchall()

# List table ids
# https://support.getgrist.com/api/#tag/tables/operation/listTables
query_tables = "SELECT * FROM 'grist://<replace-with-a-doc-id>';"
cursor.execute(query_tables).fetchall()

# Fetch records
# https://support.getgrist.com/api/#tag/records
query = "SELECT * FROM 'grist://<replace-with-a-doc-id>/<replace-with-a-table-id>';"
cursor.execute(query).fetchall()
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
  "connect_args": {
    "adapters": ["gristapi"],
    "adapter_kwargs": {
      "gristapi": {
        "grist_cfg": {
          "api_key": "<REPLACE_WITH_YOUR_API_KEY>",
          "org_id": "<REPLACE_WITH_YOUR_ORG_ID>",
          "server": "<REPLACE_WITH_YOUR_SERVER_URL>",
        }
      }
    }
  }
}
```
- Create a virtual dataset using a Grist URI, e.g.:
```sql
select * from 'grist://<DOC_ID>/<TABLE_ID>'
```

➡️ See [superset.md](docs/superset.md) for full details and examples.

| SqlAlchemy URI | Engine parameters |
| --- | --- |
| ![screenshot base](images/screenshot_base.png)| ![screenshot parametres](images/screenshot_parametres.png) | 

| SQL Lab |
| -- |
|![screenshot sql lab](images/screenshot_sqllab.png)|

--- 

## 🧠 Notes
- All data access is read-only (no insert/update/delete).
- `WHERE` (equality), `LIMIT`, and `ORDER BY` are pushed down to the /records API.
- Caching reduces repeated API calls and speeds up interactive use.
- Supported Grist type mapping →  Shillelagh field types:
| Grist Type                | Shillelagh Field    | 
|---------------------------|---------------------|
| Text                      | String()            |
| Choice                    | String()            |
| Int                       | Integer()           |
| Numeric                   | Float()             |
| Bool                      | Boolean()           |
| DateTime / Date           | DateTime()          |

## 📄 License
MIT — see [LICENSE](/LICENSE).