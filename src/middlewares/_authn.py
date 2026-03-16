from fastapi import Request
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware

from src.configs import verify_jwt_token

from ._public_paths import is_public_path
from ._user_context import (
    UserContext,
    build_user_context_from_payload,
    set_current_user,
)


class AuthenticationMiddleware(BaseHTTPMiddleware):

    def _extract_bearer_token(self, authorization_header: str) -> str:
        if not authorization_header:
            return ""
        raw = authorization_header.strip()
        if not raw:
            return ""
        if " " not in raw:
            return ""
        scheme, token = raw.split(" ", 1)
        if scheme.lower() != "bearer":
            return ""
        token = token.strip()
        if token.lower().startswith("bearer "):
            return ""
        return token

    async def _is_public_path(self, path: str) -> bool:
        return is_public_path(path)

    async def dispatch(self, request: Request, call_next):
        if await self._is_public_path(request.url.path):
            return await call_next(request)
        token = self._extract_bearer_token(request.headers.get("Authorization", ""))
        payload = verify_jwt_token(token) if token else {}
        request.state.jwt_payload = payload
        user_context = build_user_context_from_payload(payload)
        if user_context is None:
            user_context = UserContext(user_id="system")
        set_current_user(user_context)
        request.state.user = user_context
        try:
            if user_context.user_id != "system":
                logger.debug(
                    f"Authenticated request: {request.method} {request.url.path} by {user_context.user_id}"
                )
            else:
                logger.debug(
                    f"Unauthenticated request: {request.method} {request.url.path}"
                )
            return await call_next(request)
        finally:
            set_current_user(None)
