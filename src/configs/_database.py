import os
import threading
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.middlewares import get_current_user


class DatabaseConfig:
    _thread_local = threading.local()

    @classmethod
    def get_engine(cls):
        if not hasattr(cls._thread_local, "engine"):
            cls._thread_local.engine = create_async_engine(
                url=os.getenv("SQLALCHEMY_DATABASE_URI"),
                pool_recycle=1800,
                pool_size=5,
                max_overflow=45,
                pool_pre_ping=True,
                pool_timeout=60,
            )
        return cls._thread_local.engine

    @classmethod
    def _get_session_factory(cls):
        if not hasattr(cls._thread_local, "session_factory"):
            cls._thread_local.session_factory = async_sessionmaker(
                bind=cls.get_engine(),
                autoflush=False,
                autocommit=False,
                expire_on_commit=False,
            )
        return cls._thread_local.session_factory

    @classmethod
    @asynccontextmanager
    async def async_session(cls):
        session_factory = cls._get_session_factory()
        async with session_factory() as session:
            session.info["user"] = get_current_user().user_id
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()


async def get_db_session():
    async with DatabaseConfig.async_session() as session:
        yield session
