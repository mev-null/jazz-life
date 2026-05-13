from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import HTTPException, status

from app.core.exceptions import ConflictError, NotFoundError


@contextmanager
def http_errors() -> Iterator[None]:
    try:
        yield
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
