from typing import Generic, List, Optional, Type, TypeVar

import sqlalchemy.exc
from fastapi import APIRouter, Body, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from loguru import logger

from ._service import BaseService

ServiceT = TypeVar("ServiceT", bound=BaseService)


class BaseController(Generic[ServiceT]):
    def __init__(self, service: Type[ServiceT]):
        self.router = APIRouter()
        self.service = service()

        self.router.post("/")(self.create)
        self.router.get("/")(self.list)
        self.router.get("/{id}")(self.get)
        self.router.patch("/{id}")(self.patch)
        self.router.delete("/{id}")(self.delete)

    async def create(self, data: dict = Body(...)):
        logger.debug(
            f"{self.service.repository.model.__name__}: Create with data: {data}"
        )
        try:
            result = await self.service.create(data)
            return result
        except sqlalchemy.exc.SQLAlchemyError as e:
            logger.warning(e)
            raise HTTPException(
                status_code=400, detail=str(e.orig) if hasattr(e, "orig") else str(e)
            )
        except HTTPException as e:
            logger.warning(e)
            raise e
        except Exception as e:
            logger.exception(e)
            raise HTTPException(status_code=500, detail=str(e))

    async def list(
        self,
        request: Request,
        page: int = Query(1, ge=1),
        page_size: int = Query(10, ge=1, le=100),
        order_by: Optional[List[str]] = Query([]),
    ):
        logger.debug(
            f"{self.service.repository.model.__name__}: List with page: {page}, page_size: {page_size}, order_by: {order_by}, query_params: {request.query_params}"
        )
        try:
            filter_by = {}
            if request.query_params:
                filter_by = {
                    k: v
                    for k, v in request.query_params.items()
                    if k not in ["page", "page_size", "order_by"]
                }
            result = await self.service.list(
                page=page, page_size=page_size, filter_by=filter_by, order_by=order_by
            )
            total_records = await self.service.count(filter_by=filter_by)
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
            logger.warning(e)
            raise HTTPException(
                status_code=400, detail=str(e.orig) if hasattr(e, "orig") else str(e)
            )
        except HTTPException as e:
            logger.warning(e)
            raise e
        except Exception as e:
            logger.exception(e)
            raise HTTPException(status_code=500, detail=str(e))

    async def get(self, id: int):
        logger.debug(f"{self.service.repository.model.__name__}: Get id: {id}")
        try:
            result = await self.service.get(id=id)
            if not result:
                raise HTTPException(
                    status_code=404,
                    detail=f"{self.service.repository.model.__name__} not found",
                )
            return result
        except sqlalchemy.exc.SQLAlchemyError as e:
            logger.warning(e)
            raise HTTPException(
                status_code=400, detail=str(e.orig) if hasattr(e, "orig") else str(e)
            )
        except HTTPException as e:
            logger.warning(e)
            raise e
        except Exception as e:
            logger.exception(e)
            raise HTTPException(status_code=500, detail=str(e))

    async def patch(self, id: int, data: dict = Body(...)):
        logger.debug(
            f"{self.service.repository.model.__name__}: Patch id: {id} with data: {data}"
        )
        try:
            if not data:
                raise HTTPException(
                    status_code=400,
                    detail="Request body cannot be empty",
                )
            result = await self.service.patch(id=id, data=data)
            return result
        except sqlalchemy.exc.SQLAlchemyError as e:
            logger.warning(e)
            raise HTTPException(
                status_code=400, detail=str(e.orig) if hasattr(e, "orig") else str(e)
            )
        except HTTPException as e:
            logger.warning(e)
            raise e
        except Exception as e:
            logger.exception(e)
            raise HTTPException(status_code=500, detail=str(e))

    async def delete(self, id: int):
        logger.debug(f"{self.service.repository.model.__name__}: Delete id: {id}")
        try:
            await self.service.delete(id=id)
            return JSONResponse(status_code=204, content=None)
        except sqlalchemy.exc.SQLAlchemyError as e:
            logger.warning(e)
            detail = str(e.orig) if hasattr(e, "orig") else str(e)
            if "not found" in detail.lower():
                raise HTTPException(status_code=404, detail=detail)
            raise HTTPException(
                status_code=400,
                detail=detail,
            )
        except HTTPException as e:
            logger.warning(e)
            raise e
        except Exception as e:
            logger.exception(e)
            raise HTTPException(status_code=500, detail=str(e))
