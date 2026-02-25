from fastapi import Request
from jwt import decode
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware

from ._user_context import (
    UserContext,
    build_user_context_from_payload,
    set_current_user,
)


class AuthenticationMiddleware(BaseHTTPMiddleware):
    _PUBLIC_PREFIXES = ("/docs", "/redoc", "/openapi.json")

    async def _is_public_path(self, path: str) -> bool:
        return path == "/api/" or path.startswith(self._PUBLIC_PREFIXES)

    async def dispatch(self, request: Request, call_next):
        if await self._is_public_path(request.url.path):
            return await call_next(request)
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        payload = {}
        if token:
            try:
                payload = decode(token, options={"verify_signature": False})
            except Exception:
                payload = {}
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
