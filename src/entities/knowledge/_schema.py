from typing import List

from pydantic import Field

from ..base import BaseSchema


class KnowledgeCreateSchema(BaseSchema):
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1)


class KnowledgeUpdateSchema(BaseSchema):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    content: str | None = Field(default=None, min_length=1)


class KnowledgeResponseSchema(BaseSchema):
    id: int
    title: str
    content: str


class AskRequestSchema(BaseSchema):
    question: str = Field(min_length=2)
    top_k: int = Field(default=5, ge=1, le=20)


class AskSourceSchema(BaseSchema):
    chunk_id: int
    knowledge_id: int
    title: str
    score: float
    chunk_text: str


class AskResponseSchema(BaseSchema):
    answer: str
    sources: List[AskSourceSchema]
