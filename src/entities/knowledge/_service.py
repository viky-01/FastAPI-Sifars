import os
from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.configs import DatabaseConfig

from ..base import BaseService
from ._model import ChunkEmbedding, KnowledgeChunk, KnowledgeRecord
from ._repository import ChunkEmbeddingRepository, KnowledgeChunkRepository, KnowledgeRepository


class KnowledgeService(BaseService):
    def __init__(self):
        super().__init__(KnowledgeRepository)
        self.chunk_repository = KnowledgeChunkRepository()
        self.embedding_repository = ChunkEmbeddingRepository()

    def _chunk_text(self, text: str, chunk_size: int = 900, overlap: int = 120) -> List[str]:
        normalized = " ".join(text.split())
        if len(normalized) <= chunk_size:
            return [normalized]

        chunks: List[str] = []
        start = 0
        while start < len(normalized):
            end = min(start + chunk_size, len(normalized))
            chunks.append(normalized[start:end])
            if end == len(normalized):
                break
            start = max(0, end - overlap)
        return chunks

    def _get_embedding(self, input_text: str) -> List[float]:
        from google import genai

        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured")

        client = genai.Client(api_key=api_key)
        response = client.models.embed_content(
            model=os.getenv("GEMINI_EMBED_MODEL", "gemini-embedding-001"),
            contents=input_text,
        )
        return list(response.embeddings[0].values)

    def _get_pinecone_index(self):
        from pinecone import Pinecone

        api_key = os.getenv("PINECONE_API_KEY")
        index_name = os.getenv("PINECONE_INDEX_NAME")

        if not api_key or not index_name:
            raise RuntimeError("PINECONE_API_KEY and PINECONE_INDEX_NAME are required")

        client = Pinecone(api_key=api_key)
        return client.Index(index_name)

    async def _upsert_chunks_and_embeddings(self, knowledge: KnowledgeRecord) -> None:
        chunks = self._chunk_text(knowledge.content)
        index = self._get_pinecone_index()
        embed_model = os.getenv("GEMINI_EMBED_MODEL", "gemini-embedding-001")

        for idx, chunk in enumerate(chunks):
            chunk_row = await self.chunk_repository.create(
                object=KnowledgeChunk(
                    knowledge_id=knowledge.id,
                    chunk_index=idx,
                    chunk_text=chunk,
                )
            )
            embedding_values = self._get_embedding(chunk)
            vector_id = f"knowledge-{knowledge.id}-chunk-{chunk_row.id}"
            index.upsert(
                vectors=[
                    {
                        "id": vector_id,
                        "values": embedding_values,
                        "metadata": {
                            "knowledge_id": knowledge.id,
                            "chunk_id": chunk_row.id,
                        },
                    }
                ]
            )
            await self.embedding_repository.create(
                object=ChunkEmbedding(
                    chunk_id=chunk_row.id,
                    pinecone_vector_id=vector_id,
                    embedding_model=embed_model,
                )
            )

    async def create(self, data: dict):
        knowledge = await super().create(data)
        await self._upsert_chunks_and_embeddings(knowledge)
        return knowledge

    async def patch(self, id: int, data: dict):
        knowledge = await super().patch(id=id, data=data)
        if "content" in data:
            await self.reindex_knowledge(knowledge.id)
            knowledge = await self.get(id=id)
        return knowledge

    async def reindex_knowledge(self, knowledge_id: int) -> None:
        index = self._get_pinecone_index()
        async with DatabaseConfig.async_session() as session:
            result = await session.execute(
                select(KnowledgeChunk)
                .options(selectinload(KnowledgeChunk.embedding))
                .where(KnowledgeChunk.knowledge_id == knowledge_id)
            )
            current_chunks = list(result.scalars().all())

            for chunk in current_chunks:
                if chunk.embedding:
                    index.delete(ids=[chunk.embedding.pinecone_vector_id])

            for chunk in current_chunks:
                await session.delete(chunk)

            knowledge = await session.get(KnowledgeRecord, knowledge_id)
            if not knowledge:
                return

            fresh_chunks = self._chunk_text(knowledge.content)
            embed_model = os.getenv("GEMINI_EMBED_MODEL", "gemini-embedding-001")
            for idx, chunk_text in enumerate(fresh_chunks):
                chunk = KnowledgeChunk(
                    knowledge_id=knowledge.id,
                    chunk_index=idx,
                    chunk_text=chunk_text,
                )
                session.add(chunk)
                await session.flush()

                embedding_values = self._get_embedding(chunk_text)
                vector_id = f"knowledge-{knowledge.id}-chunk-{chunk.id}"
                index.upsert(
                    vectors=[
                        {
                            "id": vector_id,
                            "values": embedding_values,
                            "metadata": {
                                "knowledge_id": knowledge.id,
                                "chunk_id": chunk.id,
                            },
                        }
                    ]
                )
                session.add(
                    ChunkEmbedding(
                        chunk_id=chunk.id,
                        pinecone_vector_id=vector_id,
                        embedding_model=embed_model,
                    )
                )

    async def delete(self, id: int):
        index = self._get_pinecone_index()
        async with DatabaseConfig.async_session() as session:
            result = await session.execute(
                select(ChunkEmbedding.pinecone_vector_id)
                .join(KnowledgeChunk, ChunkEmbedding.chunk_id == KnowledgeChunk.id)
                .where(KnowledgeChunk.knowledge_id == id)
            )
            vector_ids = [row[0] for row in result.all()]
            if vector_ids:
                index.delete(ids=vector_ids)

        await super().delete(id=id)

    async def ask(self, question: str, top_k: int = 5) -> Dict[str, Any]:
        from google import genai

        question_embedding = self._get_embedding(question)
        index = self._get_pinecone_index()

        query_result = index.query(vector=question_embedding, top_k=top_k, include_metadata=True)
        matches = query_result.get("matches", [])

        sources: List[Dict[str, Any]] = []
        context_parts: List[str] = []

        async with DatabaseConfig.async_session() as session:
            for match in matches:
                metadata = match.get("metadata", {})
                chunk_id = metadata.get("chunk_id")
                if not chunk_id:
                    continue

                chunk_result = await session.execute(
                    select(KnowledgeChunk, KnowledgeRecord)
                    .join(KnowledgeRecord, KnowledgeChunk.knowledge_id == KnowledgeRecord.id)
                    .where(KnowledgeChunk.id == int(chunk_id))
                )
                row = chunk_result.first()
                if not row:
                    continue

                chunk, knowledge = row
                score = float(match.get("score", 0.0))
                context_parts.append(f"[{knowledge.title}] {chunk.chunk_text}")
                sources.append(
                    {
                        "chunk_id": chunk.id,
                        "knowledge_id": knowledge.id,
                        "title": knowledge.title,
                        "score": score,
                        "chunk_text": chunk.chunk_text,
                    }
                )

        context = "\n\n".join(context_parts)
        prompt = (
            "You are a retrieval-augmented assistant. Answer with only the provided context. "
            "If the context is insufficient, explicitly say so.\n\n"
            f"Question: {question}\n\n"
            f"Context:\n{context}"
        )

        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured")

        client = genai.Client(api_key=api_key)
        answer_response = client.models.generate_content(
            model=os.getenv("GEMINI_CHAT_MODEL", "gemini-2.0-flash"),
            contents=prompt,
        )

        return {
            "answer": answer_response.text,
            "sources": sorted(sources, key=lambda x: x["score"], reverse=True),
        }
