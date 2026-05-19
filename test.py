from shillelagh.backends.apsw.db import connect
import os

conn = connect(
    ":memory:",
    adapter_kwargs={"gristapi": {"grist_cfg": {
        "server": os.environ["GRIST_SERVER"],       # e.g. "https://docs.getgrist.com"
        "org_id": int(os.environ["GRIST_ORG_ID"]), # e.g. 42
        "api_key": os.environ["GRIST_API_KEY"],
    }}},
)
cursor = conn.cursor()

docs = cursor.execute('SELECT id, name FROM "grist://"').fetchall()
for doc_id, name in docs:
    print(doc_id, name)
