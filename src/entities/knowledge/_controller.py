from fastapi import Body, HTTPException

from ..base import BaseController
from ._schema import AskRequestSchema
from ._service import KnowledgeService


class KnowledgeController(BaseController):
    def __init__(self):
        super().__init__(KnowledgeService)
        self.router.put("/{id}")(self.put)
        self.router.post("/ask")(self.ask)

    async def put(self, id: int, data: dict = Body(...)):
        try:
            if not data:
                raise HTTPException(status_code=400, detail="Request body cannot be empty")
            return await self.service.patch(id=id, data=data)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    async def ask(self, payload: AskRequestSchema):
        try:
            return await self.service.ask(question=payload.question, top_k=payload.top_k)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
