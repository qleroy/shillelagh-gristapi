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
from shillelagh.fields import Field, String, Integer, Date, DateTime
from shillelagh.filters import Equal, Range
from shillelagh.typing import RequestedOrder

from .http import ClientConfig, GristClient, CacheConfig
from .schema import map_grist_type


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
    # table_id may initially be a *name* if given as such; we resolve it to the true id and cache.
    table_id: Optional[str]
    is_orgs: bool = False
    is_columns: bool = False
    is_workspaces: bool = False
    is_docs: bool = False


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
        doc_id,
        table_id,
        part2,
        qs,
        grist_cfg: Dict[str, Any],
        cache_cfg: Optional[Dict[str, Any]] = None,
        cachepath: Optional[str] = None,
    ) -> None:
        """
        Construct the adapter.

        Credentials and server URL can be supplied either at the top level
        or under adapter_kwargs['gristapi'] to align with Shillelagh conventions.

        Required:
          - server
          - org_id
          - api_key
        Optional:
          - workspace_id (for listing docs)
          - enabled (default True = caching enabled)
          - metadata_ttl (default 0 = no caching)
          - records_ttl (default 0 = no caching)
          - maxsize (default 1024)
          - backend (default "memory", or "sqlite" for on-disk persistence)
          - filename (for sqlite backend; default "gristapi_cache.sqlite")
          - cachepath (directory for sqlite file; default ~/.cache/gristapi/)
        """
        gk = grist_cfg
        ck = cache_cfg or {}

        server = qs.get("server") or gk.get("server")
        if not server:
            raise ProgrammingError(
                "Grist server URL is required (adapter_kwargs['gristapi']['server'])."
            )
        org_id = qs.get("org_id") or gk.get("org_id")
        if not org_id:
            raise ProgrammingError(
                "Org ID is required (adapter_kwargs['gristapi']['org_id'])."
            )
        if isinstance(org_id, list):
            org_id = org_id[0]
        api_key = qs.get("api_key") or gk.get("api_key")
        if not api_key:
            raise ProgrammingError(
                "Grist API key is required (adapter_kwargs['gristapi']['api_key'])."
            )
        if isinstance(api_key, list):
            api_key = api_key[0]
        # workspace_id = qs.get("workspace_id") or gk.get("workspace_id", None)
        # if isinstance(workspace_id, list):
        # workspace_id = workspace_id[0]

        if "enabled" in qs:
            enabled_str = qs["enabled"][0]  # get first value from query string
            enabled = enabled_str.lower() in ("1", "true", "yes", "on")
        else:
            enabled = ck.get("enabled", True)

        if metadata_ttl := qs.get("metadata_ttl"):
            metadata_ttl = int(metadata_ttl[0])
        else:
            metadata_ttl = int(ck.get("metadata_ttl", 0))

        if records_ttl := qs.get("records_ttl"):
            records_ttl = int(records_ttl[0])
        else:
            records_ttl = int(ck.get("records_ttl", 0))

        if maxsize := qs.get("maxsize"):
            maxsize = int(maxsize[0])
        else:
            maxsize = int(ck.get("maxsize", 1024))

        if backend := qs.get("backend"):
            backend = backend[0]
        else:
            backend = ck.get("backend", "memory")

        if filename := qs.get("filename"):
            filename = filename[0]
        else:
            filename = ck.get("filename", None)

        if not cachepath:
            cachepath = os.path.expanduser("~/.cache/gristapi/")

        # ensure directory exists, handle errors
        try:
            os.makedirs(cachepath, exist_ok=True)
        except OSError as e:
            raise RuntimeError(f"Cache directory unavailable: {cachepath}") from e

        # enforce filename-only (no directories)
        if filename:
            filename_safe = os.path.basename(filename)  # strips directories
            if (
                filename_safe != filename
                or "/" in filename_safe
                or "\\" in filename_safe
            ):
                raise ValueError(f"Invalid filename: {filename}")
            filename_safe = filename  # safe plain filename

            full_path = os.path.join(cachepath, filename_safe)

            # ensure file does not exist
            # if os.path.exists(full_path):
            # raise FileExistsError(f"Cache file already exists: {full_path}")
        else:
            full_path = os.path.join(cachepath, "gristapi_cache.sqlite")

        cache_config = CacheConfig(
            enabled=enabled,
            metadata_ttl=metadata_ttl,
            records_ttl=records_ttl,
            maxsize=maxsize,
            backend=backend,
            path=full_path,
        )

        workspace_id = doc_id if table_id == SPECIAL_DOCS else None

        # Store state and bootstrap an HTTP client.
        self.state = _State(
            server=server,
            org_id=org_id,
            api_key=api_key,
            doc_id=doc_id,
            table_id=table_id,
            workspace_id=workspace_id,
            is_orgs=doc_id == SPECIAL_ORGS,
            is_columns=part2 == SPECIAL_COLUMNS,
            is_workspaces=doc_id == SPECIAL_WORKSPACES
            or table_id == SPECIAL_WORKSPACES,
            is_docs=doc_id in [None, SPECIAL_DOCS] or table_id == SPECIAL_DOCS,
        )
        self.client = GristClient(
            ClientConfig(server=server, api_key=api_key, cache=cache_config)
        )

        # Cache of discovered columns for table rows (lazy-loaded).
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
        Parse a grist:// URI into (doc_id, table_id_or_name).

        grist://                      -> (None, None)           # list docs
        grist://__orgs__              -> (SPECIAL_ORGS, None)   # list orgs
        grist://<doc_id>              -> (<doc_id>, None)       # list tables
        grist://<doc_id>/__columns__  -> (<doc_id>, SPECIAL_COLUMNS) # list columns
        grist://<doc_id>/<table>      -> (<doc_id>, table)      # table rows
        """
        path = uri[len(GRIST_PREFIX) :].strip("/")
        parsed = urllib.parse.urlparse(uri)
        netloc = parsed.netloc
        path = parsed.path.strip("/")
        part1, part2 = (path.split("/", 1) + [None])[:2]
        qs = urllib.parse.parse_qs(parsed.query)
        if not netloc:
            return None, None, None, qs
        elif netloc == SPECIAL_ORGS:
            return SPECIAL_ORGS, None, None, qs
        elif netloc == SPECIAL_WORKSPACES:
            return SPECIAL_WORKSPACES, None, None, qs
        elif netloc == SPECIAL_DOCS:
            return SPECIAL_DOCS, None, None, qs
        else:
            doc_id = netloc
            if part1 == SPECIAL_WORKSPACES:
                return doc_id, SPECIAL_WORKSPACES, None, qs
            if part1 == SPECIAL_DOCS:
                return doc_id, SPECIAL_DOCS, None, qs
            elif part1 and part2 == SPECIAL_COLUMNS:
                doc_id, table_id = netloc, part1
                return doc_id, table_id, part2, qs
            else:
                table_id = path
                return doc_id, table_id, None, qs

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
        Grist types to shillelagh fields using `map_grist_type`. If the table
        was referenced by *name*, we resolve and cache the actual table ID.
        """
        # synthetic: orgs
        if self.state.is_orgs:
            return {"id": String(), "name": String()}

        # synthetic: workspaces
        if self.state.is_workspaces:
            return {"id": String(), "name": String()}

        # root: list docs
        if self.state.is_docs:
            return {"id": String(), "name": String()}

        # synthetic: columns for a doc
        if self.state.is_columns:
            return {"name": String(), "type": String()}

        # list tables in a doc
        if not self.state.table_id:
            return {"id": String(), "name": String()}

        # Rows of a specific table: discover columns via list_columns
        if self._columns is None:
            # First, if table was given by *name*, resolve to the actual id by scanning tables.
            table_id = self._resolve_table_id()

            # Fetch column metadata
            columns = self.client.list_columns(self.state.doc_id, table_id)  # type: ignore[arg-type]
            cols: Dict[str, Field] = {}
            for col in columns:
                col = col
                cid = col.get("id")
                ctype = col["fields"].get("type")
                cols[str(cid)] = map_grist_type(str(ctype))

            if not cols:
                raise ProgrammingError(
                    f"Grist table has no columns: doc={self.state.doc_id!r} table={table_id!r}"
                )

            self._columns = cols
            self._columns["id"] = Integer()

        return self._columns

    def _resolve_table_id(self) -> str:
        """
        Resolve table_id if a *name* was provided; cache the canonical id.
        Returns the canonical table id string to use with API calls.
        """
        if self._resolved_table_id:
            return self._resolved_table_id
        if self.state.doc_id is None or self.state.table_id is None:
            raise ProgrammingError(
                "Table resolution requested without doc/table in URI"
            )

        requested = self.state.table_id
        # Scan tables in the doc
        tables = self.client.list_tables(self.state.doc_id)  # type: ignore[arg-type]
        # tables is a list from your client
        for t in tables:
            tid = t.get("id")
            tname = t.get("name")
            if requested == tid or requested == tname:
                self._resolved_table_id = tid
                self.state.table_id = tid
                return tid

        # Not found
        raise ProgrammingError(
            f"Grist table not found in doc '{self.state.doc_id}': {requested!r}"
        )

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

    def get_rows(
        self,
        bounds: Dict[str, Any],
        order: List[Tuple[str, RequestedOrder]],
        limit: Optional[int] = None,
        **kwargs: Any,
    ) -> Iterator[Dict[str, Any]]:
        # logger.debug("Bounds:", bounds)
        # logger.debug("Order:", order)

        # 01) synthetic orgs
        if self.state.is_orgs:
            orgs = self.client.list_orgs()
            for org in orgs:
                yield {"id": org.get("id"), "name": org.get("name")}
            return

        # 02) synthetic workspaces
        if self.state.is_workspaces:
            workspaces = self.client.list_workspaces(self.state.org_id)
            for ws in workspaces:
                yield {"id": ws.get("id"), "name": ws.get("name")}
            return

        # 02) Docs listing — needs org_id (and optional workspace_id)
        if self.state.is_docs:
            if self.state.org_id is None:
                raise ProgrammingError(
                    "org_id is required in adapter_kwargs['gristapi'] to list docs"
                )
            for d in self.client.list_docs(self.state.org_id, self.state.workspace_id):
                # your client yields flattened doc metadata
                yield {"id": d.get("doc_id"), "name": d.get("doc_name")}
            return

        # 03) synthetic columns for a doc
        if self.state.is_columns:
            columns = self.client.list_columns(self.state.doc_id, self.state.table_id)  # type: ignore[arg-type]
            for col in columns:
                yield {
                    "name": col["fields"].get("label"),
                    "type": col["fields"].get("type"),
                }
            return

        # 2) Tables listing
        if not self.state.table_id:
            tables = self.client.list_tables(self.state.doc_id)  # type: ignore[arg-type]
            for t in tables:
                yield {"id": t.get("id"), "name": t.get("name")}
            return

        # 3) Table rows via /records only
        # ensure we have resolved the canonical table id and discovered columns
        table_id = self._resolve_table_id()
        _ = self.get_columns()  # warm the schema cache

        params = self._build_records_params(bounds, order, limit)
        # logger.debug("Params:", params)

        # Stream rows directly from /records; we rely on the server for filtering/sorting/limit.
        for row in self.client.iter_records(self.state.doc_id, table_id, params=params):  # type: ignore[arg-type]
            for k, v in row.items():
                if isinstance(self._columns[k], Date) and v is not None:
                    v = datetime.datetime.fromtimestamp(int(v))
                elif isinstance(self._columns[k], DateTime) and v is not None:
                    v = datetime.datetime.fromtimestamp(int(v))
                elif isinstance(v, list):
                    # First is element is "L" indicating a list
                    v = ",".join([str(item) for item in v[1:]])
                row[k] = v
            yield dict(row)
