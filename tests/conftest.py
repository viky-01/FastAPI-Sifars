from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import AsyncGenerator, Dict

import jwt
import pytest
from dotenv import load_dotenv
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

load_dotenv(Path(__file__).resolve().parents[1] / ".env.test", override=True)

from src.app import app
from src.configs._database import DatabaseConfig, get_db_session
from src.entities.base._model import BaseModel_


@pytest.fixture(scope="session")
async def test_engine() -> AsyncGenerator[AsyncEngine, None]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
    )

    DatabaseConfig._thread_local.engine = engine
    DatabaseConfig._thread_local.session_factory = async_sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(BaseModel_.metadata.create_all)

    yield engine

    if hasattr(DatabaseConfig._thread_local, "session_factory"):
        delattr(DatabaseConfig._thread_local, "session_factory")
    if hasattr(DatabaseConfig._thread_local, "engine"):
        delattr(DatabaseConfig._thread_local, "engine")

    await engine.dispose()


@pytest.fixture(scope="function")
async def test_db(test_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    async_session = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        session.info["user"] = "test_user"
        yield session
        await session.rollback()


@pytest.fixture
async def client(test_db: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db_session():
        yield test_db

    app.dependency_overrides[get_db_session] = override_get_db_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture
def auth_token_admin() -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=1)
    payload = {
        "sub": "admin@test.com",
        "email": "admin@test.com",
        "roles": ["admin"],
        "exp": int(exp.timestamp()),
        "permissions": ["*:*.*"],
    }
    return jwt.encode(payload, "test-secret", algorithm="HS256")


@pytest.fixture
def auth_token_user() -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=1)
    payload = {
        "sub": "user@test.com",
        "email": "user@test.com",
        "roles": ["user"],
        "exp": int(exp.timestamp()),
        "permissions": ["*:read.*"],
        "permissions_map": {"*": ["read.*"]},
    }
    return jwt.encode(payload, "test-secret", algorithm="HS256")


@pytest.fixture
def auth_headers_admin(auth_token_admin: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {auth_token_admin}"}


@pytest.fixture
def auth_headers_user(auth_token_user: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {auth_token_user}"}
