from typing import Any, Dict, Generic, List, Optional, Type, TypeVar

import sqlalchemy.exc
from fastapi import APIRouter, Body, HTTPException, Query, Request
from loguru import logger
from src.middlewares import compute_scope_filters
from starlette.responses import Response
from starlette.status import HTTP_201_CREATED

from ._service import BaseService

ServiceT = TypeVar("ServiceT", bound=BaseService)


class BaseController(Generic[ServiceT]):
    def __init__(self, service: Type[ServiceT]):
        self.router = APIRouter()
        self.service = service()

        self.router.post("/", status_code=HTTP_201_CREATED)(self.create)
        self.router.get("/")(self.list)
        self.router.get("/{id}")(self.get)
        self.router.patch("/{id}")(self.patch)
        self.router.delete("/{id}")(self.delete)

    async def _get_scope_filters(self, request: Request) -> Dict[str, Any] | None:
        user = getattr(request.state, "user", None)
        model = self.service.repository.model
        table_name = model.__tablename__
        column_names = {c.key for c in model.__table__.columns}
        return await compute_scope_filters(user, table_name, column_names)

    async def create(self, request: Request, data: dict = Body(...)):
        logger.debug(f"{self.service.repository.model.__name__}: Create called")
        try:
            scope_filters = await self._get_scope_filters(request)
            if scope_filters is not None:
                data.update(scope_filters)
            result = await self.service.create(data)
            return result
        except sqlalchemy.exc.SQLAlchemyError as e:
            logger.warning(f"SQLAlchemy error in create: {e}")
            raise HTTPException(status_code=400, detail="Invalid request data")
        except HTTPException as e:
            logger.warning(e)
            raise e
        except Exception as e:
            logger.exception(e)
            raise HTTPException(status_code=500, detail="Internal server error")

    async def list(
        self,
        request: Request,
        page: int = Query(1, ge=1),
        page_size: int = Query(10, ge=1, le=100),
        order_by: Optional[List[str]] = Query([]),
        search: Optional[str] = Query(None),
    ):
        logger.debug(
            f"{self.service.repository.model.__name__}: List with page: {page}, page_size: {page_size}"
        )
        try:
            filter_by = {}
            if request.query_params:
                filter_by = {
                    k: v
                    for k, v in request.query_params.items()
                    if k not in ["page", "page_size", "order_by", "search"]
                }
            scope_filters = await self._get_scope_filters(request)
            if scope_filters is not None:
                filter_by.update(scope_filters)
            result = await self.service.list(
                page=page,
                page_size=page_size,
                filter_by=filter_by,
                order_by=order_by,
                search=search,
            )
            total_records = await self.service.count(filter_by=filter_by, search=search)
            return {
                "data": result,
                "pagination": {
                    "current_page": page,
                    "page_size": page_size,
                    "total_pages": (total_records + page_size - 1) // page_size,
                    "total_records": total_records,
                },
            }
        except sqlalchemy.exc.SQLAlchemyError as e:
            logger.warning(f"SQLAlchemy error in list: {e}")
            raise HTTPException(status_code=400, detail="Invalid request data")
        except HTTPException as e:
            logger.warning(e)
            raise e
        except Exception as e:
            logger.exception(e)
            raise HTTPException(status_code=500, detail="Internal server error")

    async def get(self, id: int, request: Request):
        logger.debug(f"{self.service.repository.model.__name__}: Get id: {id}")
        try:
            scope_filters = await self._get_scope_filters(request)
            if scope_filters is not None:
                filter_by = {"id": id}
                filter_by.update(scope_filters)
                results = await self.service.list(
                    page=1, page_size=1, filter_by=filter_by
                )
                result = results[0] if results else None
            else:
                result = await self.service.get(id=id)
            if not result:
                raise HTTPException(
                    status_code=404,
                    detail=f"{self.service.repository.model.__name__} not found",
                )
            return result
        except sqlalchemy.exc.SQLAlchemyError as e:
            logger.warning(f"SQLAlchemy error in get: {e}")
            raise HTTPException(status_code=400, detail="Invalid request data")
        except HTTPException as e:
            logger.warning(e)
            raise e
        except Exception as e:
            logger.exception(e)
            raise HTTPException(status_code=500, detail="Internal server error")

    async def patch(self, id: int, request: Request, data: dict = Body(...)):
        logger.debug(f"{self.service.repository.model.__name__}: Patch id: {id}")
        try:
            if not data:
                raise HTTPException(
                    status_code=400,
                    detail="Request body cannot be empty",
                )
            scope_filters = await self._get_scope_filters(request)
            if scope_filters is not None:
                filter_by = {"id": id}
                filter_by.update(scope_filters)
                results = await self.service.list(
                    page=1, page_size=1, filter_by=filter_by
                )
                if not results:
                    raise HTTPException(
                        status_code=404,
                        detail=f"{self.service.repository.model.__name__} not found",
                    )
            result = await self.service.patch(id=id, data=data)
            return result
        except sqlalchemy.exc.SQLAlchemyError as e:
            logger.warning(f"SQLAlchemy error in patch: {e}")
            raise HTTPException(status_code=400, detail="Invalid request data")
        except HTTPException as e:
            logger.warning(e)
            raise e
        except Exception as e:
            logger.exception(e)
            raise HTTPException(status_code=500, detail="Internal server error")

    async def delete(self, id: int, request: Request):
        logger.debug(f"{self.service.repository.model.__name__}: Delete id: {id}")
        try:
            scope_filters = await self._get_scope_filters(request)
            if scope_filters is not None:
                filter_by = {"id": id}
                filter_by.update(scope_filters)
                results = await self.service.list(
                    page=1, page_size=1, filter_by=filter_by
                )
                if not results:
                    raise HTTPException(
                        status_code=404,
                        detail=f"{self.service.repository.model.__name__} not found",
                    )
            await self.service.delete(id=id)
            return Response(status_code=204)
        except sqlalchemy.exc.SQLAlchemyError as e:
            logger.warning(f"SQLAlchemy error in delete: {e}")
            detail = str(e.orig) if hasattr(e, "orig") else str(e)
            if "not found" in detail.lower():
                raise HTTPException(status_code=404, detail="Resource not found")
            raise HTTPException(
                status_code=400,
                detail="Invalid request data",
            )
        except HTTPException as e:
            logger.warning(e)
            raise e
        except Exception as e:
            logger.exception(e)
            raise HTTPException(status_code=500, detail="Internal server error")
