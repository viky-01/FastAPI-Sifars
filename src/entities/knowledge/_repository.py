from ..base import BaseRepository
from ._model import ChunkEmbedding, KnowledgeChunk, KnowledgeRecord


class KnowledgeRepository(BaseRepository):
    def __init__(self):
        super().__init__(KnowledgeRecord)


class KnowledgeChunkRepository(BaseRepository):
    def __init__(self):
        super().__init__(KnowledgeChunk)


class ChunkEmbeddingRepository(BaseRepository):
    def __init__(self):
        super().__init__(ChunkEmbedding)
