# Limitations

## Read-only

The adapter is strictly read-only. `INSERT`, `UPDATE`, and `DELETE` will raise a `ProgrammingError`.

## Query pushdown

The adapter pushes operations to the Grist API when possible. Anything not pushed down is evaluated locally — meaning all matching rows are fetched first.

| Operation | Pushed down? |
|---|---|
| `WHERE col = 'value'` | Yes |
| `WHERE col IN ('a', 'b')` | Yes |
| `ORDER BY` (single or multi-column) | Yes |
| `LIMIT` | Yes |
| `WHERE col > value`, `LIKE`, `OR` | No — full fetch, local filter |
| `JOIN` | No — both tables fetched in full |
| `COUNT(*)`, `SUM()`, `GROUP BY` | No — local aggregation |
| SQL functions (`strftime`, etc.) | No — local evaluation |

## Complex types

- **Attachments:** Only attachment IDs are returned, not the files themselves.
- **ChoiceList / ReferenceList:** Returned as a comma-separated string.

## Performance

### The key question: is your query pushed down?

A pushed-down query transfers only the rows you need. A non-pushed-down query transfers the entire table and filters locally. This is the single most important factor for large tables.

**Pushed down — fast at any size:**
```sql
-- Single value equality
SELECT * FROM "grist://doc/Table" WHERE status = 'active' LIMIT 100;

-- Multi-value IN — also pushed down, transfers only matching rows
SELECT * FROM "grist://doc/Orders" WHERE country IN ('FR', 'DE', 'ES');

-- Combined: equality + IN + LIMIT, all pushed down
SELECT id, name FROM "grist://doc/Contacts"
WHERE status = 'active' AND region IN ('EU', 'APAC')
LIMIT 500;
```

**Not pushed down — full table transfer:**
```sql
SELECT * FROM "grist://doc/Table" WHERE amount > 1000;
SELECT * FROM "grist://doc/Table" WHERE name LIKE '%smith%';
SELECT COUNT(*) FROM "grist://doc/Table";
```

### Row count heuristics

These are rough guides, not benchmarks — actual speed depends on your network latency, Grist server load, column count, and whether pushdown applies.

| Table size | Pushed-down query | Full table scan |
|---|---|---|
| < 1 000 rows | Instant | Instant |
| 1 000 – 10 000 rows | Instant | Fast (seconds) |
| 10 000 – 100 000 rows | Fast | Slow (tens of seconds) |
| > 100 000 rows | Fast | Very slow or timeout |

### Recommendations for large tables

**1. Always filter with `=` or `IN` on a selective column**

```sql
-- Good: equality pushed down
SELECT * FROM "grist://doc/Orders" WHERE customer_id = '123';

-- Good: IN pushed down — only matching rows transferred
SELECT * FROM "grist://doc/Orders" WHERE status IN ('pending', 'processing');

-- Bad: range filter fetches all rows, filters locally
SELECT * FROM "grist://doc/Orders" WHERE amount > 500;
```

If you need range filters on large tables, consider maintaining a filtered or aggregated view directly in Grist and querying that instead.

**2. Use `LIMIT` when exploring**

```sql
SELECT * FROM "grist://doc/BigTable" LIMIT 100;
```

`LIMIT` is pushed down to the Grist API, so this transfers at most 100 rows regardless of table size.

**3. Enable and tune the cache**

For dashboards or repeated queries on data that doesn't change often:

```python
"cache_cfg": {
    "enabled": True,
    "records_ttl": 300,   # cache rows for 5 minutes
    "metadata_ttl": 3600, # cache schema for 1 hour
    "backend": "sqlite",
}
```

The second execution of the same query hits the local cache and returns instantly.

**4. When this adapter is not the right tool**

This adapter is a good fit for:
- Interactive exploration of Grist data via SQL
- BI dashboards on tables up to ~50k rows with selective filters
- Superset charts backed by well-filtered virtual datasets

It is not a good fit for:
- Real-time analytics on tables with hundreds of thousands of rows and no selective filter
- Aggregations over full large tables run frequently (every query does a full transfer)
- ETL pipelines — use the Grist REST API directly instead
