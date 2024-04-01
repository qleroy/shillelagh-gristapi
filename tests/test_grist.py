import os
from collections import defaultdict
from importlib.metadata import entry_points

from shillelagh.backends.apsw.db import connect


connection = connect(
    ":memory:",
    adapter_kwargs={
        "gristapi": {
            "api_key": os.environ["GRIST_API_KEY"],
            "server": os.environ["GRIST_SERVER"],
            "org_id": os.environ["GRIST_ORG_ID"],
        }
    },
)
cursor = connection.cursor()


def test_shillelagh_gristapi_adapter_exists():
    loaders = defaultdict(list)

    for entry_point in entry_points(group="shillelagh.adapter"):
        loaders[entry_point.name].append(entry_point.load)

    assert "gristapi" in loaders.keys()


def test_shillelagh_gristapi_adapter_loads():
    loaders = defaultdict(list)

    for entry_point in entry_points(group="shillelagh.adapter"):
        loaders[entry_point.name].append(entry_point.load)
    for load in loaders["gristapi"]:
        assert load()


def test_fetch_docs_id():
    query = """
    select * from "grist://"
    """

    results = cursor.execute(query).fetchall()
    assert len(results) > 0


def test_fetch_table_ids():
    query_2 = f"""
    SELECT * FROM "grist://{os.environ['GRIST_DOC_ID']}"
    """

    results_2 = cursor.execute(query_2).fetchall()

    assert len(results_2) > 0


def test_fetch_data():
    query_3 = f"""
    SELECT * 
    FROM "grist://{os.environ['GRIST_DOC_ID']}/{os.environ['GRIST_TABLE_ID']}"
    """

    results_3 = cursor.execute(query_3).fetchall()

    assert len(results_3) > 0
