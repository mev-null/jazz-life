from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import HTTPException, status

from app.core.exceptions import ConflictError, NotFoundError, RecognitionError


@contextmanager
def http_errors() -> Iterator[None]:
    try:
        yield
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except RecognitionError as exc:
        # status_code は RecognitionError 側が決める (503 未設定 / 502 上流失敗)。
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
