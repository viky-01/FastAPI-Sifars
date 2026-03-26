from sqlalchemy import Column, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from ..base import BaseModel_


class KnowledgeRecord(BaseModel_):
    __tablename__ = "knowledge_records"

    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)

    chunks = relationship(
        "KnowledgeChunk", back_populates="knowledge", cascade="all, delete-orphan"
    )


class KnowledgeChunk(BaseModel_):
    __tablename__ = "knowledge_chunks"

    knowledge_id = Column(
        Integer,
        ForeignKey("knowledge_records.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index = Column(Integer, nullable=False)
    chunk_text = Column(Text, nullable=False)

    knowledge = relationship("KnowledgeRecord", back_populates="chunks")
    embedding = relationship(
        "ChunkEmbedding", back_populates="chunk", uselist=False, cascade="all, delete-orphan"
    )


class ChunkEmbedding(BaseModel_):
    __tablename__ = "chunk_embeddings"

    chunk_id = Column(
        Integer,
        ForeignKey("knowledge_chunks.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    pinecone_vector_id = Column(String(255), nullable=False, unique=True, index=True)
    embedding_model = Column(String(100), nullable=False, default="gemini-embedding-001")

    chunk = relationship("KnowledgeChunk", back_populates="embedding")
