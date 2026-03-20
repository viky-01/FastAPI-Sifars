from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware

from fastapi import Request
from fastapi.responses import JSONResponse
from src.configs import JWTVerificationError, verify_jwt_token

from ._public_paths import is_public_path
from ._user_context import build_user_context_from_payload, set_current_user


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
        if token:
            try:
                payload = verify_jwt_token(token)
            except JWTVerificationError as exc:
                logger.debug(f"JWT verification failed ({exc.code}): {exc}")
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid or expired token"},
                )
            except Exception as exc:
                logger.exception(f"Unexpected error during JWT verification: {exc}")
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Authentication failed"},
                )
        else:
            if request.url.path.startswith("/api/v1/"):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Authentication required"},
                )
            payload = {}
        request.state.jwt_payload = payload
        user_context = build_user_context_from_payload(payload)
        if user_context is None:
            request.state.user = None
            set_current_user(None)
        else:
            set_current_user(user_context)
            request.state.user = user_context
        try:
            if user_context:
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
