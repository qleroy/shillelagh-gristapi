# shillelagh-gristapi

Shillelagh adapter for querying Grist Documents.

### Command line usage

Configuration in `~/.config/shillelagh/shillelagh.yaml`:

```yaml
gristapi:
  api_key: <replace-with-your-key>
  server: <replace-with-your-server>
  org_id: <replace-with-your-org-id>
```

- find your api_key in your profile settings,
- set server to your server url, e.g. `https://templates.getgrist.com`,
- find your org_id with the [`orgs` endpoint](https://support.getgrist.com/api/#tag/orgs/operation/listOrgs), e.g. `curl -H "Authorization: Bearer <replace-with-your-apy-key> "<replace-with-your-server>/api/orgs/" | jq '.[]|.id'`.

```bash
# List document ids
# https://support.getgrist.com/api/#tag/workspaces/operation/listWorkspaces
SELECT * FROM 'grist://';

# List table ids
# https://support.getgrist.com/api/#tag/tables/operation/listTables
SELECT * FROM 'grist://<replace-with-a-doc-id>';

# Fetch records
# https://support.getgrist.com/api/#tag/tables/operation/listTables
SELECT * FROM 'grist://<replace-with-a-doc-id>/<replace-with-a-table-id>';
```

### Python usage

```python
import os

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

# List document ids
# https://support.getgrist.com/api/#tag/workspaces/operation/listWorkspaces
query_docs = "SELECT * FROM 'grist://';"
cursor.execute(query_docs).fetchall()

# List table ids
# https://support.getgrist.com/api/#tag/tables/operation/listTables
query_tables = "SELECT * FROM 'grist://<replace-with-a-doc-id>';"
cursor.execute(query_tables).fetchall()

# Fetch records
# https://support.getgrist.com/api/#tag/tables/operation/listTables
query = "SELECT * FROM 'grist://<replace-with-a-doc-id>/<replace-with-a-table-id>';"
cursor.execute(query).fetchall()
```

### Superset usage

To make the `shillelagh-gristapi` plugin available, add the following to your `requirements-local.txt` file:

```python
shillelagh
shillelagh-gristapi
```

SqlAlchemy URI

```txt
shillelagh+safe://
```

Engine parameters

```json
{
  "connect_args":
    {
      "adapters":
        ["gristapi"],
      "adapter_kwargs":
        {
          "gristapi":{
            "api_key": "<REPLACE_WITH_YOUR_API_KEY>",
            "server": "<REPLACE_WITH_YOUR_SERVER_URL>",
            "org_id": "<REPLACE_WITH_YOUR_ORD_ID>"
          }
        }
    }
}
```

| SqlAlchemy URI | Engine parameters |
| --- | --- |
| ![screenshot base](images/screenshot_base.png)| ![screenshot parametres](images/screenshot_parametres.png) | 

| SQL Lab |
| -- |
|![screenshot sql lab](images/screenshot_sqllab.png)|