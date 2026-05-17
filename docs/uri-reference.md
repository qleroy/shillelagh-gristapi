# URI Reference

## URI patterns

The adapter maps `grist://` URIs to Grist REST API resources. Each URI resolves to a different `ResourceKind` with a fixed or dynamically discovered column schema.

| URI | ResourceKind | Returns |
|---|---|---|
| `grist://` | DOCS | list of documents |
| `grist://__docs__` | DOCS | alias for above |
| `grist://__orgs__` | ORGS | list of organizations |
| `grist://__workspaces__` | WORKSPACES | list of workspaces |
| `grist://<doc_id>` | TABLES | list of tables in document |
| `grist://<ws_id>/__docs__` | DOCS | documents in a specific workspace |
| `grist://<doc_id>/<table_id>` | RECORDS | rows from a table |
| `grist://<doc_id>/<table_id>/__columns__` | COLUMNS | column metadata for a table |

## Column schemas

### ORGS (`grist://__orgs__`)

| Column | Type |
|---|---|
| `id` | String |
| `name` | String |
| `createdAt` | DateTime |
| `updatedAt` | DateTime |
| `domain` | String |
| `access` | String |

### WORKSPACES (`grist://__workspaces__`)

| Column | Type |
|---|---|
| `id` | String |
| `name` | String |
| `createdAt` | DateTime |
| `updatedAt` | DateTime |
| `orgDomain` | String |
| `access` | String |

### DOCS (`grist://` or `grist://__docs__` or `grist://<ws_id>/__docs__`)

| Column | Type |
|---|---|
| `id` | String |
| `name` | String |
| `createdAt` | DateTime |
| `updatedAt` | DateTime |
| `workspaceId` | String |
| `workspaceName` | String |
| `workspaceAccess` | String |
| `orgDomain` | String |

### TABLES (`grist://<doc_id>`)

| Column | Type |
|---|---|
| `id` | String |
| `primaryViewId` | Integer |
| `summarySourceTable` | Integer |
| `onDemand` | Boolean |
| `rawViewSectionRef` | Integer |
| `recordCardViewSectionRef` | Integer |
| `tableRef` | Integer |

### COLUMNS (`grist://<doc_id>/<table_id>/__columns__`)

| Column | Type |
|---|---|
| `id` | String |
| `type` | String |
| `colRef` | Integer |
| `parentId` | Integer |
| `parentPos` | Float |
| `isFormula` | Boolean |
| `formula` | String |
| `label` | String |
| `description` | String |
| `untieColIdFromLabel` | Boolean |
| `summarySourceCol` | Integer |
| `displayCol` | Integer |
| `visibleCol` | Integer |
| `reverseCol` | Integer |
| `recalcWhen` | Integer |

### RECORDS (`grist://<doc_id>/<table_id>`)

Schema is discovered dynamically from the Grist table's column metadata. The `id` column (Integer) is always present. See [type-mapping.md](type-mapping.md) for how Grist types map to SQL types.

## Query parameter overrides

Any configuration parameter can be appended to a URI as a query string to override the adapter's defaults for that specific query:

```sql
SELECT * FROM "grist://<doc_id>/<table_id>?records_ttl=10&backend=memory"
```

Overridable parameters:

| Parameter | Example | Effect |
|---|---|---|
| `records_ttl` | `records_ttl=30` | Row cache TTL in seconds |
| `metadata_ttl` | `metadata_ttl=600` | Schema cache TTL in seconds |
| `backend` | `backend=memory` | Cache backend (`sqlite` or `memory`) |
| `enabled` | `enabled=false` | Disable caching for this query |
| `maxsize` | `maxsize=2048` | Max cache entries |
| `filename` | `filename=myapp.sqlite` | Cache file name (SQLite backend only) |
| `cachepath` | `cachepath=/tmp/cache` | Cache directory |
| `server` | `server=https://grist.example.com` | Override Grist server URL |
| `org_id` | `org_id=99` | Override organization ID |
| `api_key` | `api_key=xxx` | Override API key |

URI parameters take precedence over all other configuration sources.
