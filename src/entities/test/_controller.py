from fastapi import Body

from ..base import BaseController
from ._schema import TestSchema
from ._service import TestService


class TestController(BaseController):
    def __init__(self):
        super().__init__(TestService)

    async def create(self, data: TestSchema = Body(...)):
        return await super().create(data.model_dump())

    async def patch(self, id: int, data: dict = Body(...)):
        return await super().patch(id, data)
