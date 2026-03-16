_PUBLIC_PREFIXES = ("/docs", "/redoc", "/openapi.json")
_PUBLIC_EXACT = ("/api/", "/api/health")


def is_public_path(path: str) -> bool:
    return path in _PUBLIC_EXACT or path.startswith(_PUBLIC_PREFIXES)
