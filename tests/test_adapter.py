"""Tests for GristAPIAdapter."""
import datetime
import json
from unittest.mock import MagicMock

import pytest
from shillelagh.exceptions import ProgrammingError
from shillelagh.fields import Boolean, DateTime, Float, Integer, String

from shillelagh_gristapi.adapter import GristAPIAdapter, ResourceKind, _parse_dt
from shillelagh_gristapi.schema import Reference, ReferenceList

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

GRIST_CFG = {"server": "https://grist.example.com", "org_id": 1, "api_key": "testkey"}


def make_adapter(
    tmp_path,
    resource_kind=ResourceKind.RECORDS,
    doc_id=None,
    table_id=None,
    **kwargs,
):
    adapter = GristAPIAdapter(
        resource_kind=resource_kind,
        doc_id=doc_id,
        table_id=table_id,
        query_params={},
        grist_cfg=GRIST_CFG,
        cache_cfg={"backend": "memory"},
        cachepath=str(tmp_path),
        **kwargs,
    )
    adapter.client = MagicMock()
    return adapter


# ---------------------------------------------------------------------------
# _parse_dt
# ---------------------------------------------------------------------------


class TestParseDt:
    def test_none_returns_none(self):
        assert _parse_dt(None) is None

    def test_empty_string_returns_none(self):
        assert _parse_dt("") is None

    def test_int_unix_timestamp(self):
        result = _parse_dt(0)
        assert isinstance(result, datetime.datetime)
        assert result.tzinfo == datetime.timezone.utc

    def test_iso_string(self):
        result = _parse_dt("2024-06-15T12:30:00.000Z")
        assert isinstance(result, datetime.datetime)
        assert result.year == 2024
        assert result.month == 6
        assert result.day == 15
        assert result.tzinfo == datetime.timezone.utc


# ---------------------------------------------------------------------------
# parse_uri
# ---------------------------------------------------------------------------


class TestParseUri:
    def test_root_listing(self):
        kind, doc_id, table_id, _ = GristAPIAdapter.parse_uri("grist://")
        assert kind is ResourceKind.DOCS
        assert doc_id is None
        assert table_id is None

    def test_orgs(self):
        kind, doc_id, table_id, _ = GristAPIAdapter.parse_uri("grist://__orgs__")
        assert kind is ResourceKind.ORGS
        assert doc_id is None
        assert table_id is None

    def test_workspaces(self):
        kind, doc_id, table_id, _ = GristAPIAdapter.parse_uri("grist://__workspaces__")
        assert kind is ResourceKind.WORKSPACES
        assert doc_id is None
        assert table_id is None

    def test_docs_alias(self):
        kind, doc_id, table_id, _ = GristAPIAdapter.parse_uri("grist://__docs__")
        assert kind is ResourceKind.DOCS
        assert doc_id is None
        assert table_id is None

    def test_doc_only(self):
        kind, doc_id, table_id, _ = GristAPIAdapter.parse_uri("grist://docABC123")
        assert kind is ResourceKind.TABLES
        assert doc_id == "docABC123"
        assert table_id is None

    def test_doc_and_table(self):
        kind, doc_id, table_id, _ = GristAPIAdapter.parse_uri("grist://docABC123/MyTable")
        assert kind is ResourceKind.RECORDS
        assert doc_id == "docABC123"
        assert table_id == "MyTable"

    def test_columns_subresource(self):
        kind, doc_id, table_id, _ = GristAPIAdapter.parse_uri(
            "grist://docABC123/MyTable/__columns__"
        )
        assert kind is ResourceKind.COLUMNS
        assert doc_id == "docABC123"
        assert table_id == "MyTable"

    def test_workspace_scoped_docs(self):
        kind, doc_id, table_id, _ = GristAPIAdapter.parse_uri("grist://ws42/__docs__")
        assert kind is ResourceKind.DOCS
        assert doc_id == "ws42"
        assert table_id is None

    def test_query_params_parsed(self):
        _, _, _, qp = GristAPIAdapter.parse_uri("grist://docABC123?limit=10&sort=name")
        assert qp["limit"] == ["10"]
        assert qp["sort"] == ["name"]

    def test_supports_grist_scheme(self):
        assert GristAPIAdapter.supports("grist://anything")

    def test_supports_rejects_other_schemes(self):
        assert not GristAPIAdapter.supports("https://other.com")


# ---------------------------------------------------------------------------
# _order_to_sort_string
# ---------------------------------------------------------------------------


class MockOrder:
    def __init__(self, name: str):
        self.name = name


ASC = MockOrder("ASCENDING")
DESC = MockOrder("DESCENDING")


class TestOrderToSortString:
    def test_empty_order_returns_none(self):
        assert GristAPIAdapter._order_to_sort_string([]) is None

    def test_single_asc(self):
        assert GristAPIAdapter._order_to_sort_string([("name", ASC)]) == "name"

    def test_single_desc(self):
        assert GristAPIAdapter._order_to_sort_string([("age", DESC)]) == "-age"

    def test_multi_column(self):
        result = GristAPIAdapter._order_to_sort_string(
            [("pet", ASC), ("age", DESC), ("name", ASC)]
        )
        assert result == "pet,-age,name"


# ---------------------------------------------------------------------------
# _build_records_params
# ---------------------------------------------------------------------------


class TestBuildRecordsParams:
    def test_empty(self):
        params = GristAPIAdapter._build_records_params({}, [], None)
        assert params == {}

    def test_equal_filter(self):
        from shillelagh.filters import Equal

        params = GristAPIAdapter._build_records_params(
            {"country": Equal("FR")}, [], None
        )
        assert json.loads(params["filter"]) == {"country": ["FR"]}

    def test_sort_pushed(self):
        params = GristAPIAdapter._build_records_params({}, [("name", ASC)], None)
        assert params["sort"] == "name"

    def test_limit_pushed(self):
        params = GristAPIAdapter._build_records_params({}, [], 50)
        assert params["limit"] == 50

    def test_all_together(self):
        from shillelagh.filters import Equal

        params = GristAPIAdapter._build_records_params(
            {"status": Equal("active")}, [("id", DESC)], 10
        )
        assert json.loads(params["filter"]) == {"status": ["active"]}
        assert params["sort"] == "-id"
        assert params["limit"] == 10

    def test_isin_single_value(self):
        from shillelagh_gristapi.schema import IsIn

        params = GristAPIAdapter._build_records_params(
            {"country": IsIn(["FR"])}, [], None
        )
        assert json.loads(params["filter"]) == {"country": ["FR"]}

    def test_isin_multiple_values(self):
        from shillelagh_gristapi.schema import IsIn

        params = GristAPIAdapter._build_records_params(
            {"country": IsIn(["FR", "DE", "ES"])}, [], None
        )
        assert json.loads(params["filter"]) == {"country": ["FR", "DE", "ES"]}

    def test_isin_multiple_columns(self):
        from shillelagh_gristapi.schema import IsIn

        params = GristAPIAdapter._build_records_params(
            {"status": IsIn(["active", "pending"]), "region": IsIn(["EU"])}, [], None
        )
        f = json.loads(params["filter"])
        assert set(f["status"]) == {"active", "pending"}
        assert f["region"] == ["EU"]

    def test_unsupported_filter_raises(self):
        from shillelagh.filters import Filter

        class FakeFilter(Filter):
            pass

        with pytest.raises(ProgrammingError, match="Unsupported filter"):
            GristAPIAdapter._build_records_params({"col": FakeFilter()}, [], None)


# ---------------------------------------------------------------------------
# get_columns — synthetic schemas
# ---------------------------------------------------------------------------


class TestGetColumnsSynthetic:
    def test_orgs_schema(self, tmp_path):
        adapter = make_adapter(tmp_path, ResourceKind.ORGS)
        cols = adapter.get_columns()
        assert set(cols) == {"id", "name", "createdAt", "updatedAt", "domain", "access"}

    def test_workspaces_schema(self, tmp_path):
        adapter = make_adapter(tmp_path, ResourceKind.WORKSPACES)
        cols = adapter.get_columns()
        assert "id" in cols
        assert "name" in cols
        assert "orgDomain" in cols

    def test_docs_schema_root(self, tmp_path):
        adapter = make_adapter(tmp_path, ResourceKind.DOCS)
        cols = adapter.get_columns()
        assert "id" in cols
        assert "workspaceId" in cols
        assert "orgDomain" in cols

    def test_columns_schema(self, tmp_path):
        adapter = make_adapter(
            tmp_path, ResourceKind.COLUMNS, doc_id="docXYZ", table_id="MyTable"
        )
        cols = adapter.get_columns()
        assert "id" in cols
        assert "type" in cols
        assert "isFormula" in cols

    def test_tables_schema(self, tmp_path):
        adapter = make_adapter(tmp_path, ResourceKind.TABLES, doc_id="docXYZ")
        cols = adapter.get_columns()
        assert "id" in cols
        assert "primaryViewId" in cols

    def test_real_table_schema_from_client(self, tmp_path):
        adapter = make_adapter(
            tmp_path, ResourceKind.RECORDS, doc_id="docXYZ", table_id="Contacts"
        )
        adapter.client.list_columns.return_value = [
            {"id": "Name", "fields": {"type": "Text", "colRef": 1, "displayCol": 0}},
            {"id": "Age", "fields": {"type": "Int", "colRef": 2, "displayCol": 0}},
        ]
        cols = adapter.get_columns()
        assert isinstance(cols["Name"], String)
        assert isinstance(cols["Age"], Integer)
        assert "id" in cols  # synthetic id field added

    def test_real_table_schema_cached(self, tmp_path):
        adapter = make_adapter(
            tmp_path, ResourceKind.RECORDS, doc_id="docXYZ", table_id="Contacts"
        )
        adapter.client.list_columns.return_value = [
            {"id": "Name", "fields": {"type": "Text", "colRef": 1, "displayCol": 0}},
        ]
        adapter.get_columns()
        adapter.get_columns()
        adapter.client.list_columns.assert_called_once()

    def test_real_table_no_columns_raises(self, tmp_path):
        adapter = make_adapter(
            tmp_path, ResourceKind.RECORDS, doc_id="docXYZ", table_id="Empty"
        )
        adapter.client.list_columns.return_value = []
        with pytest.raises(ProgrammingError, match="no columns"):
            adapter.get_columns()


# ---------------------------------------------------------------------------
# get_rows — synthetic resources
# ---------------------------------------------------------------------------


class TestGetRowsSynthetic:
    def test_get_rows_orgs(self, tmp_path):
        adapter = make_adapter(tmp_path, ResourceKind.ORGS)
        adapter.client.list_orgs.return_value = [
            {
                "id": 1,
                "name": "MyOrg",
                "createdAt": None,
                "updatedAt": None,
                "domain": "myorg",
                "access": "owners",
            }
        ]
        rows = list(adapter.get_rows({}, []))
        assert len(rows) == 1
        assert rows[0]["name"] == "MyOrg"
        assert rows[0]["domain"] == "myorg"

    def test_get_rows_workspaces(self, tmp_path):
        adapter = make_adapter(tmp_path, ResourceKind.WORKSPACES)
        adapter.client.list_workspaces.return_value = [
            {
                "id": 10,
                "name": "WS1",
                "createdAt": None,
                "updatedAt": None,
                "orgDomain": "myorg",
                "access": "owners",
            }
        ]
        rows = list(adapter.get_rows({}, []))
        assert rows[0]["name"] == "WS1"
        assert rows[0]["orgDomain"] == "myorg"

    def test_get_rows_docs_root(self, tmp_path):
        adapter = make_adapter(tmp_path, ResourceKind.DOCS)
        adapter.client.list_docs.return_value = [
            {
                "doc_id": "doc1",
                "doc_name": "My Doc",
                "doc_created_at": None,
                "doc_updated_at": None,
                "workspace_id": 10,
                "workspace_name": "WS1",
                "workspace_access": "owners",
                "org_domain": "myorg",
            }
        ]
        rows = list(adapter.get_rows({}, []))
        assert rows[0]["id"] == "doc1"
        assert rows[0]["name"] == "My Doc"
        assert rows[0]["orgDomain"] == "myorg"

    def test_get_rows_tables(self, tmp_path):
        adapter = make_adapter(tmp_path, ResourceKind.TABLES, doc_id="docXYZ")
        adapter.client.list_tables.return_value = [
            {
                "id": "Contacts",
                "fields": {
                    "primaryViewId": 1,
                    "summarySourceTable": 0,
                    "onDemand": False,
                    "rawViewSectionRef": 2,
                    "recordCardViewSectionRef": 3,
                    "tableRef": 10,
                },
            }
        ]
        rows = list(adapter.get_rows({}, []))
        assert rows[0]["id"] == "Contacts"
        assert rows[0]["primaryViewId"] == 1

    def test_get_rows_columns(self, tmp_path):
        adapter = make_adapter(
            tmp_path, ResourceKind.COLUMNS, doc_id="docXYZ", table_id="Contacts"
        )
        adapter.client.list_columns.return_value = [
            {
                "id": "Name",
                "fields": {
                    "type": "Text",
                    "colRef": 1,
                    "parentId": 1,
                    "parentPos": 1.0,
                    "isFormula": False,
                    "formula": "",
                    "label": "Name",
                    "description": "",
                    "untieColIdFromLabel": False,
                    "summarySourceCol": 0,
                    "displayCol": 0,
                    "visibleCol": None,
                    "reverseCol": 0,
                    "recalcWhen": 0,
                },
            }
        ]
        rows = list(adapter.get_rows({}, []))
        assert rows[0]["id"] == "Name"
        assert rows[0]["type"] == "Text"

    def test_get_rows_table_records(self, tmp_path):
        adapter = make_adapter(
            tmp_path, ResourceKind.RECORDS, doc_id="docXYZ", table_id="Contacts"
        )
        adapter.client.list_columns.return_value = [
            {"id": "Name", "fields": {"type": "Text", "colRef": 1, "displayCol": 0}},
            {"id": "Age", "fields": {"type": "Int", "colRef": 2, "displayCol": 0}},
        ]
        adapter.client.iter_records.return_value = [
            {"id": 1, "Name": "Alice", "Age": 30},
            {"id": 2, "Name": "Bob", "Age": 25},
        ]
        rows = list(adapter.get_rows({}, []))
        assert len(rows) == 2
        assert rows[0]["Name"] == "Alice"
        assert rows[1]["Age"] == 25

    def test_get_rows_client_error_raises_programming_error(self, tmp_path):
        adapter = make_adapter(tmp_path, ResourceKind.ORGS)
        adapter.client.list_orgs.side_effect = RuntimeError("Network error")
        with pytest.raises(ProgrammingError, match="list_orgs"):
            list(adapter.get_rows({}, []))


# ---------------------------------------------------------------------------
# _row_to_python
# ---------------------------------------------------------------------------


class TestRowToPython:
    def _make_adapter_with_columns(self, tmp_path, columns, display_map=None):
        adapter = make_adapter(
            tmp_path, ResourceKind.RECORDS, doc_id="docXYZ", table_id="T"
        )
        adapter._columns = columns
        adapter._field_to_displayed_col_id = display_map or {}
        return adapter

    def test_plain_string(self, tmp_path):
        adapter = self._make_adapter_with_columns(tmp_path, {"Name": String()})
        result = adapter._row_to_python({"Name": "Alice"})
        assert result["Name"] == "Alice"

    def test_none_value(self, tmp_path):
        adapter = self._make_adapter_with_columns(tmp_path, {"Name": String()})
        result = adapter._row_to_python({"Name": None})
        assert result["Name"] is None

    def test_datetime_from_int(self, tmp_path):
        adapter = self._make_adapter_with_columns(tmp_path, {"ts": DateTime()})
        result = adapter._row_to_python({"ts": 0})
        assert isinstance(result["ts"], datetime.datetime)

    def test_datetime_from_iso_string(self, tmp_path):
        adapter = self._make_adapter_with_columns(tmp_path, {"ts": DateTime()})
        result = adapter._row_to_python({"ts": "2024-01-01T00:00:00.000Z"})
        assert isinstance(result["ts"], datetime.datetime)

    def test_list_value_strips_sentinel(self, tmp_path):
        adapter = self._make_adapter_with_columns(tmp_path, {"tags": String()})
        result = adapter._row_to_python({"tags": ["L", "tag1", "tag2"]})
        assert result["tags"] == "tag1,tag2"

    def test_list_sentinel_only_returns_none(self, tmp_path):
        adapter = self._make_adapter_with_columns(tmp_path, {"tags": String()})
        result = adapter._row_to_python({"tags": ["L"]})
        assert result["tags"] is None

    def test_reference_uses_display_col(self, tmp_path):
        adapter = self._make_adapter_with_columns(
            tmp_path,
            {"Owner": Reference()},
            display_map={"Owner": "gristHelper_Display_Owner"},
        )
        result = adapter._row_to_python(
            {"Owner": 5, "gristHelper_Display_Owner": ["L", "Alice"]}
        )
        assert result["Owner"] == "Alice"

    def test_reference_falls_back_to_raw_when_no_display(self, tmp_path):
        adapter = self._make_adapter_with_columns(tmp_path, {"Owner": Reference()})
        result = adapter._row_to_python({"Owner": ["L", "Bob"]})
        assert result["Owner"] == "Bob"

    def test_missing_column_in_row_returns_none(self, tmp_path):
        adapter = self._make_adapter_with_columns(
            tmp_path, {"Name": String(), "Age": Integer()}
        )
        result = adapter._row_to_python({"Name": "Alice"})
        assert result["Name"] == "Alice"
        assert result["Age"] is None


# ---------------------------------------------------------------------------
# Constructor validation
# ---------------------------------------------------------------------------


class TestAdapterInit:
    def test_missing_server_raises(self, tmp_path):
        with pytest.raises(ProgrammingError, match="server"):
            GristAPIAdapter(
                resource_kind=ResourceKind.DOCS,
                doc_id=None,
                table_id=None,
                query_params={},
                grist_cfg={"server": "", "org_id": 1, "api_key": "k"},
                cache_cfg={"backend": "memory"},
                cachepath=str(tmp_path),
            )

    def test_missing_api_key_raises(self, tmp_path):
        with pytest.raises(ProgrammingError, match="API key"):
            GristAPIAdapter(
                resource_kind=ResourceKind.DOCS,
                doc_id=None,
                table_id=None,
                query_params={},
                grist_cfg={"server": "https://x.com", "org_id": 1, "api_key": ""},
                cache_cfg={"backend": "memory"},
                cachepath=str(tmp_path),
            )

    def test_invalid_org_id_raises(self, tmp_path):
        with pytest.raises(ProgrammingError, match="integer"):
            GristAPIAdapter(
                resource_kind=ResourceKind.DOCS,
                doc_id=None,
                table_id=None,
                query_params={},
                grist_cfg={
                    "server": "https://x.com",
                    "org_id": "not-a-number",
                    "api_key": "k",
                },
                cache_cfg={"backend": "memory"},
                cachepath=str(tmp_path),
            )

    def test_legacy_params_accepted(self, tmp_path):
        adapter = GristAPIAdapter(
            resource_kind=ResourceKind.DOCS,
            doc_id=None,
            table_id=None,
            query_params={},
            server="https://grist.example.com",
            org_id=1,
            api_key="testkey",
            cache_cfg={"backend": "memory"},
            cachepath=str(tmp_path),
        )
        assert adapter.state.server == "https://grist.example.com"

    def test_invalid_filename_raises(self, tmp_path):
        with pytest.raises(ValueError, match="filename"):
            GristAPIAdapter(
                resource_kind=ResourceKind.DOCS,
                doc_id=None,
                table_id=None,
                query_params={},
                grist_cfg=GRIST_CFG,
                cache_cfg={"backend": "sqlite", "filename": "subdir/cache.sqlite"},
                cachepath=str(tmp_path),
            )
