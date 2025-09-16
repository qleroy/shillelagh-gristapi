# tests/test_adapter.py
import pytest
from shillelagh.adapters.registry import load_adapter  # if you use registry

# or import your adapter directly


def test_supports_workspace_uri():
    # 'grist://' should be supported for listing docs
    ...


def test_fetch_records_with_filters(mock_grist_api):
    # assert adapter translates WHERE/ORDER/LIMIT into API params
    ...
