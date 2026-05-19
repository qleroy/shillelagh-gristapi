import pytest

from shillelagh_gristapi.adapter import GristAPIAdapter, ResourceKind

pytestmark = pytest.mark.integration


class TestOrganizations:
    def test_list_orgs(self, grist_credentials):
        adapter = GristAPIAdapter(
            resource_kind=ResourceKind.ORGS,
            doc_id=None,
            table_id=None,
            query_params={},
            grist_cfg={
                "server": grist_credentials["server"],
                "org_id": grist_credentials["org_id"],
                "api_key": grist_credentials["api_key"],
            },
            cache_cfg={"enabled": False},
        )
        columns = adapter.get_columns()
        assert "id" in columns
        assert "name" in columns


class TestDocuments:
    def test_list_docs(self, grist_credentials):
        adapter = GristAPIAdapter(
            resource_kind=ResourceKind.DOCS,
            doc_id=None,
            table_id=None,
            query_params={},
            grist_cfg={
                "server": grist_credentials["server"],
                "org_id": grist_credentials["org_id"],
                "api_key": grist_credentials["api_key"],
            },
            cache_cfg={"enabled": False},
        )
        columns = adapter.get_columns()
        assert "id" in columns
        assert "name" in columns


class TestTables:
    def test_list_tables(self, grist_credentials, test_doc_id):
        if not test_doc_id:
            pytest.skip("GRIST_DOC_ID not set")
        adapter = GristAPIAdapter(
            resource_kind=ResourceKind.TABLES,
            doc_id=test_doc_id,
            table_id=None,
            query_params={},
            grist_cfg={
                "server": grist_credentials["server"],
                "org_id": grist_credentials["org_id"],
                "api_key": grist_credentials["api_key"],
            },
            cache_cfg={"enabled": False},
        )
        columns = adapter.get_columns()
        assert "id" in columns


class TestColumns:
    def test_columns(self, grist_credentials, test_doc_id):
        if not test_doc_id:
            pytest.skip("GRIST_DOC_ID not set")
        adapter = GristAPIAdapter(
            resource_kind=ResourceKind.COLUMNS,
            doc_id=test_doc_id,
            table_id=None,
            query_params={},
            grist_cfg={
                "server": grist_credentials["server"],
                "org_id": grist_credentials["org_id"],
                "api_key": grist_credentials["api_key"],
            },
            cache_cfg={"enabled": False},
        )
        columns = adapter.get_columns()
        assert "id" in columns
        assert "type" in columns


class TestRecords:
    def test_fetch_records(self, grist_credentials, test_doc_id):
        if not test_doc_id:
            pytest.skip("GRIST_DOC_ID not set")
        adapter = GristAPIAdapter(
            resource_kind=ResourceKind.TABLES,
            doc_id=test_doc_id,
            table_id=None,
            query_params={},
            grist_cfg={
                "server": grist_credentials["server"],
                "org_id": grist_credentials["org_id"],
                "api_key": grist_credentials["api_key"],
            },
            cache_cfg={"enabled": False},
        )
        columns = adapter.get_columns()
        assert len(columns) > 0
