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

        Parameters
        ----------
        doc_id : str | None
            Document identifier (e.g. 'doc123').
            None when listing all docs.
        table_id : str | None
            Table identifier within a doc.
            None when listing tables.
        subresource : str | None
            Optional secondary resource within a table (e.g. "__columns__").
        query_params : dict
            Parsed query parameters from the URI (output of parse_qs()).

        Required (from adapter_kwargs['gristapi'] or legacy kwargs or query params):
        - server:   Grist base URL, e.g. "https://grist.example.com"
        - org_id:   Organization identifier (int)
        - api_key:  API access token

        Optional cache knobs (query params override cache_cfg):
        - enabled       (bool; default True)
        - metadata_ttl  (int seconds; default 300)
        - records_ttl   (int seconds; default 60)
        - maxsize       (int; default 1024)
        - backend       ("sqlite" or "memory"; default "sqlite")
        - filename      (cache file name when backend="sqlite"; default "cache.sqlite")
        - cachepath     (directory for the cache file; default "~/.cache/gristapi")
        """

        # ---------- Small helpers (local scope) ----------
        def _qs_get(qs: Dict[str, Any], key: str, default: Any = None) -> Any:
            """Return first value for key from parse_qs-like dict, else default."""
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

        # ---------- Validate config presence (legacy + modern) ----------
        assert_grist_params(
            grist_cfg=grist_cfg, server=server, org_id=org_id, api_key=api_key
        )
        base_cfg = grist_cfg or {"server": server, "org_id": org_id, "api_key": api_key}
        cache_cfg = cache_cfg or {}

        # ---------- Resolve core credentials (query params override config) ----------
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

        # ---------- Resolve cache configuration (query params > cache_cfg > defaults) ----------
        def _get_str_param(key: str, default: str = None) -> Optional[str]:
            return _qs_get(query_params, key, cache_cfg.get(key, default))

        def _get_int_param(key: str, default: int) -> int:
            return (
                _to_int(_qs_get(query_params, key, cache_cfg.get(key, default)))
                or default
            )

        def _get_bool_param(key: str, default: bool) -> Optional[bool]:
            val = _qs_get(query_params, key, cache_cfg.get(key, default))
            return _to_bool(val) if val is not None else default

        # Then the actual config parsing becomes ultra-readable:
        enabled_val = _get_bool_param("enabled", True)
        metadata_ttl_val = _get_int_param("metadata_ttl", 300)
        records_ttl_val = _get_int_param("records_ttl", 60)
        maxsize_val = _get_int_param("maxsize", 1024)
        backend_val = _get_str_param("backend", "sqlite")
        filename_val = _get_str_param("filename", "cache.sqlite")

        # ---------- Resolve cache path (default to ~/.cache/gristapi) ----------
        if not cachepath:
            cachepath = os.path.join(os.path.expanduser("~"), ".cache", "gristapi")
        try:
            os.makedirs(cachepath, exist_ok=True)
        except OSError as e:
            raise RuntimeError(f"Cache directory unavailable: {cachepath}") from e

        # ---------- Ensure filename is a bare file name (no directories) ----------
        if filename_val:
            filename_base = os.path.basename(filename_val)
            if filename_base != filename_val:
                raise ValueError(f"Invalid filename: {filename_val}")
            full_cache_path = os.path.join(cachepath, filename_base)
        else:
            full_cache_path = os.path.join(cachepath, "cache.sqlite")

        # ---------- Build cache config ----------
        cache_config = CacheConfig(
            enabled=enabled_val,
            metadata_ttl=metadata_ttl_val,
            records_ttl=records_ttl_val,
            maxsize=maxsize_val,
            backend=backend_val,
            path=full_cache_path,
        )

        # ---------- Interpret special modes from URI parts ----------
        # Workspace-scoped doc listing: grist://<workspace_id>/__docs__
        workspace_id = doc_id if table_id == SPECIAL_DOCS else None

        # ---------- Persist state & bootstrap HTTP client ----------
        self.state = _State(
            server=server_val,
            org_id=org_val,
            api_key=key_val,
            doc_id=doc_id,
            table_id=table_id,
            workspace_id=workspace_id,
            is_orgs=(doc_id == SPECIAL_ORGS),
            is_columns=(subresource == SPECIAL_COLUMNS),
            is_workspaces=(doc_id == SPECIAL_WORKSPACES),  # only valid at root-level
            is_docs=(doc_id in (None, SPECIAL_DOCS)),  # root or special alias
        )

        self.client = GristClient(
            ClientConfig(server=server_val, api_key=key_val, cache=cache_config)
        )

        # ---------- Lazy schema cache ----------
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
        Return a mapping of column_name -> Field() for the current resource.

        Listing resources expose two synthetic columns:
          - docs list:   {"id": String(), "name": String()}
          - tables list: {"id": String(), "name": String()}

        For a specific table, we fetch the table schema once and map official
        Grist types to shillelagh fields using `map_grist_type`.
        """
        # synthetic: orgs
        if self.state.is_orgs:
            return {
                "id": String(),
                "name": String(),
                "createdAt": DateTime(),
                "updatedAt": DateTime(),
                "domain": String(),
                "access": String(),
            }

        # synthetic: workspaces
        if self.state.is_workspaces:
            return {
                "id": String(),
                "name": String(),
                "createdAt": DateTime(),
                "updatedAt": DateTime(),
                "orgDomain": String(),
                "access": String(),
            }

        # root: list docs
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

        # synthetic: columns for a doc
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

        # list tables in a doc
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

        # Rows of a specific table: discover columns via list_columns
        if self._columns is None:
            table_id = self.state.table_id

            # Fetch column metadata
            columns = self.client.list_columns(self.state.doc_id, table_id)  # type: ignore[arg-type]
            cols: Dict[str, Field] = {}
            displayCols: Dict[str, int] = {}
            for col in columns:
                cid = str(col.get("id"))
                ctype = col["fields"].get("type")
                grist_type = map_grist_type(str(ctype))
                if cid.startswith("gristHelper_Display"):
                    continue
                if cid == "manualSort":
                    continue
                cols[str(cid)] = grist_type
                displayCols[str(cid)] = col["fields"].get("displayCol", 0)

            field_to_displayed_col_id: Dict[str, str] = {}
            for col in columns:
                displayCol = col["fields"].get("displayCol", 0)
                if displayCol:
                    for col2 in columns:
                        colRef = col2["fields"].get("colRef", 0)
                        if colRef == displayCol:
                            field_to_displayed_col_id[col["id"]] = col2["id"]
                            break

            if not cols:
                raise ProgrammingError(
                    f"Grist table has no columns: doc={self.state.doc_id!r} table={table_id!r}"
                )

            self._columns = cols
            self._field_to_displayed_col_id = field_to_displayed_col_id
            self._columns["id"] = Integer()

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
        Convertit une ligne brute renvoyée par l’API Grist
        en valeurs Python natives selon self._columns.
        """
        parsed = {}

        for col, field in self._columns.items():
            raw_value = row.get(col)

            if isinstance(field, DateTime) and raw_value is not None:
                try:
                    raw_value = datetime.datetime.fromtimestamp(int(raw_value))
                except (ValueError, TypeError):
                    raw_value = None
            elif isinstance(field, Reference):
                displayedColId = self._field_to_displayed_col_id.get(col)
                raw_value = row.get(displayedColId)
            elif isinstance(field, ReferenceList):
                displayedColId = self._field_to_displayed_col_id.get(col)
                displayedColValue = row.get(displayedColId)
                raw_value = ",".join(displayedColValue[1:])
            elif isinstance(raw_value, list):
                raw_value = ",".join([str(item) for item in raw_value[1:]])

            parsed[col] = field.parse(raw_value) if raw_value is not None else None

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
