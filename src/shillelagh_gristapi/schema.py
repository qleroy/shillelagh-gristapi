from typing import Any, List, Optional, Set, Tuple

from shillelagh.fields import Boolean, DateTime, Float, Integer, String
from shillelagh.fields import Field, Order
from shillelagh.filters import Equal, Filter, Operator


class IsIn(Filter):
    """
    Multi-value equality filter.

    Handles both single-value (WHERE col = 'x') and multi-value
    (WHERE col IN ('x', 'y')) equality constraints, mapping them to
    Grist's filter parameter: {"col": ["x", "y"]}.
    """

    operators: Set[Operator] = {Operator.EQ}

    def __init__(self, values: List[Any]) -> None:
        self.values = values

    @classmethod
    def build(cls, operations: Set[Tuple[Operator, Any]]) -> "IsIn":
        return cls([value for _, value in operations])

    def check(self, value: Any) -> bool:
        return value in self.values

    def __repr__(self) -> str:
        return f"IN {self.values!r}"


class Reference(Field[str, str]):
    type = "TEXT"
    db_api_type = "TEXT"


class ReferenceList(Field[str, str]):
    type = "TEXT"
    db_api_type = "TEXT"


def map_grist_type(grist_type: str) -> Field:
    """
    Map a Grist column type (officially supported) to a shillelagh field.
    Falls back to String() for unknown or less common types.
    """
    if grist_type is None:
        return String()
    t = grist_type.strip().lower()

    if t == "text":
        return String(order=Order.ANY, filters=[IsIn])
    if t == "numeric":
        return Float(order=Order.ANY, filters=[IsIn])
    if t.startswith("int"):
        return Integer(order=Order.ANY, filters=[IsIn])
    if t == "bool":
        return Boolean(order=Order.ANY, filters=[IsIn])
    if t == "date":
        return DateTime(order=Order.ANY, filters=[IsIn])
    if t.startswith("datetime:"):
        return DateTime(order=Order.ANY, filters=[IsIn])
    if t == "choice":
        return String(order=Order.ANY, filters=[IsIn])
    if t == "choicelist":
        # multiple picks — elements separated by commas; no server-side filter support
        return String(order=Order.ANY)
    if t.startswith("ref:"):
        return Reference()
    if t.startswith("reflist:"):
        return ReferenceList()
    if t == "attachments":
        return String(order=Order.ANY, filters=[IsIn])

    # Safe fallback
    return String()
