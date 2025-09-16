from __future__ import annotations

import json
import sqlite3
from typing import Dict

import pytest
import responses


def _open_conn():
    # Use shillelagh in sqlite3 by loading the extension and opening a "db URI"
    con = sqlite3.connect(":memory:")
    con.enable_load_extension(True)
    try:
        con.load_extension("shillelagh")  # On some systems: .load shillelagh inside CLI
    except sqlite3.OperationalError:
        # Some environments require URI open; tests will not actually execute sqlite extension load.
        pass
    return con


def _db_uri(adapter_kwargs: Dict) -> str:
    # Classic Shillelagh SQLAlchemy-style URIs use sqlite; for sqlite3 module we pass a URI string when needed.
    # Here we only test adapter behavior by importing the table names with quotes.
    kw = json.dumps({"gristapi": adapter_kwargs})
    return f"shillelagh+safe://?adapters=gristapi&adapter_kwargs={kw}"


@responses.activate
def test_list_docs_and_tables(monkeypatch):
    # Mock endpoints
    server = "https://docs.getgrist.com"
    responses.add(
        responses.GET,
        f"{server}/api/docs",
        json={"docs": [{"id": "D1", "name": "Demo Doc"}]},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{server}/api/docs/D1/tables",
        json={"tables": [{"id": "T1", "name": "Expenses", "columns": []}]},
        status=200,
    )

    # Build a query that hits the listing URIs
    # We don't actually use sqlite3 execution here (since .load extension varies),
    # we call the adapter through SQL string semantics: SELECT * FROM "grist://...";
    # In a real integration test you'd use Shillelagh's Python API to open the virtual table.
    from shillelagh.backends.apsw.db import connect  # Shillelagh's own connector

    uri = _db_uri({"api_key": "XYZ", "server": server})
    con = connect(uri)
    cur = con.cursor()

    rows = list(cur.execute('SELECT id, name FROM "grist://";'))
    assert rows == [("D1", "Demo Doc")]

    rows = list(cur.execute('SELECT id, name FROM "grist://D1";'))
    assert rows == [("T1", "Expenses")]


@responses.activate
def test_records_with_pushdown_and_limit():
    server = "https://docs.getgrist.com"

    # Table schema discovery:
    responses.add(
        responses.GET,
        f"{server}/api/docs/D1/tables",
        json={
            "tables": [
                {
                    "id": "Expenses",
                    "name": "Expenses",
                    "columns": [
                        {"id": "name", "name": "name", "type": "text"},
                        {"id": "amount", "name": "amount", "type": "numeric"},
                    ],
                }
            ]
        },
        status=200,
    )

    # First page of records:
    def _records(match_request):
        # Assert pushdown params came through (limit + filter + sort)
        qs = match_request.qs
        # Example: limit=5, filter[name]=Alice, sort[0][col]=amount ...
        assert "limit" in qs and qs["limit"] == ["5"]
        assert (
            "filter[name]" in qs or "filter" in qs
        )  # depending on your param encoding
        return (
            200,
            {},
            json.dumps(
                {
                    "records": [
                        {"id": 1, "fields": {"name": "Alice", "amount": 120.0}},
                        {"id": 2, "fields": {"name": "Alice", "amount": 110.0}},
                    ]
                }
            ),
        )

    responses.add_callback(
        responses.GET,
        f"{server}/api/docs/D1/tables/Expenses/records",
        callback=_records,
        content_type="application/json",
    )

    from shillelagh.backends.apsw.db import connect

    uri = f'shillelagh+safe://?adapters=gristapi&adapter_kwargs={json.dumps({"gristapi": {"api_key": "XYZ", "server": server}})}'
    con = connect(uri)
    cur = con.cursor()

    # WHERE, ORDER, LIMIT pushdown
    q = (
        'SELECT name, amount FROM "grist://D1/Expenses" '
        "WHERE name = 'Alice' ORDER BY amount DESC LIMIT 5"
    )
    rows = list(cur.execute(q))
    assert len(rows) == 2
    assert rows[0][0] == "Alice"
