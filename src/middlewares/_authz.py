from fnmatch import fnmatch

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


class AuthorizationMiddleware(BaseHTTPMiddleware):
    _PUBLIC_PREFIXES = ("/docs", "/redoc", "/openapi.json")

    async def _is_public_path(self, path: str) -> bool:
        return path == "/api/" or path.startswith(self._PUBLIC_PREFIXES)

    async def _build_required_permission(
        self, request: Request
    ) -> tuple[str, str] | None:
        if not request.url.path.startswith("/api/v1/"):
            return None
        parts = request.url.path.strip("/").split("/")
        if len(parts) < 3:
            return None
        resource = parts[2].replace("-", "_")
        method = request.method.upper()
        if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
            return None
        return resource, method

    async def _extract_permissions(
        self, payload: dict
    ) -> tuple[list[str], dict[str, list[str]]]:
        permissions = payload.get("permissions") or []
        permissions_map = (
            payload.get("permissions_map")
            or payload.get("permissions_by_resource")
            or {}
        )
        if isinstance(permissions, dict):
            permissions_map = permissions
            permissions = []
        if not isinstance(permissions, list):
            permissions = [permissions] if permissions else []
        permissions = [str(p) for p in permissions]
        if not isinstance(permissions_map, dict):
            permissions_map = {}
        normalized_map: dict[str, list[str]] = {}
        for resource, methods in permissions_map.items():
            if isinstance(methods, list):
                normalized_map[str(resource)] = [str(m).upper() for m in methods]
            elif methods is None:
                normalized_map[str(resource)] = []
            else:
                normalized_map[str(resource)] = [str(methods).upper()]
        return permissions, normalized_map

    async def check_permission(
        self,
        resource: str,
        method: str,
        permissions: list[str] | None = None,
        permissions_map: dict[str, list[str]] | None = None,
    ) -> bool:
        method = method.upper()
        permissions = permissions or []
        permissions_map = permissions_map or {}

        async def has_map_permission(permissions_map: dict[str, list[str]]) -> bool:
            specific_methods = permissions_map.get(resource) or []
            wildcard_resource_methods = permissions_map.get("*") or []
            return (
                method in specific_methods
                or "*" in specific_methods
                or method in wildcard_resource_methods
                or "*" in wildcard_resource_methods
            )

        if await has_map_permission(permissions_map):
            return True

        expected_permission = f"{resource}:{method}"
        return any(
            fnmatch(expected_permission, user_permission)
            for user_permission in permissions
        )

    async def dispatch(self, request: Request, call_next):
        if await self._is_public_path(request.url.path):
            return await call_next(request)
        required_permission = await self._build_required_permission(request)
        if required_permission is None:
            return await call_next(request)
        user = getattr(request.state, "user", None)
        if user is None or user.user_id == "system":
            return JSONResponse(
                status_code=401,
                content={"detail": "Authentication required"},
            )
        payload = getattr(request.state, "jwt_payload", None) or {}
        permissions, permissions_map = await self._extract_permissions(payload)
        resource, method = required_permission
        if not await self.check_permission(
            resource, method, permissions, permissions_map
        ):
            return JSONResponse(
                status_code=403,
                content={
                    "detail": f"Insufficient permissions: {resource}:{method} required"
                },
            )
        return await call_next(request)
