"""retrieval: question embeddings, schema hash, feedback, data dictionary

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-05
"""
from alembic import op
import sqlalchemy as sa


revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None

DIM = 384


def upgrade():
    postgres = op.get_bind().dialect.name == "postgresql"
    if postgres:
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
        from pgvector.sqlalchemy import Vector
        embedding_type = Vector(DIM)
    else:
        embedding_type = sa.JSON()

    op.add_column('datasets', sa.Column('dictionary', sa.JSON(), nullable=True))
    op.add_column('query_log', sa.Column('schema_hash', sa.String(length=32), nullable=True))
    op.add_column('query_log', sa.Column('embedding', embedding_type, nullable=True))
    op.add_column('query_log', sa.Column('embedder', sa.String(length=32), nullable=True))
    op.add_column('query_log', sa.Column('feedback', sa.Boolean(), nullable=True))
    op.create_index('ix_query_log_schema_hash', 'query_log', ['schema_hash'])
    if postgres:
        # approximate nearest neighbour on cosine distance
        op.execute(
            "CREATE INDEX ix_query_log_embedding ON query_log "
            "USING hnsw (embedding vector_cosine_ops)"
        )


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_query_log_embedding")
    op.drop_index('ix_query_log_schema_hash', table_name='query_log')
    with op.batch_alter_table('query_log') as batch:
        for col in ('feedback', 'embedder', 'embedding', 'schema_hash'):
            batch.drop_column(col)
    with op.batch_alter_table('datasets') as batch:
        batch.drop_column('dictionary')
