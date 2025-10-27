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

In **Superset → Settings → Database Connections → + Database**, choose **"Other (SQLAlchemy URI)"**
and set the **SQLAlchemy URI** to:

```
shillelagh+safe://
```

> Use `shillelagh+safe://` instead of `shillelagh://` to enable only trusted adapters.

---

## 3️⃣ Configure the Engine Parameters

In the **“Advanced → Engine Parameters”** field, paste:

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

**✅ Tips**

* Replace `api_key`, `org_id`, and `server` with your real values.
* Use a mounted volume like `/app/cache/gristapi` for writable cache in Docker.

---

## 4️⃣ Create a virtual dataset

Create a new dataset from **SQL Lab**:
and enter a SQL query referencing a Grist table:

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

Note : `WHERE` (equality only), `ORDER BY` and `LIMIT` are pushed to the API, meaning that only required data are transfered through the network.

---

## 5️⃣ Save & Explore

You can now visualize Grist data in Superset charts and dashboards —
with filtering, ordering, and limit pushdown to Grist’s `/records` API.

---

## ⚠️ Notes

* Only **read-only** operations are supported.
* Each Grist document/table becomes a virtual table in Superset.
* Query-level parameters like `?records_ttl=10` or `?backend=memory` are supported.
* Make sure your Superset image has write access to the cache directory (`cachepath`).
