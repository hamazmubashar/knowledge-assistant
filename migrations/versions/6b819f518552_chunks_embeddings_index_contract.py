"""chunks embeddings index contract

Revision ID: 6b819f518552
Revises: 031dbfec18c5
Create Date: 2026-10-08 12:21:33.302594

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import pgvector.sqlalchemy
from sqlalchemy.dialects import postgresql

revision: str = '6b819f518552'
down_revision: Union[str, Sequence[str], None] = '031dbfec18c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table('embedding_indexes',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('model_name', sa.String(length=200), nullable=False),
    sa.Column('dimensions', sa.Integer(), nullable=False),
    sa.Column('status', sa.Enum('building', 'active', 'retired', name='indexstatus', native_enum=False, create_constraint=True, length=20), server_default='building', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('activated_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('model_name', 'dimensions')
    )
    op.create_index('uq_one_active_index', 'embedding_indexes', ['status'], unique=True, postgresql_where=sa.text("status = 'active'"))

    op.create_table('chunks',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('version_id', sa.UUID(), nullable=False),
    sa.Column('page_id', sa.UUID(), nullable=False),
    sa.Column('page_number', sa.Integer(), nullable=False),
    sa.Column('chunk_index', sa.Integer(), nullable=False),
    sa.Column('heading', sa.Text(), nullable=True),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('token_count', sa.Integer(), nullable=False),
    sa.Column('access_group', sa.Enum('general', 'support', 'operations', 'hr', name='accessgroup', native_enum=False, create_constraint=True, length=20), nullable=False),
    sa.Column('extraction_method', sa.Enum('pymupdf', 'ocr', name='extractionmethod', native_enum=False, create_constraint=True, length=20), nullable=False),
    sa.Column('low_confidence', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('search_vector', postgresql.TSVECTOR(), sa.Computed("to_tsvector('english', coalesce(heading, '') || ' ' || text)", persisted=True), nullable=False),
    sa.ForeignKeyConstraint(['page_id'], ['pages.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['version_id'], ['document_versions.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('version_id', 'chunk_index')
    )
    op.create_index(op.f('ix_chunks_access_group'), 'chunks', ['access_group'], unique=False)
    op.create_index('ix_chunks_search_vector', 'chunks', ['search_vector'], unique=False, postgresql_using='gin')
    op.create_index(op.f('ix_chunks_version_id'), 'chunks', ['version_id'], unique=False)

    op.create_table('embeddings',
    sa.Column('chunk_id', sa.UUID(), nullable=False),
    sa.Column('index_id', sa.Integer(), nullable=False),
    sa.Column('embedding', pgvector.sqlalchemy.vector.VECTOR(dim=384), nullable=False),
    sa.ForeignKeyConstraint(['chunk_id'], ['chunks.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['index_id'], ['embedding_indexes.id'], ),
    sa.PrimaryKeyConstraint('chunk_id', 'index_id')
    )
    op.create_index('ix_embeddings_hnsw', 'embeddings', ['embedding'], unique=False, postgresql_using='hnsw', postgresql_ops={'embedding': 'vector_cosine_ops'})

    op.add_column('pages', sa.Column('ocr_confidence', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('pages', 'ocr_confidence')
    op.drop_index('ix_embeddings_hnsw', table_name='embeddings', postgresql_using='hnsw', postgresql_ops={'embedding': 'vector_cosine_ops'})
    op.drop_table('embeddings')
    op.drop_index(op.f('ix_chunks_version_id'), table_name='chunks')
    op.drop_index('ix_chunks_search_vector', table_name='chunks', postgresql_using='gin')
    op.drop_index(op.f('ix_chunks_access_group'), table_name='chunks')
    op.drop_table('chunks')
    op.drop_index('uq_one_active_index', table_name='embedding_indexes', postgresql_where=sa.text("status = 'active'"))
    op.drop_table('embedding_indexes')