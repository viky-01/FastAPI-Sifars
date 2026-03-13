# FastAPI Template

Production-ready FastAPI template with:

- Generated CRUD layers
- Middleware-based JWT authorization
- Auto audit logging
- Async test setup

## Quick Start

1. Install deps

```bash
poetry install
```

2. Set env in `.env`

```env
SQLALCHEMY_DATABASE_URI=sqlite+aiosqlite:///./test.db
CORS_ALLOW_ORIGINS=http://localhost:3000,http://localhost:8000
```

3. Run app

```bash
python main.py
```

Open docs: `http://127.0.0.1:8000/docs`

## Create New Entity

1. Add model in `src/entities/<entity>/_model.py`
2. Run:

```bash
python generate_cruds.py
```

This generates `_repository.py`, `_service.py`, `_controller.py`, `_schema.py`.

## Authorization (Plug-and-Play)

Authorization is enforced centrally in middleware from JWT claims.
No per-controller permission wiring required.

JWT signature verification is configurable for different identity providers.

Required permission is inferred from route + method:

- `POST /api/v1/<entity>/` -> `<entity>:create.one`
- `GET /api/v1/<entity>/` -> `<entity>:read.all`
- `GET /api/v1/<entity>/{id}` -> `<entity>:read.one`
- `PUT|PATCH /api/v1/<entity>/{id}` -> `<entity>:update.one`
- `DELETE /api/v1/<entity>/{id}` -> `<entity>:delete.one`

Permission format conventions:

- Canonical format: `<resource>:<action>.<scope>` (e.g. `audit_logs:read.all`)
- Also accepted as input: `<resource>.<action>.<scope>` (normalized internally)
- Allowed `action`: `read | create | update | delete | *`
- Allowed `scope`: `one | all | *`

### JWT verification config

Supported providers:

- `shared_secret` (HS256-style)
- `public_key` (static PEM public key)
- `jwks` (OIDC/JWKS endpoint, ideal for Keycloak/Auth0/Cognito)
- `auto` (infers `jwks`/`public_key`/`shared_secret` from env)

Relevant env vars:

- `JWT_PROVIDER` = `shared_secret` | `public_key` | `jwks` | `auto`
- `JWT_ALGORITHMS` (comma-separated, e.g. `RS256` or `HS256`)
- `JWT_SECRET` (required for `shared_secret`)
- `JWT_PUBLIC_KEY` (required for `public_key`)
- `JWT_JWKS_URL` (required for `jwks` unless `JWT_ISSUER` is set)
- `JWT_JWKS_TIMEOUT_MS` (optional, default `3000`)
- `JWT_JWKS_CACHE_TTL_SEC` (optional, default `300`)
- `JWT_JWKS_CACHE_MAX_KEYS` (optional, default `100`)
- `JWT_ISSUER` (optional but recommended)
- `JWT_AUDIENCE` (optional but recommended)
- `JWT_REQUIRE_EXP` (default `true`)
- `JWT_VERIFY_NBF` (default `true`)
- `JWT_VERIFY_IAT` (default `false`)

#### Keycloak example

```env
JWT_PROVIDER=jwks
JWT_ALGORITHMS=RS256
JWT_JWKS_URL=https://<keycloak-host>/realms/<realm>/protocol/openid-connect/certs
JWT_ISSUER=https://<keycloak-host>/realms/<realm>
JWT_AUDIENCE=<client-id>
JWT_REQUIRE_EXP=true
```

JWT can provide:

- direct permissions: `permissions` (e.g. `"orders:read.all"`, `"*:read.all"`, `"orders:*.*"`)
- resource-method mapping: `permissions_map` or `permissions_by_resource` (e.g. `"orders": ["read.all", "update.one", "*.*"]`)

Example payload:

```json
{
  "sub": "user@example.com",
  "permissions": ["products:read.one", "orders:read.all"],
  "permissions_map": {
    "orders": ["read.all"],
    "products": ["read.one", "update.one"]
  }
}
```

## Testing

Run tests:

```bash
pytest -v
```

Base reusable entity test class:

- `tests/base_entity_api_test.py`

Example implementation:

- `tests/test_test_entity.py`

## Notes

- Audit logs are automatic via SQLAlchemy events.
- Migrations run on startup.
- Supported DBs: PostgreSQL, MySQL, SQLite.

## JWT verification at scale

Token validation is performed per protected request, but verification is local in the API process.

- `JWT_PROVIDER=shared_secret`: signature verification uses `JWT_SECRET` locally.
- `JWT_PROVIDER=public_key`: signature verification uses `JWT_PUBLIC_KEY` locally.
- `JWT_PROVIDER=jwks`: token is still verified locally; JWKS endpoint is used only to resolve public keys (typically cached, fetched on miss/rotation).

This means the app does **not** call the identity provider for full token introspection on every request by default.

### Production recommendations

- Prefer `jwks` for Keycloak/Auth0/Cognito to support key rotation.
- Set `JWT_ISSUER` and `JWT_AUDIENCE` in production.
- Keep `JWT_REQUIRE_EXP=true`.
- Use short-lived access tokens and refresh-token flow.
- Scale API workers by request throughput (JWT verification is usually not the primary bottleneck compared to DB/business logic).
