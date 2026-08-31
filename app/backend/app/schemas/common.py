from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ListResponse(BaseModel, Generic[T]):
    items: list[T]
    # `total` carries the full count for paginated endpoints (records etc.).
    # It defaults to 0 so existing `ListResponse(items=...)` calls work unchanged.
    # On endpoints without pagination it may not match len(items), so the
    # frontend should only read it on paginated paths.
    total: int = 0
