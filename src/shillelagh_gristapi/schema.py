from shillelagh.fields import Boolean, Date, DateTime, Float, Integer, String
from shillelagh.fields import Field, Order
from shillelagh.filters import Filter, Equal


def map_grist_type(grist_type: str) -> Field:
    """
    Map a Grist column type (officially supported) to a shillelagh field.
    Falls back to String() for unknown or less common types.
    """
    if grist_type is None:
        return String()
    t = grist_type.strip().lower()

    # Exact official Grist types
    if t == "text":
        return String(order=Order.ANY, filters=[Equal])
    if t == "numeric":
        return Float(order=Order.ANY, filters=[Equal])
    if t.startswith("int"):
        return Integer(order=Order.ANY, filters=[Equal])
    if t == "bool":
        return Boolean(order=Order.ANY, filters=[Equal])
    if t == "date":
        return Date(order=Order.ANY, filters=[Equal])
    if t.startswith("datetime:"):
        return DateTime(order=Order.ANY, filters=[Equal])
    if t == "choice":
        # choice is a single pick from a set → String likely
        return String(order=Order.ANY, filters=[Equal])
    if t == "choicelist":
        # multiple picks → maybe JSON, or a delimiter-separated string
        return String(order=Order.ANY, filters=[Equal])
    if t.startswith("ref:"):
        # pointing to another table → JSON might represent e.g. an ID, or structured
        return String(order=Order.ANY, filters=[Equal])
    if t.startswith("reflist:"):
        return String(order=Order.ANY, filters=[Equal])
    if t == "attachments":
        # attachments are files/images → JSON (maybe with URLs/metadata)
        return String(order=Order.ANY, filters=[Equal])

    # Safe fallback
    return String()
