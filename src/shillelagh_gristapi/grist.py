# pylint: disable=abstract-method
"""
An adapter for the Grist API.
"""
from datetime import (
    date,
    datetime,
)
from typing import (
    Any,
    Dict,
    Iterator,
    List,
    Optional,
    Tuple,
)
import logging
import os
import urllib.parse

import requests
import requests_cache

from . import request_cache_backend

from shillelagh.adapters.base import Adapter
from shillelagh.fields import (
    Boolean,
    Date,
    DateTime,
    Field,
    Float,
    Integer,
    Order,
    String,
)
from shillelagh.filters import (
    Filter,
    Range,
)
from shillelagh.typing import (
    RequestedOrder,
    Row,
)

logger = logging.getLogger()

if os.getenv("DEBUG") and os.getenv("DEBUG").lower() in ["true", "1"]:
    logging.basicConfig(level=logging.DEBUG)
    stdout_handler = logging.StreamHandler()
    stdout_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    stdout_handler.setFormatter(formatter)
    logger.addHandler(stdout_handler)
else:
    logging.basicConfig(level=logging.ERROR)


class GristAPI(Adapter):
    """
    An adapter for the Grist API.
    """

    # Set this to ``True`` if the adapter doesn't access the filesystem.
    safe = True
    supports_limit = True

    @staticmethod
    def supports(uri: str, fast: bool = True, **kwargs: Any) -> Optional[bool]:
        logger.debug(f"supports {uri=} {fast=} {kwargs=}")
        parsed = urllib.parse.urlparse(uri)
        logger.debug(f"supports {parsed=}")
        return parsed.scheme == "grist"

    @staticmethod
    def parse_uri(uri: str) -> Tuple[str]:
        return (uri,)

    def __init__(
        self,
        uri: str,
        org_id: str,
        server: str,
        api_key: str,
        expire_after: Optional[int] = None,
        cache_name: Optional[str] = None,
    ):
        super().__init__()

        parsed = urllib.parse.urlparse(uri)
        query_string = urllib.parse.parse_qs(parsed.query)

        split_path = parsed.path.split("/")
        self.table_id = None
        if len(split_path) > 1:
            self.table_id = split_path[1]
        self.doc_id = parsed.netloc
        logger.debug(f"__init__ {self.doc_id=}")
        if not api_key:
            api_key = query_string["key"][0]
        if not server:
            server = query_string["server"][0]
        if not org_id:
            org_id = query_string["org_id"][0]
        if not expire_after:
            try:
                expire_after = int(query_string["expire_after"][0])
            except KeyError:
                expire_after = 0
        if not cache_name:
            try:
                cache_name = query_string["cache_name"][0]
            except KeyError:
                cache_name = "grist_cache"
        self.headers = {"Authorization": f"Bearer {api_key}"}
        self.server = server
        self.org_id = org_id
        self.expire_after = expire_after
        self.cache_name = cache_name

        backend = request_cache_backend()
        self._session = requests_cache.CachedSession(
            cache_name=self.cache_name,
            backend=backend,
            expire_after=self.expire_after,
        )

        if self.doc_id:
            if self.table_id:
                self._set_columns_data()
            else:
                self._set_columns_tables()
        else:
            self._set_columns_docs()

    def _set_columns_data(self) -> None:
        """
        Call to
        https://support.getgrist.com/api/#tag/columns/operation/listColumns
        to set column types
        """
        logger.debug(f"_set_columns_data {self.table_id=}")
        url = f"{self.server}/api/docs/{self.doc_id}/tables/{self.table_id}/columns"

        response = self._session.get(url, headers=self.headers)
        columns = response.json()["columns"]

        def gettype(type):
            if type == "Text":
                return String(order=Order.NONE)
            elif type == "Int":
                return Integer(order=Order.NONE)
            elif type == "Numeric":
                return Float(order=Order.NONE)
            elif type == "Bool":
                return Boolean(order=Order.NONE)
            elif type == "Choice":
                return String(order=Order.NONE)
            elif type == "ChoiceList":
                return String(order=Order.NONE)
            elif type == "Date":
                return Date(filters=[Range], exact=False, order=Order.NONE)
            elif type.startswith("DateTime:"):
                return DateTime(filters=[Range], exact=False, order=Order.NONE)
            elif type.startswith("Ref:"):
                return String(order=Order.NONE)
            elif type.startswith("RefList:"):
                return String(order=Order.NONE)
            elif type == "Attachments":
                return String(order=Order.NONE)
            else:
                logger.debug(f"{type=}")
                return String(order=Order.NONE)

        labeltypes = [(c["id"], gettype(c["fields"]["type"])) for c in columns]
        self.columns: Dict[str, Field] = {lt[0]: lt[1] for lt in labeltypes}
        self.columns_datestimes = {
            k: v for k, v in self.columns.items() if type(v) in [Date, DateTime]
        }
        self.columns["id"] = Integer(order=Order.NONE)
        # self.columns["manualSort"] = Integer(order=Order.NONE)
        logger.debug(f"_set_columns_data {self.columns=}")

    def _set_columns_tables(self) -> Dict[str, Field]:
        self.columns = {
            "id": String(order=Order.NONE),
        }

    def _set_columns_docs(self) -> Dict[str, Field]:
        self.columns = {
            "id": Integer(order=Order.NONE),
            "name": String(order=Order.NONE),
            "access": String(order=Order.NONE),
            "orgDomain": String(order=Order.NONE),
            "doc_id": String(order=Order.NONE),
            "doc_name": String(order=Order.NONE),
            "doc_createdAt": String(order=Order.NONE),
            "doc_updatedAt": String(order=Order.NONE),
        }

    def fetch_table(
        self,
        bounds: Dict[str, Filter],
        order: List[Tuple[str, RequestedOrder]],
        limit: Optional[int] = None,
        **kwargs,
    ) -> Iterator[Row]:
        """
        Call to
        https://support.getgrist.com/api/#tag/records/operation/listRecords
        Yields a row of data
        """
        logger.debug("fetch_table")
        if limit is None:
            limit = 0
        url = f"{self.server}/api/docs/{self.doc_id}/tables/{self.table_id}/records?limit={limit}"
        logger.debug(f"fetch_table {url=}")

        response = self._session.get(url, headers=self.headers)
        records = response.json()["records"]
        for record in records:
            field = record["fields"]
            logger.debug(f"{field=}")
            logger.debug(f"{self.columns=}")
            f = {}
            f["id"] = record["id"]
            for k, v in field.items():
                if isinstance(self.columns[k], Date) and v is not None:
                    v = date.fromtimestamp(int(v))
                elif isinstance(self.columns[k], DateTime) and v is not None:
                    v = datetime.fromtimestamp(int(v))
                elif isinstance(v, list):
                    v = ",".join([str(item) for item in v])
                f[k] = v
            yield f

    def fetch_table_ids(
        self,
        bounds: Dict[str, Filter],
        order: List[Tuple[str, RequestedOrder]],
        **kwargs,
    ) -> Iterator[Row]:
        """
        Call to
        https://support.getgrist.com/api/#tag/tables/operation/listTables
        Yields a table_id
        """
        url = f"{self.server}/api/docs/{self.doc_id}/tables"

        response = self._session.get(url, headers=self.headers)
        tables = response.json()["tables"]
        for table in tables:
            yield {"id": table["id"]}

    def fetch_docs_ids(
        self,
        bounds: Dict[str, Filter],
        order: List[Tuple[str, RequestedOrder]],
        **kwargs,
    ) -> Iterator[Row]:
        """
        Call to
        https://support.getgrist.com/api/#tag/workspaces/operation/listWorkspaces
        Yields a doc_id
        """
        url = f"{self.server}/api/orgs/{self.org_id}/workspaces"

        response = self._session.get(url, headers=self.headers)
        workspaces = response.json()
        for workspace in workspaces:
            for doc in workspace["docs"]:
                yield {
                    "id": workspace["id"],
                    "name": workspace["name"],
                    "access": workspace["access"],
                    "orgDomain": workspace["orgDomain"],
                    "doc_id": doc["id"],
                    "doc_name": doc["name"],
                    "doc_createdAt": doc["createdAt"],
                    "doc_updatedAt": doc["updatedAt"],
                }

    def get_columns(self) -> Dict[str, Field]:
        return self.columns

    def get_metadata(self) -> Dict[str, Any]:
        return {}

    def get_rows(
        self,
        bounds: Dict[str, Filter],
        order: List[Tuple[str, RequestedOrder]],
        limit: Optional[int] = None,
        **kwargs,
    ) -> Iterator[Row]:
        if self.doc_id:
            if self.table_id:
                logger.debug(f"get_rows fetch_table {self.doc_id=} {self.table_id}")
                return self.fetch_table(bounds, order, limit, **kwargs)
            else:
                logger.debug(f"get_rows fetch_table_ids {self.doc_id=}")
                return self.fetch_table_ids(bounds, order, **kwargs)
        else:
            logger.debug("get_rows fetch_docs_ids")
            return self.fetch_docs_ids(bounds, order, **kwargs)
