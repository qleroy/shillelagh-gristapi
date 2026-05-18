# Getting Started

## Prerequisites

- **Python 3.9+**
- **Grist API key** — find it in your Grist profile under "API key". See the [Grist authentication docs](https://support.getgrist.com/rest-api/#authentication).
- **org_id** — the numeric ID of your Grist organization. You can discover it with:
  ```bash
  curl -H "Authorization: Bearer <YOUR_API_KEY>" https://docs.getgrist.com/api/orgs | jq '.[].id'
  ```
- **server URL** — the base URL of your Grist deployment, e.g. `https://docs.getgrist.com` for the hosted service or `https://grist.example.com` for a self-hosted instance.

## Install

```bash
pip install shillelagh-gristapi
```

For the interactive CLI:

```bash
pip install 'shillelagh[console]'
```

From source (with dev dependencies):

```bash
git clone https://github.com/qleroy/shillelagh-gristapi.git
cd shillelagh-gristapi
pip install -e .[dev]
```

## Step-by-step: first queries

### 1. Connect

```python
from shillelagh.backends.apsw.db import connect
import os

conn = connect(
    ":memory:",
    adapter_kwargs={"gristapi": {"grist_cfg": {
        "server": os.environ["GRIST_SERVER"],       # e.g. "https://docs.getgrist.com"
        "org_id": int(os.environ["GRIST_ORG_ID"]), # e.g. 42
        "api_key": os.environ["GRIST_API_KEY"],
    }}},
)
cursor = conn.cursor()
```

### 2. List documents

```python
docs = cursor.execute('SELECT id, name FROM "grist://"').fetchall()
for doc_id, name in docs:
    print(doc_id, name)
```

### 3. List tables in a document

```python
doc_id = "<YOUR_DOC_ID>"
tables = cursor.execute(f'SELECT id FROM "grist://{doc_id}"').fetchall()
for (table_id,) in tables:
    print(table_id)
```

### 4. Query rows from a table

```python
table_id = "<YOUR_TABLE_ID>"
rows = cursor.execute(
    f'SELECT * FROM "grist://{doc_id}/{table_id}" LIMIT 5'
).fetchall()
for row in rows:
    print(row)
```

### 5. Filter and sort (pushed down to Grist API)

```python
rows = cursor.execute(
    f'SELECT id, Name FROM "grist://{doc_id}/{table_id}" '
    "WHERE Department = 'Finance' ORDER BY id LIMIT 10"
).fetchall()
```

Equality `WHERE` clauses, `ORDER BY`, and `LIMIT` are sent directly to the Grist `/records` endpoint, minimizing data transfer.

## CLI usage

Add your credentials to `~/.config/shillelagh/shillelagh.yaml`:

```yaml
gristapi:
  grist_cfg:
    server: https://docs.getgrist.com
    org_id: 42
    api_key: your_api_key_here
```

Then run queries:

```bash
shillelagh 'SELECT id, name FROM "grist://"'
shillelagh 'SELECT * FROM "grist://<DOC_ID>/<TABLE_ID>" LIMIT 5'
```

## Next steps

- [docs/configuration.md](configuration.md) — all configuration options, caching, and per-query URI overrides
- [docs/uri-reference.md](uri-reference.md) — complete list of `grist://` URI patterns and their column schemas
