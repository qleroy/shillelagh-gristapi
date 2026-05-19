# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**shillelagh-gristapi** is a [Shillelagh](https://github.com/betodealmeida/shillelagh) adapter that exposes Grist (a spreadsheet-database platform) tables as SQL-queryable resources via SQLite/SQLAlchemy. This enables BI tools like Apache Superset to query Grist data with SQL.

## Commands

```bash
# Install with dev dependencies
pip install -e .[dev]

# Run all tests
pytest -q --cov=shillelagh_gristapi --cov-report=term-missing

# Run a single test
pytest tests/test_adapter.py::test_name -v

# Lint and format
ruff check .
ruff format .

# Type checking
mypy .
```

Pre-commit hooks run ruff and mypy automatically on commit.

## Architecture

All source code lives in `src/shillelagh_gristapi/`:

- **`adapter.py`** — Core `GristAPIAdapter` class implementing Shillelagh's `Adapter` interface. Handles URI parsing, schema discovery, row fetching, and filter/sort pushdown to the Grist REST API.
- **`http.py`** — `GristClient`: authenticated HTTP client for Grist REST API calls with optional caching.
- **`cache.py`** — Two cache backends: `MemoryCache` (TTL+LRU in-process) and `SQLiteCache` (persistent, WAL mode).
- **`schema.py`** — Maps Grist column types to Shillelagh field types.

### URI scheme

The adapter handles a `grist://` URI scheme with several modes:

| URI pattern | Returns |
|---|---|
| `grist://` | list of documents (`__docs__`) |
| `grist://<doc_id>` | list of tables in a document |
| `grist://<doc_id>/<table_id>` | rows from that table |
| `grist://__orgs__` | list of organizations |
| `grist://<doc_id>/__columns__` | column metadata |

### Filter/sort pushdown

- Equality filters → JSON filter parameter on Grist API
- Sorting → comma-separated sort string (prefix `-` for descending)
- LIMIT → passed directly to API
- Unsupported filters fall back to local evaluation

### Caching

- Metadata (orgs, workspaces, docs, tables, columns): cached 300s
- Records: cached 60s (configurable, can be disabled)
- Cache backend: memory (default) or SQLite (set via `cache_dir`)

### Type mapping

`schema.py` maps Grist types to Shillelagh fields. `Reference` and `ReferenceList` are custom text-based fields that resolve display column values. Unmapped types fall back to `StringField`.
