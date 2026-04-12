# 🛠️ Technical Architecture

This internal documentation explains how the Grist Shillelagh adapter is structured and how it processes SQL queries into Grist API calls.

## 🏗️ Core Modules

The package is divided into four main functional blocks:

-   **`adapter.py` (The Entry Point):** Implements the Shillelagh `Adapter` interface. It handles URI parsing (`grist://...`), schema discovery via `get_columns()`, and query execution via `get_rows()`.
-   **`http.py` (The Client):** A specialized HTTP client (`GristClient`) for the Grist REST API. It manages authentication, handles pagination for records, and integrates the caching layer.
-   **`cache.py` (The Persistence):** Provides a simple key-value storage abstraction with TTL support. It supports both `sqlite` (persistent) and `memory` (ephemeral) backends.
-   **`schema.py` (The Translator):** Contains the logic to map Grist's internal column types to Shillelagh field types (e.g., `RefList` -> `ReferenceList`).

---

## 🔄 Query Execution Flow

1.  **Instantiation:** Shillelagh detects a `grist://` URI and instantiates `GristAPIAdapter`.
2.  **Schema Discovery (`get_columns`):**
    -   If a specific table is requested, the adapter calls `client.list_columns()`.
    -   It filters out Grist internal columns (e.g., `gristHelper_`).
    -   It maps types using `schema.py`.
    -   **Reference Resolution:** It identifies if a reference column has a `displayCol` to show formatted values instead of raw IDs.
3.  **Data Retrieval (`get_rows`):**
    -   **Pushdown:** The adapter analyzes SQL `WHERE` and `LIMIT` clauses.
    -   Equality filters (`=`, `IN`) and sorting are converted into Grist API parameters (`filter`, `sort`).
    -   **Streaming:** The `GristClient` iterates over records (handling pagination) and yields raw JSON rows.
    -   **Transformation:** `_row_to_python` converts raw JSON data into Python objects based on the discovered schema, applying date parsing and reference resolution.

---

## ⚡ Caching Strategy

The adapter uses a two-tier caching system managed by `GristClient`:

1.  **Metadata Cache:** Stores column definitions and table lists. High TTL by default (`300s`) as schemas change infrequently.
2.  **Record Cache:** Stores the result of specific record queries. Lower TTL (`60s`) to ensure data freshness while speeding up repeated dashboard refreshes.

**Key components:**
- `CacheConfig`: Configuration object passed through the stack.
- `GristClient._get_with_cache()`: Wrapper that checks for a valid (non-expired) entry before hitting the network.

---

## 🔍 Pushdown Logic

The pushdown logic is located in `_build_records_params()` within `adapter.py`. 
It converts Shillelagh `Filter` objects into a JSON-encoded `filter` string compatible with Grist's `/records` endpoint.

Currently, only **`Equal`** filters are supported for pushdown. Any other filter type (like `Like`, `Range`) will cause Shillelagh to fetch all data and filter it locally in Python.
