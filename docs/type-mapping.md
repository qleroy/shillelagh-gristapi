# Type Mapping

## Column type mapping

The adapter automatically translates Grist column types into the appropriate Shillelagh field types, which determine how values are exposed to SQL.

| Grist Type | SQL/Shillelagh Type | Notes |
|---|---|---|
| `Text` | `TEXT` / `String()` | Standard text. |
| `Numeric` | `FLOAT` / `Float()` | Decimal numbers. |
| `Int` / `Int*` | `INTEGER` / `Integer()` | Integers. |
| `Bool` | `BOOLEAN` / `Boolean()` | True/False values. |
| `Date` | `DATETIME` / `DateTime()` | Dates without time. |
| `DateTime` | `DATETIME` / `DateTime()` | Dates with time. |
| `Choice` | `TEXT` / `String()` | Single selection from a list. |
| `ChoiceList` | `TEXT` / `String()` | Multiple selections, returned as a comma-separated string. |
| `Ref` | `TEXT` / `Reference()` | Reference to another table. |
| `RefList` | `TEXT` / `ReferenceList()` | List of references. |
| `Attachments` | `TEXT` / `String()` | Attachment IDs, comma-separated. |

Any Grist type not listed above falls back to `String()`.

## Reference and ReferenceList display resolution

`Ref` and `RefList` columns are handled specially:

- If a **Display Column** is configured in Grist for a reference column, the adapter automatically fetches and returns the *display value* (e.g. a name) instead of the raw numeric row ID.
- For `RefList`, multiple display values are joined with commas.
- If no Display Column is configured, the raw row ID (or list of IDs) is returned as a string.

This resolution happens transparently via Grist's `gristHelper_Display` columns, which the adapter detects and maps during schema discovery.
