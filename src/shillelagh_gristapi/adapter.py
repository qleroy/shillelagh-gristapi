from __future__ import annotations

"""
GristAPIAdapter
---------------
A minimal, read-only Shillelagh adapter that exposes the Grist REST API as
virtual tables using a custom URI scheme:

  - grist://                       -> list docs
  - grist://<doc_id>               -> list tables in doc
  - grist://<doc_id>/<table_id>  -> rows of a specific table

This adapter intentionally separates:
  * discovery/listing (docs, tables) with synthetic two-column schemas
  * row streaming for a specific table with a discovered schema

Pushdown strategy:
  * Equality and IN filters are pushed to the standard `/records` endpoint via
    a JSON-encoded `filter` parameter; single-column sort and limit are pushed too.
  * Any filters not pushed are evaluated locally as a last resort.

Assumptions:
  * The accompanying `GristClient` provides:
      - list_orgs()
      - list_workspaces(org_id)
      - list_docs(ws_id)
      - list_tables(doc_id)
      - list_columns(doc_id, table_id)
      - iter_records(doc_id, table_id, params) -> Iterator[dict]
  * `map_grist_type` maps official Grist column types to shillelagh Field classes.

This file is read-only by design.
"""

import json
import logging
from dataclasses import dataclass
import datetime
import os
from typing import Any, Dict, Iterator, List, Optional, Tuple
import urllib

from shillelagh.adapters.base import Adapter
from shillelagh.exceptions import ProgrammingError
from shillelagh.fields import Field, String, Integer, DateTime, Boolean, Float
from shillelagh.filters import Equal
from shillelagh.typing import RequestedOrder

from .http import ClientConfig, GristClient, CacheConfig
from .schema import map_grist_type
from .schema import Reference
from .schema import ReferenceList


GRIST_PREFIX = "grist://"
SPECIAL_ORGS = "__orgs__"
SPECIAL_COLUMNS = "__columns__"
SPECIAL_WORKSPACES = "__workspaces__"
SPECIAL_DOCS = "__docs__"
logger = logging.getLogger(__name__)


# ---------------------------
# URI parsing helpers
# ---------------------------


# ---------------------------
# Adapter state container
# ---------------------------


@dataclass
class _State:
    server: str
    org_id: int
    api_key: str
    doc_id: Optional[str]
    workspace_id: Optional[str]
    table_id: Optional[str]
    is_orgs: bool = False
    is_columns: bool = False
    is_workspaces: bool = False
    is_docs: bool = False


# ---------------------------
# Backwards compatibility
# ---------------------------
def assert_grist_params(
    grist_cfg: Optional[Dict[str, Any]] = None,
    server: Optional[str] = None,
    org_id: Optional[int] = None,
    api_key: Optional[str] = None,
):
    if grist_cfg is not None:
        pass
    elif server and org_id and api_key:
        pass
    else:
        raise ValueError(
            "You must either provide grist_cfg or server + org_id + api_key."
        )


# ---------------------------
# Adapter
# ---------------------------


class GristAPIAdapter(Adapter):
    """
    Read-only adapter for Grist.

    Supports three "virtual" resources behind one URI grammar:
      - docs list
      - tables list (per doc)
      - table rows (per doc/table)

    Safety:
      safe=True allows use via `shillelagh+safe://` transport.
    """

    safe = True  # allow loading via shillelagh+safe://
    supports_limit = True

    def __init__(
        self,
        doc_id: Optional[str],
        table_id: Optional[str],
        subresource: Optional[str],
        query_params: Dict[str, Any],
        grist_cfg: Optional[Dict[str, Any]] = None,
        server: Optional[str] = None,  # backward compatibility
        org_id: Optional[int] = None,  # backward compatibility
        api_key: Optional[str] = None,  # backward compatibility
        cache_cfg: Optional[Dict[str, Any]] = None,
        cachepath: Optional[str] = None,
    ) -> None:
        """
        Construct the adapter.

        Required (via adapter_kwargs['gristapi'] or legacy kwargs or URI query):
        - server:  Grist base URL (e.g. "https://docs.getgrist.com")
        - org_id:  Organization ID (int)
        - api_key: API token

        Optional caching (URI query > cache_cfg > defaults):
        - enabled       (bool; default True)
        - metadata_ttl  (int seconds; default 300)
        - records_ttl   (int seconds; default 60)
        - maxsize       (int; default 1024)
        - backend       ("sqlite" or "memory"; default "sqlite")
        - filename      (cache file name when sqlite; default "grist_cache.sqlite")
        - cachepath     (directory for cache file; default "~/.cache/gristapi")
        """
        import tempfile

        # ---------- small local helpers ----------
        def _qs_get(qs: Dict[str, Any], key: str, default: Any = None) -> Any:
            """Return first value for key from a parse_qs-like dict, else default."""
            v = qs.get(key, default)
            return v[0] if isinstance(v, list) else v

        def _to_bool(v: Any) -> Optional[bool]:
            if isinstance(v, bool):
                return v
            if v is None:
                return None
            return str(v).strip().lower() in {"1", "true", "yes", "on"}

        def _to_int(v: Any) -> Optional[int]:
            if v is None:
                return None
            try:
                return int(v)
            except (TypeError, ValueError):
                return None

        def _get_str_param(key: str, default: Optional[str] = None) -> Optional[str]:
            return _qs_get(query_params, key, cache_cfg.get(key, default))

        def _get_int_param(key: str, default: int) -> int:
            return (
                _to_int(_qs_get(query_params, key, cache_cfg.get(key, default)))
                or default
            )

        def _get_bool_param(key: str, default: bool) -> bool:
            val = _qs_get(query_params, key, cache_cfg.get(key, default))
            parsed = _to_bool(val) if val is not None else None
            return default if parsed is None else parsed

        # ---------- validate base config presence (legacy + modern) ----------
        assert_grist_params(
            grist_cfg=grist_cfg, server=server, org_id=org_id, api_key=api_key
        )
        base_cfg = grist_cfg or {"server": server, "org_id": org_id, "api_key": api_key}
        cache_cfg = cache_cfg or {}

        # ---------- resolve credentials (URI > config) ----------
        server_val = _qs_get(query_params, "server", base_cfg.get("server"))
        org_val = _qs_get(query_params, "org_id", base_cfg.get("org_id"))
        key_val = _qs_get(query_params, "api_key", base_cfg.get("api_key"))

        if not server_val:
            raise ProgrammingError(
                "Grist server URL is required (adapter_kwargs['gristapi']['server'])."
            )
        if org_val is None:
            raise ProgrammingError(
                "Org ID is required (adapter_kwargs['gristapi']['org_id'])."
            )
        org_val = _to_int(org_val)
        if org_val is None:
            raise ProgrammingError("Org ID must be an integer.")
        if not key_val:
            raise ProgrammingError(
                "Grist API key is required (adapter_kwargs['gristapi']['api_key'])."
            )

        # ---------- resolve cache config (URI > cache_cfg > defaults) ----------
        enabled_val = _get_bool_param("enabled", True)
        metadata_ttl_val = _get_int_param("metadata_ttl", 300)
        records_ttl_val = _get_int_param("records_ttl", 60)
        maxsize_val = _get_int_param("maxsize", 1024)
        backend_val = _get_str_param("backend", "sqlite") or "sqlite"
        filename_val = (
            _get_str_param("filename", "cache.sqlite") or "grist_cache.sqlite"
        )

        # ---------- resolve cache directory with fallbacks and safety ----------
        # Priority: function arg > URI query > cache_cfg > default (~/.cache/gristapi)
        raw_cache_dir = (
            cachepath
            or _get_str_param("cachepath")
            or cache_cfg.get("cachepath")
            or os.path.join(os.path.expanduser("~"), ".cache", "gristapi")
        )
        cache_dir = os.path.abspath(os.path.expanduser(raw_cache_dir))

        # ensure directory is writable; fallback to /tmp/gristapi if not
        def _ensure_writable_directory(path: str) -> str:
            try:
                os.makedirs(path, exist_ok=True)
                test_file = os.path.join(path, ".write_test")
                with open(test_file, "wb") as fh:
                    fh.write(b"ok")
                os.remove(test_file)
                return path
            except OSError as e:
                logger.warning(
                    "Cache dir not writable '%s' (%s). Falling back to /tmp/gristapi.",
                    path,
                    e,
                )
                fallback = os.path.join(tempfile.gettempdir(), "gristapi")
                os.makedirs(fallback, exist_ok=True)
                return fallback

        cache_dir = _ensure_writable_directory(cache_dir)

        # filename must be a bare name (no directories)
        fname = os.path.basename(filename_val)
        if fname != filename_val:
            raise ValueError(
                f"Invalid filename (must not contain directories): {filename_val}"
            )

        full_cache_path = os.path.join(cache_dir, fname)
        if backend_val == "memory":
            logger.debug(
                "Cache backend=memory; path '%s' will be ignored.", full_cache_path
            )

        # ---------- build cache config ----------
        cache_config = CacheConfig(
            enabled=enabled_val,
            metadata_ttl=metadata_ttl_val,
            records_ttl=records_ttl_val,
            maxsize=maxsize_val,
            backend=backend_val,
            path=full_cache_path,
        )

        # ---------- interpret special modes from URI parts ----------
        # Workspace-scoped docs listing (non-root): grist://<workspace_id>/__docs__
        workspace_id = doc_id if table_id == SPECIAL_DOCS else None

        # ---------- persist state & bootstrap HTTP client ----------
        self.state = _State(
            server=server_val,
            org_id=org_val,
            api_key=key_val,
            doc_id=doc_id,
            table_id=table_id,
            workspace_id=workspace_id,
            is_orgs=(doc_id == SPECIAL_ORGS),
            is_columns=(subresource == SPECIAL_COLUMNS),
            is_workspaces=(doc_id == SPECIAL_WORKSPACES),
            is_docs=(doc_id in (None, SPECIAL_DOCS) or table_id == SPECIAL_DOCS),
        )

        self.client = GristClient(
            ClientConfig(server=server_val, api_key=key_val, cache=cache_config)
        )

        # ---------- lazy schema cache ----------
        self._columns: Optional[Dict[str, Field]] = None
        self._resolved_table_id: str = ""

    # -------------
    # discovery
    # -------------

    @staticmethod
    def parse_uri(
        uri: str,
    ) -> Tuple[Optional[str], Optional[str], Optional[str], Dict[str, Any]]:
        """
         Parse a grist:// URI into (doc_id, table_id, subresource, query_params).

        Grammar (netloc = <doc_id> or a special root):
          grist://                                 -> (None, None, None, q)                 # list docs (root)
          grist://__orgs__                         -> (SPECIAL_ORGS, None, None, q)         # list orgs
          grist://__workspaces__                   -> (SPECIAL_WORKSPACES, None, None, q)   # list workspaces
          grist://__docs__                         -> (SPECIAL_DOCS, None, None, q)         # list docs (alias)
          grist://<doc_id>                         -> (<doc_id>, None, None, q)             # list tables in doc
          grist://<doc_id>/<table_id>/__columns__  -> (<doc_id>, <table_id>, SPECIAL_COLUMNS, q) # list columns in table
        """
        parsed = urllib.parse.urlparse(uri)
        netloc = parsed.netloc.strip()
        # Split and decode the path segments (filter out empty strings)
        segs = [urllib.parse.unquote(p) for p in parsed.path.split("/") if p]
        query_params = urllib.parse.parse_qs(parsed.query)

        # Case 1: Root listing (no netloc) => list available documents
        if not netloc:
            return None, None, None, query_params

        # Case 2: Special root resources (__orgs__, __workspaces__, __docs__)
        if netloc in (SPECIAL_ORGS, SPECIAL_WORKSPACES, SPECIAL_DOCS):
            return netloc, None, None, query_params

        # Case 3: Regular document ID (e.g. grist://doc-xyz123)
        doc_id = netloc

        # No path segments => list tables in that document
        if len(segs) == 0:
            return doc_id, None, None, query_params

        # Single segment => either a normal table or an internal special tag (__docs__)
        if len(segs) == 1:
            s0 = segs[0]
            if s0 == SPECIAL_DOCS:
                # Some users may use grist://<workspace_id>/__docs__ (list docs for a workspace)
                # Only makes sense if <doc_id> is actually a workspace_id.
                return doc_id, s0, None, query_params
            return doc_id, s0, None, query_params

        # Multiple segments:
        # If the last one is __columns__, treat everything before it as the table_id.
        if segs[-1] == SPECIAL_COLUMNS:
            table_id = "/".join(segs[:-1])
            return doc_id, table_id, SPECIAL_COLUMNS, query_params

        # Otherwise, rejoin everything as a (possibly nested) table identifier.
        table_id = "/".join(segs)
        return doc_id, table_id, None, query_params

    @staticmethod
    def supports(uri: str, fast: bool = True, **kwargs: Any) -> bool:
        """
        Fast path: purely syntactic check on the scheme prefix.
        Do not hit the network here.
        """
        return uri.startswith(GRIST_PREFIX)

    # -------------
    # schema
    # -------------

    def get_columns(self) -> Dict[str, Field]:
        """
        Return a mapping {column_name: Field()} for the current resource.

        Synthetic resources expose fixed schemas (orgs, workspaces, docs, columns, tables).
        For real tables, we fetch Grist metadata once, map Grist types via `map_grist_type`,
        and build a `field_id -> displayed_field_id` map to support Reference/ReferenceList rendering.
        """

        # ---- Synthetic: organizations ----
        if self.state.is_orgs:
            return {
                "id": String(),
                "name": String(),
                "createdAt": DateTime(),
                "updatedAt": DateTime(),
                "domain": String(),
                "access": String(),
            }

        # ---- Synthetic: workspaces ----
        if self.state.is_workspaces:
            return {
                "id": String(),
                "name": String(),
                "createdAt": DateTime(),
                "updatedAt": DateTime(),
                "orgDomain": String(),
                "access": String(),
            }

        # ---- Synthetic: docs listing (root / __docs__) ----
        if self.state.is_docs:
            return {
                "id": String(),
                "name": String(),
                "createdAt": DateTime(),
                "updatedAt": DateTime(),
                "workspaceId": String(),
                "workspaceName": String(),
                "workspaceAccess": String(),
                "orgDomain": String(),
            }

        # ---- Synthetic: list columns for a given table ----
        if self.state.is_columns:
            return {
                "id": String(),
                "type": String(),
                "colRef": Integer(),
                "parentId": Integer(),
                "parentPos": Float(),
                "isFormula": Boolean(),
                "formula": String(),
                "label": String(),
                "description": String(),
                "untieColIdFromLabel": Boolean(),
                "summarySourceCol": Integer(),
                "displayCol": Integer(),
                "visibleCol": Boolean(),
                "reverseCol": Integer(),
                "recalcWhen": Integer(),
            }

        # ---- Synthetic: list tables in a doc ----
        if not self.state.table_id:
            return {
                "id": String(),
                "primaryViewId": Integer(),
                "summarySourceTable": Integer(),
                "onDemand": Boolean(),
                "rawViewSectionRef": Integer(),
                "recordCardViewSectionRef": Integer(),
                "tableRef": Integer(),
            }

        # ---- Real table: discover schema once and cache it ----
        if self._columns is not None:
            return self._columns

        doc_id = self.state.doc_id
        table_id = self.state.table_id
        if not doc_id or not table_id:
            raise ProgrammingError(
                "Missing doc_id or table_id for table schema discovery."
            )

        try:
            columns_meta = self.client.list_columns(doc_id, table_id)  # type: ignore[arg-type]
        except Exception as exc:
            logger.exception(
                "Failed to list columns: doc=%r table=%r", doc_id, table_id
            )
            raise ProgrammingError(f"Grist list_columns failed: {exc}") from exc

        schema: Dict[str, Field] = {}
        # Track which columns declare a displayCol (referencing another column by colRef)
        wants_display_for: Dict[str, int] = {}  # field_id -> displayCol (colRef int)
        # Build colRef -> id index so we can resolve displayCol in O(1)
        colref_to_id: Dict[int, str] = {}

        # First pass: build schema & colRef index, skip helper columns
        for meta in columns_meta:
            field_id = str(meta.get("id"))
            fields = meta.get("fields", {}) or {}
            if not field_id:
                continue

            # Skip internal helper fields and manual sort
            if field_id.startswith("gristHelper_Display") or field_id == "manualSort":
                continue

            # Map grist type -> Shillelagh Field
            grist_type_name = str(fields.get("type"))
            try:
                field_class = map_grist_type(grist_type_name)
            except Exception:
                # Fallback to String for unknown/unsupported types
                field_class = String()

            schema[field_id] = field_class

            # Index colRef → id for later resolution of displayCol
            col_ref = fields.get("colRef")
            if isinstance(col_ref, int):
                colref_to_id[col_ref] = field_id

            # Record a display target if present
            display_col_ref = fields.get("displayCol")
            if isinstance(display_col_ref, int) and display_col_ref > 0:
                wants_display_for[field_id] = display_col_ref

        if not schema:
            raise ProgrammingError(
                f"Grist table has no columns: doc={doc_id!r} table={table_id!r}"
            )

        # Second pass: resolve displayCol references to field IDs
        field_to_displayed_col_id: Dict[str, str] = {}
        for field_id, display_ref in wants_display_for.items():
            target_id = colref_to_id.get(display_ref)
            if target_id:
                field_to_displayed_col_id[field_id] = target_id

        # Ensure there is an "id" field (don’t overwrite if the table already has one)
        if "id" not in schema:
            schema["id"] = Integer()

        # Cache results
        self._columns = schema
        # Store the mapping for Reference / ReferenceList rendering path
        self._field_to_displayed_col_id = field_to_displayed_col_id  # type: ignore[attr-defined]

        return self._columns

    @staticmethod
    def _order_to_sort_string(order: List[Tuple[str, RequestedOrder]]) -> Optional[str]:
        """
        Convert shillelagh order spec into a multi-column sort string for /records.
        ASC  -> "col"
        DESC -> "-col"
        Multiple columns joined by commas, e.g. "pet,-age".
        """
        if not order:
            return None

        parts: List[str] = []
        for col, direction in order:
            is_asc = getattr(direction, "name", "").upper() == "ASCENDING"
            parts.append(col if is_asc else f"-{col}")
        return ",".join(parts)

    @staticmethod
    def _build_records_params(
        bounds: Dict[str, Any],
        order: List[Tuple[str, RequestedOrder]],
        limit: Optional[int],
    ) -> Dict[str, Any]:
        """
        Build /records params with only what the endpoint supports.
        - filter: JSON object of Equal/In
        - sort:   multi-column string, e.g. "colA,-colB"
        - limit:  int
        """
        params: Dict[str, Any] = {}

        # Validate and build filter
        filter_obj: Dict[str, Any] = {}
        for col, f in (bounds or {}).items():
            if isinstance(f, Equal):
                filter_obj[col] = [f.value]
            else:
                # Unknown filter types are not supported
                raise ProgrammingError(
                    f"Unsupported filter type for column {col!r}: {type(f).__name__}"
                )

        if filter_obj:
            params["filter"] = json.dumps(filter_obj)

        sort_str = GristAPIAdapter._order_to_sort_string(order)
        if sort_str:
            params["sort"] = sort_str

        if limit is not None:
            params["limit"] = int(limit)

        return params

    # -----------
    # data
    # -----------

    def _row_to_python(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert a raw Grist row into native Python values according to self._columns.
        Safe against None and non-list payloads returned by the API.
        """

        # guard in case mapping wasn't initialized yet
        field_to_display = getattr(self, "_field_to_displayed_col_id", {}) or {}

        def _join_after_sentinel(value: Any) -> Optional[str]:
            """
            Grist often returns lists with a leading sentinel/metadata element.
            This returns a comma-joined string of elements after the first one.
            If value is None or empty, returns None. If not a list, returns str(value).
            """
            if value is None:
                return None
            if isinstance(value, list):
                if len(value) <= 1:
                    return None  # either [] or [sentinel] → nothing to show
                return ",".join(str(x) for x in value[1:])
            # scalar case (string/number/etc.)
            return str(value)

        def _parse_dt(v: Any) -> Optional[datetime.datetime]:
            if v in (None, ""):
                return None
            return datetime.datetime.fromtimestamp(v)

        parsed: Dict[str, Any] = {}
        for col_name, field in (self._columns or {}).items():
            raw = row.get(col_name)

            # Datetime fields: robust parsing
            if isinstance(field, DateTime):
                parsed_val = _parse_dt(raw)

            # Reference => display via mapped displayed column (if available)
            elif isinstance(field, Reference):
                display_id = field_to_display.get(col_name)
                if display_id:
                    parsed_val = _join_after_sentinel(row.get(display_id))
                    # fallback to raw if display is missing/empty
                    if parsed_val is None:
                        parsed_val = _join_after_sentinel(raw)
                else:
                    parsed_val = _join_after_sentinel(raw)

            # ReferenceList => display via mapped displayed column (list-safe)
            elif isinstance(field, ReferenceList):
                display_id = field_to_display.get(col_name)
                if display_id:
                    parsed_val = _join_after_sentinel(row.get(display_id))
                    if parsed_val is None:
                        parsed_val = _join_after_sentinel(raw)
                else:
                    parsed_val = _join_after_sentinel(raw)

            # Bare list values (skip sentinel if present)
            elif isinstance(raw, list):
                parsed_val = _join_after_sentinel(raw)

            else:
                parsed_val = raw

            # Final parse through field type if not None
            parsed[col_name] = (
                field.parse(parsed_val) if parsed_val is not None else None
            )

        return parsed

    def get_rows(
        self,
        bounds: Dict[str, Any],
        order: List[Tuple[str, RequestedOrder]],
        limit: Optional[int] = None,
        **kwargs: Any,
    ) -> Iterator[Dict[str, Any]]:
        logger.debug(f"Bounds= {bounds}")
        logger.debug(f"Order= {order}")

        # 01) synthetic orgs
        if self.state.is_orgs:
            orgs = self.client.list_orgs()
            for org in orgs:
                if createdAt := org.get("createdAt"):
                    createdAt = datetime.datetime.strptime(
                        createdAt, "%Y-%m-%dT%H:%M:%S.%fZ"
                    )
                if updatedAt := org.get("updatedAt"):
                    updatedAt = datetime.datetime.strptime(
                        updatedAt, "%Y-%m-%dT%H:%M:%S.%fZ"
                    )
                yield {
                    "id": org.get("id"),
                    "name": org.get("name"),
                    "createdAt": createdAt,
                    "updatedAt": updatedAt,
                    "domain": org.get("domain"),
                    "access": org.get("access"),
                }
            return

        # 02) synthetic workspaces
        if self.state.is_workspaces:
            workspaces = self.client.list_workspaces(self.state.org_id)
            for ws in workspaces:
                if createdAt := ws.get("createdAt"):
                    createdAt = datetime.datetime.strptime(
                        createdAt, "%Y-%m-%dT%H:%M:%S.%fZ"
                    )
                if updatedAt := ws.get("updatedAt"):
                    updatedAt = datetime.datetime.strptime(
                        updatedAt, "%Y-%m-%dT%H:%M:%S.%fZ"
                    )
                yield {
                    "id": ws.get("id"),
                    "name": ws.get("name"),
                    "createdAt": createdAt,
                    "updatedAt": updatedAt,
                    "orgDomain": ws.get("orgDomain"),
                    "access": ws.get("access"),
                }
            return

        # 02) Docs listing — needs org_id (and optional workspace_id)
        if self.state.is_docs:
            if self.state.org_id is None:
                raise ProgrammingError(
                    "org_id is required in adapter_kwargs['gristapi'] to list docs"
                )
            for d in self.client.list_docs(self.state.org_id, self.state.workspace_id):
                # your client yields flattened doc metadata
                if createdAt := d.get("doc_created_at"):
                    createdAt = datetime.datetime.strptime(
                        createdAt, "%Y-%m-%dT%H:%M:%S.%fZ"
                    )
                if updatedAt := d.get("doc_updated_at"):
                    updatedAt = datetime.datetime.strptime(
                        updatedAt, "%Y-%m-%dT%H:%M:%S.%fZ"
                    )
                # if isinstance(self._columns[k], DateTime) and v is not None:
                # v = datetime.datetime.fromtimestamp(int(v))
                yield {
                    "id": d.get("doc_id"),
                    "name": d.get("doc_name"),
                    "createdAt": createdAt,
                    "updatedAt": updatedAt,
                    "workspaceId": d.get("workspace_id"),
                    "workspaceName": d.get("workspace_name"),
                    "workspaceAccess": d.get("workspace_access"),
                    "orgDomain": d.get("org_domain"),
                }
            return

        # 03) synthetic columns for a doc
        if self.state.is_columns:
            columns = self.client.list_columns(self.state.doc_id, self.state.table_id)  # type: ignore[arg-type]
            for col in columns:
                yield {
                    "id": col.get("id"),
                    "type": col["fields"].get("type"),
                    "colRef": col["fields"].get("colRef"),
                    "parentId": col["fields"].get("parentId"),
                    "parentPos": col["fields"].get("parentPos"),
                    "isFormula": col["fields"].get("isFormula"),
                    "formula": col["fields"].get("formula"),
                    "label": col["fields"].get("label"),
                    "description": col["fields"].get("description"),
                    "untieColIdFromLabel": col["fields"].get("untieColIdFromLabel"),
                    "summarySourceCol": col["fields"].get("summarySourceCol"),
                    "displayCol": col["fields"].get("displayCol"),
                    "visibleCol": col["fields"].get("visibleCol"),
                    "reverseCol": col["fields"].get("reverseCol"),
                    "recalcWhen": col["fields"].get("recalcWhen"),
                }
            return

        # 2) Tables listing
        if not self.state.table_id:
            tables = self.client.list_tables(self.state.doc_id)  # type: ignore[arg-type]
            for t in tables:
                yield {
                    "id": t.get("id"),
                    "primaryViewId": t["fields"].get("primaryViewId"),
                    "summarySourceTable": t["fields"].get("summarySourceTable"),
                    "onDemand": t["fields"].get("onDemand"),
                    "rawViewSectionRef": t["fields"].get("rawViewSectionRef"),
                    "recordCardViewSectionRef": t["fields"].get(
                        "recordCardViewSectionRef"
                    ),
                    "tableRef": t["fields"].get("tableRef"),
                }
            return

        # 3) Table rows via /records only
        table_id = self.state.table_id
        _ = self.get_columns()  # warm the schema cache

        params = self._build_records_params(bounds, order, limit)
        logger.debug(f"Params= {params}")

        # Stream rows directly from /records; we rely on the server for filtering/sorting/limit.
        for row in self.client.iter_records(self.state.doc_id, table_id, params=params):  # type: ignore[arg-type]
            yield self._row_to_python(row)
