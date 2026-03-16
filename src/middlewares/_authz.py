from fnmatch import fnmatch

from starlette.middleware.base import BaseHTTPMiddleware

from fastapi import Request
from fastapi.responses import JSONResponse

from ._public_paths import is_public_path


class AuthorizationMiddleware(BaseHTTPMiddleware):
    _METHOD_ACTION_MAP = {
        "GET": "read",
        "POST": "create",
        "PUT": "update",
        "PATCH": "update",
        "DELETE": "delete",
    }

    def _build_permission_candidates(self, action: str, target_scope: str) -> set[str]:
        action_name = action.strip().lower()
        scope = target_scope.strip().lower()
        return {
            f"{action_name}.{scope}",
            f"{action_name}.*",
            f"*.{scope}",
            "*.*",
        }

    def _normalize_resource_name(self, value: str) -> str:
        return value.strip().lower().replace("-", "_")

    def _normalize_permission_string(self, value: str) -> str:
        permission = str(value).strip().lower()
        if not permission:
            return ""
        if ":" in permission:
            resource, action_scope = permission.split(":", 1)
            return f"{self._normalize_resource_name(resource)}:{action_scope.strip()}"
        if "." in permission:
            resource, action_scope = permission.split(".", 1)
            return f"{self._normalize_resource_name(resource)}:{action_scope.strip()}"
        return permission

    def _is_valid_resource_pattern(self, value: str) -> bool:
        if not value:
            return False
        if value == "*":
            return True
        return all(character.isalnum() or character == "_" for character in value)

    def _is_valid_permission_pattern(self, value: str) -> bool:
        permission = self._normalize_permission_string(value)
        if not permission or ":" not in permission:
            return False

        resource, action_scope = permission.split(":", 1)
        if not self._is_valid_resource_pattern(resource):
            return False
        if "." not in action_scope:
            return False

        action, scope = action_scope.split(".", 1)
        action_allowed = action in {"read", "create", "update", "delete", "*"}
        scope_allowed = scope in {"one", "all", "*"}
        return action_allowed and scope_allowed

    def _is_valid_map_method_pattern(self, value: str) -> bool:
        candidate = str(value).strip().lower()
        if not candidate or "." not in candidate:
            return False
        action, scope = candidate.split(".", 1)
        action_allowed = action in {"read", "create", "update", "delete", "*"}
        scope_allowed = scope in {"one", "all", "*"}
        return action_allowed and scope_allowed

    async def _is_public_path(self, path: str) -> bool:
        return is_public_path(path)

    async def _build_required_permission(
        self, request: Request
    ) -> tuple[str, str, str, str] | None:
        if not request.url.path.startswith("/api/v1/"):
            return None
        parts = request.url.path.strip("/").split("/")
        if len(parts) < 3:
            return None
        resource = parts[2].replace("-", "_")
        method = request.method.upper()
        if method not in self._METHOD_ACTION_MAP:
            return None
        target_scope = "all"
        if method == "GET":
            if len(parts) >= 4:
                action = "read"
                target_scope = "one"
            else:
                action = "read"
                target_scope = "all"
        else:
            action = self._METHOD_ACTION_MAP[method]
            target_scope = "one"
        return resource, method, action, target_scope

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
        keycloak_roles: list[str] = []
        resource_access = payload.get("resource_access")
        if isinstance(resource_access, dict):
            for resource_info in resource_access.values():
                if not isinstance(resource_info, dict):
                    continue
                resource_roles = resource_info.get("roles") or []
                if isinstance(resource_roles, list):
                    keycloak_roles.extend(str(role) for role in resource_roles)
                elif resource_roles:
                    keycloak_roles.append(str(resource_roles))

        realm_access = payload.get("realm_access")
        if isinstance(realm_access, dict):
            realm_roles = realm_access.get("roles") or []
            if isinstance(realm_roles, list):
                keycloak_roles.extend(str(role) for role in realm_roles)
            elif realm_roles:
                keycloak_roles.append(str(realm_roles))

        permissions = [
            self._normalize_permission_string(p)
            for p in [*permissions, *keycloak_roles]
            if str(p).strip() and self._is_valid_permission_pattern(str(p))
        ]
        if not isinstance(permissions_map, dict):
            permissions_map = {}
        normalized_map: dict[str, list[str]] = {}
        for resource, methods in permissions_map.items():
            normalized_resource = self._normalize_resource_name(str(resource))
            if not self._is_valid_resource_pattern(normalized_resource):
                continue
            if isinstance(methods, list):
                normalized_values = [
                    str(m).strip().lower()
                    for m in methods
                    if self._is_valid_map_method_pattern(str(m))
                ]
                normalized_map[normalized_resource] = list(
                    dict.fromkeys(normalized_values)
                )
            elif methods is None:
                normalized_map[normalized_resource] = []
            elif isinstance(methods, dict):
                enabled_values = [
                    str(value).strip().lower()
                    for value, enabled in methods.items()
                    if bool(enabled) and self._is_valid_map_method_pattern(str(value))
                ]
                normalized_map[normalized_resource] = list(
                    dict.fromkeys(enabled_values)
                )
            else:
                normalized_map[normalized_resource] = (
                    [str(methods).strip().lower()]
                    if self._is_valid_map_method_pattern(str(methods))
                    else []
                )
        return permissions, normalized_map

    async def _has_permission(
        self,
        resource: str,
        candidates: set[str],
        permissions: list[str] | None = None,
        permissions_map: dict[str, list[str]] | None = None,
    ) -> bool:
        permissions = permissions or []
        permissions_map = permissions_map or {}
        normalized_resource = self._normalize_resource_name(resource)

        async def has_map_permission(permissions_map: dict[str, list[str]]) -> bool:
            specific_methods = permissions_map.get(normalized_resource) or []
            wildcard_resource_methods = permissions_map.get("*") or []
            return (
                any(candidate in specific_methods for candidate in candidates)
                or "*" in specific_methods
                or any(
                    candidate in wildcard_resource_methods for candidate in candidates
                )
                or "*" in wildcard_resource_methods
            )

        if await has_map_permission(permissions_map):
            return True

        expected_permissions = [
            f"{normalized_resource}:{candidate}" for candidate in sorted(candidates)
        ]
        return any(
            any(
                fnmatch(expected_permission, user_permission)
                for expected_permission in expected_permissions
            )
            for user_permission in permissions
        )

    async def _check_permission(
        self,
        resource: str,
        action: str,
        target_scope: str,
        permissions: list[str],
        permissions_map: dict[str, list[str]],
    ) -> bool:
        broad_candidates = self._build_permission_candidates(action, target_scope)
        return await self._has_permission(
            resource,
            broad_candidates,
            permissions,
            permissions_map,
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
        resource, method, action, target_scope = required_permission
        has_permission = await self._check_permission(
            resource,
            action,
            target_scope,
            permissions,
            permissions_map,
        )
        if not has_permission:
            return JSONResponse(
                status_code=403,
                content={
                    "detail": (
                        "Insufficient permissions: "
                        f"{resource}:{action}.{target_scope} required"
                    )
                },
            )
        return await call_next(request)
