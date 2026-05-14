from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ListResponse(BaseModel, Generic[T]):
    items: list[T]
    # `total` は paginated エンドポイント (records 等) で全件数を返すために使う。
    # デフォルト 0 で既存の `ListResponse(items=...)` 呼び出しは無修正で通る。
    # ページネーション対応していない endpoint では items 件数と一致しない値が
    # 入る可能性があるので、フロント側は paginated 経路だけで参照する。
    total: int = 0
