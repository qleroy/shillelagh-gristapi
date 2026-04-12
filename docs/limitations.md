# ⚠️ Limitations

This adapter aims to bridge Grist's REST API and SQL via Shillelagh. However, due to the nature of the API and its current implementation, certain features and performance aspects have limitations.

## 🔒 Read-Only
- **No Writing:** The adapter is strictly **read-only**. You cannot use `INSERT`, `UPDATE`, or `DELETE` statements.
- Any attempt to modify data will result in a `ProgrammingError`.

## ⚡ Query Pushdown
To ensure optimal performance, the adapter tries to "push down" SQL operations to the Grist API whenever possible. If an operation cannot be pushed down, it will be handled **locally** by Shillelagh (fetching all records first).

### Supported Pushdowns
- **`WHERE` (Equality):** `column = 'value'` or `column IN ('a', 'b')` is pushed down to the API.
- **`ORDER BY`:** Single or multi-column sorting is pushed down to the API.
- **`LIMIT`:** The number of records fetched from the API is restricted.

### Not Pushed Down (Processed Locally)
- **Complex Filters:** `>` , `<`, `LIKE`, or `OR` clauses are evaluated locally after fetching data.
- **Joins:** SQL `JOIN` statements are processed locally by Shillelagh. This means Shillelagh will fetch all required rows from both tables before joining them.
- **Aggregations:** `COUNT(*)`, `SUM()`, `GROUP BY` etc., are calculated locally.
- **Functions:** SQL functions (e.g., `strftime`, `substring`) are executed locally.

## 🧩 Complex Types
- **Attachments:** Only attachment IDs are available. The adapter does not download or process the files themselves.
- **Reference Lists:** Multiple referenced values are returned as a single comma-separated string.

## ⏳ Performance & Caching
- **Rate Limiting:** If you query very large tables or frequently refresh without caching, you might hit Grist API rate limits.
- **Initial Schema Fetch:** The first time you query a table, the adapter must fetch the column metadata. This is cached (according to `metadata_ttl`) to speed up subsequent queries.
- **Full Table Scans:** If a query doesn't use equality filters on its `WHERE` clause, Shillelagh will fetch **all** records from the table before filtering them locally. For large Grist tables (e.g., > 10,000 rows), this may be slow.

## 🛠 Troubleshooting Large Queries
If you find a query is too slow:
1. Ensure your `WHERE` clauses use `=` or `IN` on indexed columns.
2. Enable caching (`cache_cfg.enabled = True`) to avoid re-fetching the same data.
3. Use a smaller `LIMIT` if you only need a sample of the data.
