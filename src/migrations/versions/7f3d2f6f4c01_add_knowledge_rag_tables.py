"""add knowledge rag tables

Revision ID: 7f3d2f6f4c01
Revises: 0af612617347
Create Date: 2026-03-26 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7f3d2f6f4c01"
down_revision: Union[str, None] = "0af612617347"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.create_table(
        "knowledge_records",
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "knowledge_chunks",
        sa.Column("knowledge_id", sa.Integer(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["knowledge_id"], ["knowledge_records.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_knowledge_chunks_knowledge_id"), "knowledge_chunks", ["knowledge_id"], unique=False)

    op.create_table(
        "chunk_embeddings",
        sa.Column("chunk_id", sa.Integer(), nullable=False),
        sa.Column("pinecone_vector_id", sa.String(length=255), nullable=False),
        sa.Column("embedding_model", sa.String(length=100), nullable=False),
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["chunk_id"], ["knowledge_chunks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chunk_id"),
        sa.UniqueConstraint("pinecone_vector_id"),
    )
    op.create_index(op.f("ix_chunk_embeddings_chunk_id"), "chunk_embeddings", ["chunk_id"], unique=True)
    op.create_index(op.f("ix_chunk_embeddings_pinecone_vector_id"), "chunk_embeddings", ["pinecone_vector_id"], unique=True)


def downgrade():
    op.drop_index(op.f("ix_chunk_embeddings_pinecone_vector_id"), table_name="chunk_embeddings")
    op.drop_index(op.f("ix_chunk_embeddings_chunk_id"), table_name="chunk_embeddings")
    op.drop_table("chunk_embeddings")

    op.drop_index(op.f("ix_knowledge_chunks_knowledge_id"), table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")

    op.drop_table("knowledge_records")
