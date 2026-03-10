from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional, Type, TypeVar

from sqlalchemy import (
    JSON,
    BigInteger,
    Date,
    Integer,
    Numeric,
    String,
    Text,
    asc,
    cast,
    desc,
    func,
    or_,
)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.future import select
from sqlalchemy.sql import Select

from src.configs import DatabaseConfig

from ._model import BaseModel_

ModelT = TypeVar("ModelT", bound=BaseModel_)


class BaseRepository:
    def __init__(self, model: Type[ModelT]):
        self.model = model

    def _convert_filter_by(self, filter_by: Dict[str, Any]) -> Dict[str, Any]:
        converted = {}
        for k, v in filter_by.items():
            column = self.model.__table__.columns[k]
            col_type = column.type
            if isinstance(col_type, (BigInteger, Integer)):
                try:
                    converted[k] = int(v)
                except ValueError:
                    raise ValueError(f"Invalid integer value for {k}: {v}")
            elif isinstance(col_type, (String, Text)):
                converted[k] = str(v)
            elif isinstance(col_type, Numeric):
                try:
                    converted[k] = float(v)
                except ValueError:
                    raise ValueError(f"Invalid numeric value for {k}: {v}")
            elif isinstance(col_type, Date):
                from datetime import datetime

                try:
                    converted[k] = datetime.strptime(str(v), "%Y-%m-%d").date()
                except ValueError:
                    raise ValueError(f"Invalid date value for {k}: {v}")
            elif isinstance(col_type, JSON):
                import json

                try:
                    converted[k] = json.loads(str(v))
                except json.JSONDecodeError:
                    raise ValueError(f"Invalid JSON value for {k}: {v}")
            else:
                converted[k] = v
        return converted

    def _normalize_search_pattern(self, search: str | None) -> str | None:
        if search is None:
            return None
        value = str(search).strip()
        if not value:
            return None
        if "%" in value or "_" in value:
            return value
        return f"%{value}%"

    def _build_search_predicates(self, search_pattern: str) -> list[Any]:
        return [
            cast(column, String).ilike(search_pattern)
            for column in self.model.__table__.columns
        ]

    @asynccontextmanager
    async def get_session(self):
        async with DatabaseConfig.async_session() as session:
            try:
                yield session
            except SQLAlchemyError as e:
                try:
                    await session.rollback()
                except Exception as e2:
                    print(f"Rollback failed: {e2}")
                raise e

    async def create(self, object: ModelT):
        async with self.get_session() as session:
            session.add(object)
            await session.commit()
            await session.refresh(object)
            return object

    async def list(
        self,
        page: int = 1,
        page_size: int = 10,
        order_by: Optional[List[str]] = None,
        filter_by: Optional[Dict[str, Any]] = None,
        search: str | None = None,
    ):
        column_names = [c.key for c in self.model.__table__.columns]
        filter_by = {k: v for k, v in (filter_by or {}).items() if k in column_names}
        filter_by = self._convert_filter_by(filter_by)
        order_by = [
            field for field in (order_by or []) if field.lstrip("-") in column_names
        ]
        search_pattern = self._normalize_search_pattern(search)
        offset: int = (page - 1) * page_size
        async with self.get_session() as session:
            query: Select[Any] = select(self.model).filter_by(**filter_by)
            if search_pattern:
                query = query.where(or_(*self._build_search_predicates(search_pattern)))
            query = query.offset(offset).limit(page_size)
            for field in order_by:
                if field.startswith("-"):
                    query = query.order_by(desc(getattr(self.model, field[1:])))
                else:
                    query = query.order_by(asc(getattr(self.model, field)))
            result = await session.execute(query)
            return [item for item in result.scalars().all()]

    async def get(self, id: int):
        async with self.get_session() as session:
            result = await session.get(self.model, id)
            return result

    async def patch(self, id: int, **kwargs: Dict[str, Any]):
        async with self.get_session() as session:
            instance = await session.get(self.model, id)
            if not instance:
                raise SQLAlchemyError(f"{self.model.__name__} not found with id {id}")
            column_names = [c.key for c in self.model.__table__.columns]
            for key, value in kwargs.items():
                if key not in column_names:
                    raise SQLAlchemyError(f"Invalid field: {key}")
                setattr(instance, key, value)
            await session.commit()
            await session.refresh(instance)
            return instance

    async def delete(self, id: int):
        async with self.get_session() as session:
            instance = await session.get(self.model, id)
            if not instance:
                raise SQLAlchemyError(f"{self.model.__name__} not found with id {id}")
            await session.delete(instance)
            await session.commit()

    async def count(
        self,
        filter_by: Optional[Dict[str, Any]] = None,
        search: str | None = None,
    ):
        column_names = [c.key for c in self.model.__table__.columns]
        filter_by = {k: v for k, v in (filter_by or {}).items() if k in column_names}
        filter_by = self._convert_filter_by(filter_by)
        search_pattern = self._normalize_search_pattern(search)
        async with self.get_session() as session:
            query: Select[Any] = (
                select(func.count()).select_from(self.model).filter_by(**filter_by)
            )
            if search_pattern:
                query = query.where(or_(*self._build_search_predicates(search_pattern)))
            result = await session.execute(query)
            return result.scalar_one() or 0

    async def execute(self, query: Any):
        async with self.get_session() as session:
            result = await session.execute(query)
            return result
