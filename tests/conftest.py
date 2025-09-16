import os
import pytest


@pytest.fixture(autouse=True)
def _env_defaults(monkeypatch):
    # Keep network calls out of tests unless mocked
    monkeypatch.setenv("NO_PROXY", "*")
    monkeypatch.setenv("GRIST_SERVER", "https://docs.getgrist.com")
    yield
