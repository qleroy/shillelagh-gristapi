import os
import pathlib

import pytest

try:
    from dotenv import load_dotenv

    load_dotenv(pathlib.Path(__file__).parent.parent / ".env")
except ImportError:
    pass


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: marks tests as integration (deselect with '-m \"not integration\"')",
    )


@pytest.fixture(scope="session")
def grist_credentials():
    api_key = os.environ.get("GRIST_API_KEY")
    org_id = os.environ.get("GRIST_ORG_ID")
    server = os.environ.get("GRIST_SERVER", "https://docs.getgrist.com")

    if not api_key or not org_id:
        pytest.skip("GRIST_API_KEY and GRIST_ORG_ID must be set")

    return {
        "api_key": api_key,
        "org_id": org_id,
        "server": server,
    }


@pytest.fixture(scope="session")
def test_doc_id():
    return os.environ.get("GRIST_DOC_ID")


@pytest.fixture
def integration_adapter(grist_credentials, test_doc_id):
    from shillelagh_gristapi.adapter import GristAPIAdapter, ResourceKind

    return GristAPIAdapter(
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


@pytest.fixture
def integration_adapter_with_cache(grist_credentials, test_doc_id, tmp_path):
    from shillelagh_gristapi.adapter import GristAPIAdapter, ResourceKind

    return GristAPIAdapter(
        resource_kind=ResourceKind.TABLES,
        doc_id=test_doc_id,
        table_id=None,
        query_params={},
        grist_cfg={
            "server": grist_credentials["server"],
            "org_id": grist_credentials["org_id"],
            "api_key": grist_credentials["api_key"],
        },
        cache_cfg={
            "enabled": True,
            "backend": "memory",
            "maxsize": 100,
        },
    )
