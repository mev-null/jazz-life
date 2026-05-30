"""音声認識エンドポイント (ADR-016)。

録音した短いクリップを受け取り、AudD で曲を認識して `RecognitionResult` を返す。
frontend (Digging の Listen タブ) はこの結果を Record 追加フォームに prefill する。

認証は既存のアプリログイン (`get_current_user`) で保護する。AudD への通信は
RecognitionService が担い、失敗は RecognitionError → http_errors で HTTP 化する。
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
    """録音クリップ (multipart `file`) を AudD で認識して 1 件のマッチを返す。

    マッチしなければ `matched=False`。トークン未設定は 503、上流失敗は 502。
    """
    with http_errors():
        audio = file.file.read()
        return service.recognize(audio, file.content_type)
