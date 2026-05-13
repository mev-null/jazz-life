"""Spotify Authorization Code Flow と JWT セッションの 4 endpoint。

設計詳細は docs/000-pre-adr.md §15 / §F-A1 と plan
(/home/codespace/.claude/plans/memoized-orbiting-lark.md) §設計詳細 5。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse

from app.core.exceptions import AuthError, SpotifyAuthError
from app.core.settings import OAUTH_STATE_COOKIE_NAME, Settings, get_settings
from app.models.user import User
from app.routers.deps import get_auth_service, get_current_user
from app.schemas.auth import AuthUserRead
from app.services.auth_service import AuthService

router = APIRouter(prefix="/api/auth", tags=["auth"])


# OAuth state cookie はコールバックのみで使うため path を絞る。
_STATE_COOKIE_PATH = "/api/auth/callback"


@router.get("/login")
def login(
    auth_service: AuthService = Depends(get_auth_service),
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    state = auth_service.issue_state()
    response = RedirectResponse(
        url=auth_service.build_authorize_url(state),
        status_code=status.HTTP_302_FOUND,
    )
    response.set_cookie(
        key=OAUTH_STATE_COOKIE_NAME,
        value=state,
        max_age=settings.state_ttl_seconds,
        httponly=True,
        samesite=settings.cookie_samesite,  # type: ignore[arg-type]
        secure=settings.cookie_secure,
        path=_STATE_COOKIE_PATH,
    )
    return response


@router.get("/callback")
def callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    auth_service: AuthService = Depends(get_auth_service),
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    if error is not None:
        # ユーザが認可画面で deny した場合などに Spotify が返す
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="authorization denied")
    if not code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="missing code")

    cookie_state = request.cookies.get(OAUTH_STATE_COOKIE_NAME)
    try:
        auth_service.verify_state(state, cookie_state)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    try:
        result = auth_service.complete_callback(code)
    except SpotifyAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    response = RedirectResponse(
        url=settings.frontend_base_url,
        status_code=status.HTTP_302_FOUND,
    )
    response.set_cookie(
        key=settings.cookie_name,
        value=result.session_token,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        samesite=settings.cookie_samesite,  # type: ignore[arg-type]
        secure=settings.cookie_secure,
        path="/",
    )
    response.delete_cookie(key=OAUTH_STATE_COOKIE_NAME, path=_STATE_COOKIE_PATH)
    return response


@router.get("/me", response_model=AuthUserRead)
def me(user: User = Depends(get_current_user)) -> AuthUserRead:
    return AuthUserRead.model_validate(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    settings: Settings = Depends(get_settings),
) -> Response:
    response.delete_cookie(key=settings.cookie_name, path="/")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
