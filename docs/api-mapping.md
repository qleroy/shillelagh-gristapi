# 🗺️ API Mapping

This document describes how Grist column types and resources are mapped to SQL types (Shillelagh fields) and tables.

## Column Type Mapping

The adapter automatically translates Grist column types into the most appropriate Shillelagh field types.

| Grist Type | SQL/Shillelagh Type | Notes |
|------------|---------------------|-------|
| `Text` | `TEXT` / `String()` | Standard text. |
| `Numeric` | `FLOAT` / `Float()` | Decimal numbers. |
| `Int` / `Int*` | `INTEGER` / `Integer()` | Integers. |
| `Bool` | `BOOLEAN` / `Boolean()` | True/False values. |
| `Date` | `DATETIME` / `DateTime()` | Dates without time. |
| `DateTime` | `DATETIME` / `DateTime()` | Dates with time. |
| `Choice` | `TEXT` / `String()` | Single selection from a list. |
| `ChoiceList` | `TEXT` / `String()` | Multiple selections, returned as comma-separated values. |
| `Ref` | `TEXT` / `Reference()` | Reference to another table. Returns the display value of the referenced row if available, otherwise the row ID. |
| `RefList` | `TEXT` / `ReferenceList()`| List of references. Returns comma-separated display values or IDs. |
| `Attachments`| `TEXT` / `String()` | List of attachment IDs, comma-separated. |

### Special handling for References
Grist "Reference" and "ReferenceList" columns are handled specially:
- If a **Display Column** is configured in Grist for that reference, the adapter will automatically fetch and display the *formatted* value instead of the raw numeric row ID.
- For `RefList`, multiple display values are joined with commas.

---

## Synthetic Resources (System Tables)

The adapter provides several "synthetic" tables to help you discover your Grist data structure using SQL.

### Documents
- **URI:** `grist://` or `grist://__docs__`
- **Columns:** `id`, `name`, `createdAt`, `updatedAt`, `workspaceId`, `workspaceName`, `workspaceAccess`, `orgDomain`.

### Workspaces
- **URI:** `grist://__workspaces__`
- **Columns:** `id`, `name`, `createdAt`, `updatedAt`, `orgDomain`, `access`.

### Organizations
- **URI:** `grist://__orgs__`
- **Columns:** `id`, `name`, `createdAt`, `updatedAt`, `domain`, `access`.

### Tables (inside a document)
- **URI:** `grist://<doc_id>`
- **Columns:** `id`, `primaryViewId`, `summarySourceTable`, `onDemand`, `rawViewSectionRef`, `recordCardViewSectionRef`, `tableRef`.

### Columns (inside a table)
- **URI:** `grist://<doc_id>/<table_id>/__columns__`
- **Columns:** `id`, `type`, `label`, `description`, `isFormula`, `formula`, etc. (Full Grist column metadata).
