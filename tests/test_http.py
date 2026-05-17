"""Tests for GristClient (HTTP layer) using the responses mock library."""
import pytest
import responses as responses_lib

from shillelagh_gristapi.http import CacheConfig, ClientConfig, GristClient

BASE = "https://grist.example.com"


def make_client(cache_enabled=False, backend="memory", path=None):
    cfg = ClientConfig(
        server=BASE,
        api_key="testtoken",
        cache=CacheConfig(enabled=cache_enabled, backend=backend, path=path),
    )
    return GristClient(cfg)


# ---------------------------------------------------------------------------
# list_orgs
# ---------------------------------------------------------------------------


@responses_lib.activate
def test_list_orgs():
    responses_lib.add(
        responses_lib.GET,
        f"{BASE}/api/orgs",
        json=[{"id": 1, "name": "MyOrg", "domain": "myorg", "access": "owners"}],
    )
    client = make_client()
    result = client.list_orgs()
    assert len(list(result)) == 1
    assert list(result)[0]["name"] == "MyOrg"


@responses_lib.activate
def test_list_orgs_http_error():
    responses_lib.add(responses_lib.GET, f"{BASE}/api/orgs", status=401)
    client = make_client()
    with pytest.raises(Exception):
        client.list_orgs()


# ---------------------------------------------------------------------------
# list_workspaces
# ---------------------------------------------------------------------------


@responses_lib.activate
def test_list_workspaces():
    responses_lib.add(
        responses_lib.GET,
        f"{BASE}/api/orgs/1/workspaces",
        json=[
            {
                "id": 10,
                "name": "WS1",
                "createdAt": "2024-01-01T00:00:00.000Z",
                "updatedAt": "2024-01-01T00:00:00.000Z",
                "orgDomain": "myorg",
                "access": "owners",
                "docs": [],
            }
        ],
    )
    client = make_client()
    result = list(client.list_workspaces(1))
    assert len(result) == 1
    assert result[0]["name"] == "WS1"


# ---------------------------------------------------------------------------
# list_docs
# ---------------------------------------------------------------------------


@responses_lib.activate
def test_list_docs():
    responses_lib.add(
        responses_lib.GET,
        f"{BASE}/api/orgs/1/workspaces",
        json=[
            {
                "id": 10,
                "name": "WS1",
                "createdAt": None,
                "updatedAt": None,
                "orgDomain": "myorg",
                "access": "owners",
                "docs": [
                    {
                        "id": "docABC",
                        "name": "My Doc",
                        "createdAt": "2024-01-01T00:00:00.000Z",
                        "updatedAt": "2024-01-01T00:00:00.000Z",
                    }
                ],
            }
        ],
    )
    client = make_client()
    docs = list(client.list_docs(1))
    assert len(docs) == 1
    assert docs[0]["doc_id"] == "docABC"
    assert docs[0]["doc_name"] == "My Doc"
    assert docs[0]["workspace_id"] == 10
    assert docs[0]["org_domain"] == "myorg"


@responses_lib.activate
def test_list_docs_filtered_by_workspace():
    responses_lib.add(
        responses_lib.GET,
        f"{BASE}/api/orgs/1/workspaces",
        json=[
            {
                "id": 10,
                "name": "WS1",
                "createdAt": None,
                "updatedAt": None,
                "orgDomain": "myorg",
                "access": "owners",
                "docs": [{"id": "docA", "name": "Doc A", "createdAt": None, "updatedAt": None}],
            },
            {
                "id": 20,
                "name": "WS2",
                "createdAt": None,
                "updatedAt": None,
                "orgDomain": "myorg",
                "access": "owners",
                "docs": [{"id": "docB", "name": "Doc B", "createdAt": None, "updatedAt": None}],
            },
        ],
    )
    client = make_client()
    docs = list(client.list_docs(1, ws_id=10))
    assert len(docs) == 1
    assert docs[0]["doc_id"] == "docA"


# ---------------------------------------------------------------------------
# list_tables
# ---------------------------------------------------------------------------


@responses_lib.activate
def test_list_tables():
    responses_lib.add(
        responses_lib.GET,
        f"{BASE}/api/docs/docABC/tables",
        json={
            "tables": [
                {"id": "Contacts", "fields": {"primaryViewId": 1, "tableRef": 5}},
                {"id": "Orders", "fields": {"primaryViewId": 2, "tableRef": 6}},
            ]
        },
    )
    client = make_client()
    tables = list(client.list_tables("docABC"))
    assert len(tables) == 2
    assert tables[0]["id"] == "Contacts"


# ---------------------------------------------------------------------------
# list_columns
# ---------------------------------------------------------------------------


@responses_lib.activate
def test_list_columns():
    responses_lib.add(
        responses_lib.GET,
        f"{BASE}/api/docs/docABC/tables/Contacts/columns",
        json={
            "columns": [
                {"id": "Name", "fields": {"type": "Text", "colRef": 1}},
                {"id": "Age", "fields": {"type": "Int", "colRef": 2}},
            ]
        },
    )
    client = make_client()
    cols = list(client.list_columns("docABC", "Contacts"))
    assert len(cols) == 2
    assert cols[0]["id"] == "Name"
    assert cols[1]["fields"]["type"] == "Int"


# ---------------------------------------------------------------------------
# iter_records
# ---------------------------------------------------------------------------


@responses_lib.activate
def test_iter_records_basic():
    responses_lib.add(
        responses_lib.GET,
        f"{BASE}/api/docs/docABC/tables/Contacts/records",
        json={
            "records": [
                {"id": 1, "fields": {"Name": "Alice", "Age": 30}},
                {"id": 2, "fields": {"Name": "Bob", "Age": 25}},
            ]
        },
    )
    client = make_client()
    rows = list(client.iter_records("docABC", "Contacts"))
    assert len(rows) == 2
    assert rows[0]["Name"] == "Alice"
    assert rows[0]["id"] == 1
    assert rows[1]["Age"] == 25


@responses_lib.activate
def test_iter_records_empty():
    responses_lib.add(
        responses_lib.GET,
        f"{BASE}/api/docs/docABC/tables/Empty/records",
        json={"records": []},
    )
    client = make_client()
    rows = list(client.iter_records("docABC", "Empty"))
    assert rows == []


@responses_lib.activate
def test_iter_records_with_filter():
    responses_lib.add(
        responses_lib.GET,
        f"{BASE}/api/docs/docABC/tables/Contacts/records",
        json={"records": [{"id": 1, "fields": {"Name": "Alice"}}]},
    )
    client = make_client()
    rows = list(
        client.iter_records("docABC", "Contacts", params={"filter": '{"Name":["Alice"]}'})
    )
    assert len(rows) == 1
    # verify the filter param was sent
    assert "filter" in responses_lib.calls[0].request.url


# ---------------------------------------------------------------------------
# Caching behavior
# ---------------------------------------------------------------------------


@responses_lib.activate
def test_list_orgs_cached_on_second_call():
    responses_lib.add(
        responses_lib.GET,
        f"{BASE}/api/orgs",
        json=[{"id": 1, "name": "Org1"}],
    )
    client = make_client(cache_enabled=True, backend="memory")
    client.list_orgs()
    client.list_orgs()  # should hit cache, not network
    assert len(responses_lib.calls) == 1


@responses_lib.activate
def test_cache_cleared_then_refetched():
    responses_lib.add(
        responses_lib.GET,
        f"{BASE}/api/orgs",
        json=[{"id": 1, "name": "Org1"}],
    )
    responses_lib.add(
        responses_lib.GET,
        f"{BASE}/api/orgs",
        json=[{"id": 1, "name": "Org1"}],
    )
    client = make_client(cache_enabled=True, backend="memory")
    client.list_orgs()
    client.clear_cache()
    client.list_orgs()
    assert len(responses_lib.calls) == 2


# ---------------------------------------------------------------------------
# Authorization header
# ---------------------------------------------------------------------------


@responses_lib.activate
def test_authorization_header_sent():
    responses_lib.add(responses_lib.GET, f"{BASE}/api/orgs", json=[])
    client = make_client()
    client.list_orgs()
    assert responses_lib.calls[0].request.headers["Authorization"] == "Bearer testtoken"


# ---------------------------------------------------------------------------
# Server URL trailing slash stripped
# ---------------------------------------------------------------------------


@responses_lib.activate
def test_trailing_slash_stripped():
    responses_lib.add(responses_lib.GET, f"{BASE}/api/orgs", json=[])
    cfg = ClientConfig(
        server=f"{BASE}/",  # trailing slash
        api_key="testtoken",
        cache=CacheConfig(enabled=False),
    )
    client = GristClient(cfg)
    client.list_orgs()
    assert responses_lib.calls[0].request.url.startswith(BASE + "/api")
