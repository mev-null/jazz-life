"""Audio recognition endpoint (ADR-016).

Accepts a short recorded clip, identifies the track via AudD, and returns a
`RecognitionResult`. The frontend (the Listen tab in Digging) uses the result to
prefill the add-record form.

Protected by the existing app login (`get_current_user`). RecognitionService
handles the AudD call; failures surface as RecognitionError and are mapped to
HTTP by http_errors.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile

from app.models.user import User
from app.routers._handlers import http_errors
from app.routers.deps import get_current_user, get_recognition_service
from app.schemas.recognition import RecognitionResult
from app.services.recognition_service import RecognitionService

router = APIRouter(prefix="/api/recognize", tags=["recognize"])


@router.post("", response_model=RecognitionResult)
def recognize(
    file: UploadFile = File(...),
    service: RecognitionService = Depends(get_recognition_service),
    _: User = Depends(get_current_user),
) -> RecognitionResult:
    """Recognize a recorded clip (multipart `file`) via AudD and return one match.

    `matched=False` when nothing matched. 503 if the API token is not
    configured, 502 on upstream failure.
    """
    with http_errors():
        audio = file.file.read()
        return service.recognize(audio, file.content_type)
