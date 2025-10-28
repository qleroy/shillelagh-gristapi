# 📊 Apache Superset

You can use **Shillelagh + GristAPIAdapter** directly inside **Apache Superset** to query your Grist workspaces as virtual datasets.

---

## 1️⃣ Install dependencies in your Superset image

Add both `shillelagh` and this adapter to your Superset Docker image or virtualenv:

```bash
pip install shillelagh shillelagh-gristapi
```

---

## 2️⃣ Create a new database connection

In **Superset → Settings → Database Connections → + Database**, choose **"Shillelagh"**, 
enter a name a **Display Name** like **"docs.getgrist.com"**,
and set the **SQLAlchemy URI** to:

```
shillelagh+safe://
```

> Use `shillelagh+safe://` instead of `shillelagh://` to enable only trusted adapters.

---

## 3️⃣ Configure the Engine Parameters

In the **"Advanced → Other → Engine Parameters"** field, paste:

```json
{
  "connect_args": {
    "adapters": ["gristapi"],
    "adapter_kwargs": {
      "gristapi": {
        "grist_cfg": {
          "api_key": "<REPLACE_WITH_YOUR_API_KEY>",
          "org_id": "<REPLACE_WITH_YOUR_ORG_ID>",
          "server": "<REPLACE_WITH_YOUR_SERVER_URL>",
        },
        "cache_cfg": {
          "enabled": true,
          "metadata_ttl": 300,
          "records_ttl": 60,
          "backend": "sqlite",
          "filename": "cache.sqlite"
        },
        "cachepath": "/app/cache/gristapi"
      }
    }
  }
}
```

### Minimal

```python
{
  "connect_args": {
    "adapters": ["gristapi"],
    "adapter_kwargs": {
      "gristapi": {
        "grist_cfg": {
          "server": "https://docs.getgrist.com",
          "org_id": 123,
          "api_key": "xxxxxxxx"
        }
      }
    }
  }
}
```

With caching

```python
{
  "connect_args": {
    "adapters": ["gristapi"],
    "adapter_kwargs": {
      "gristapi": {
        "grist_cfg": 
          {
            "server": "https://docs.getgrist.com",
            "org_id": 123,
            "api_key": "xxxxxxxx"
          },
        "cache_cfg": 
          {
            "enabled": true,
            "metadata_ttl": 300,
            "records_ttl": 60,
            "backend": "sqlite",
            "filename": "/app/.cache/gristapi.sqlite"
           },
        "cachepath": "/app/.cache"
      }
    }
  }
}
```

---

## 4️⃣ Create a virtual dataset

Navigate to **SQL → SQL Lab**, 
in **Database** choose **"docs.getgrist.com"** and enter a SQL query referencing a Grist table:

```sql
-- SELECT * FROM 'grist://' -- list docs
-- SELECT * FROM 'grist://<DOC_ID> -- list tables of DOC_ID
SELECT * FROM "grist://<DOC_ID>/<TABLE_ID>"
```

You can also filter or limit data:

```sql
SELECT id, name
FROM "grist://doc_abcdef123456/Employees"
WHERE department = 'Finance'
LIMIT 10;
```

Run your query, click on **Save dataset**, choose a dataset name and click **Save and explore**.

---

## 5️⃣ Explore

You can now visualize Grist data in Superset charts just like any other data source.

---

## ⚠️ Notes

* Only **read-only** operations are supported.
* Each Grist document/table becomes a virtual table in Superset.
* Query-level parameters like `?records_ttl=10` or `?backend=memory` are supported.
* Note : `WHERE` (equality only), `ORDER BY` and `LIMIT` are pushed to the API, meaning that only required data are transfered through the network.
* Make sure your Superset image has write access to the cache directory (`cachepath`).

---

## 🧰 Troubleshooting

| Issue                            | Likely cause                          | Solution                                             |
| -------------------------------- | ------------------------------------- | ---------------------------------------------------- |
| "shillelagh error: Unsupported table: grist://" | `shillelagh-gristapi` not installed. | Install `shillelagh-gristapi` |
| "Connection refused" / "Bad URI" | SQLAlchemy URI incorrect              | Double check `shillelagh+safe://` and JSON config    |
| 401 / 403 / "unauthorized"       | Invalid API key / org_id / server URL | Verify values & permissions in Grist                 |
| "No such table" error            | Incorrect doc or table ID             | Use Grist UI to find correct IDs                     |
| Schema change not reflected      | Cache metadata stale                  | Lower `metadata_ttl` or clear cache                  |
| Slow query performance           | No filter pushdown, large data set    | Add WHERE clause; limit columns + rows; enable cache |
