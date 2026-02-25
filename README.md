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

Required permission is inferred from route + method:

- `POST /api/v1/<entity>/` -> `<entity>:create`
- `GET /api/v1/<entity>/` -> `<entity>:list`
- `GET /api/v1/<entity>/{id}` -> `<entity>:read`
- `PUT|PATCH /api/v1/<entity>/{id}` -> `<entity>:update`
- `DELETE /api/v1/<entity>/{id}` -> `<entity>:delete`

JWT can provide:

- direct permissions: `permissions` (e.g. `"orders:*"`, `"*:read"`)
- role mapping: `roles` + `role_permissions`

Example payload:

```json
{
  "sub": "user@example.com",
  "roles": ["manager"],
  "permissions": ["products:read"],
  "role_permissions": {
    "manager": ["orders:*", "products:update"]
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
