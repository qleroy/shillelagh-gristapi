# shillelagh-gristapi

A [Shillelagh](https://github.com/betodealmeida/shillelagh) adapter that exposes the [Grist REST API](https://support.getgrist.com/api/) as SQL-queryable virtual tables via SQLite/SQLAlchemy.

## Features

- Query Grist documents, tables, and records with SQL
- Filter pushdown for `=` and `IN` conditions; server-side `ORDER BY` and `LIMIT`
- Discovery queries: list organizations, workspaces, documents, and tables via `grist://` URIs
- Column metadata introspection via `grist://<doc_id>/<table_id>/__columns__`
- Built-in TTL caching (SQLite or in-memory) to reduce API calls
- Enforces Grist access rules — your API key permissions apply automatically
- Works with Apache Superset, the `shillelagh` CLI, and any SQLAlchemy-compatible tool

## Installation

```bash
pip install shillelagh-gristapi
```

For the interactive CLI:

```bash
pip install 'shillelagh[console]'
```

For source installation, see [docs/getting-started.md](docs/getting-started.md).

## Quickstart

```python
from shillelagh.backends.apsw.db import connect
import os

conn = connect(
    ":memory:",
    adapter_kwargs={"gristapi": {"grist_cfg": {
        "server": os.environ["GRIST_SERVER"],
        "org_id": int(os.environ["GRIST_ORG_ID"]),
        "api_key": os.environ["GRIST_API_KEY"],
    }}},
)
cursor = conn.cursor()
rows = cursor.execute('SELECT * FROM "grist://<DOC_ID>/<TABLE_ID>" LIMIT 10').fetchall()
```

## Documentation

| Document | Description |
|---|---|
| [docs/getting-started.md](docs/getting-started.md) | Prerequisites, install, step-by-step first queries |
| [docs/uri-reference.md](docs/uri-reference.md) | All `grist://` URI patterns and their column schemas |
| [docs/configuration.md](docs/configuration.md) | CLI, Python, and Superset configuration reference |
| [docs/type-mapping.md](docs/type-mapping.md) | Grist column types to SQL/Shillelagh field mapping |
| [docs/superset.md](docs/superset.md) | Apache Superset integration guide |
| [docs/limitations.md](docs/limitations.md) | Known restrictions and performance notes |

## License

MIT — see [LICENSE](LICENSE).
