"""datasets and query log

Revision ID: 0001
Revises: 
Create Date: 2026-11-05
"""
from alembic import op
import sqlalchemy as sa


revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('datasets',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('filename', sa.String(length=255), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('rows', sa.Integer(), nullable=True),
    sa.Column('columns', sa.JSON(), nullable=True),
    sa.Column('detected_types', sa.JSON(), nullable=True),
    sa.Column('preview', sa.JSON(), nullable=True),
    sa.Column('warnings', sa.JSON(), nullable=False),
    sa.Column('tables', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_datasets_created_at'), 'datasets', ['created_at'], unique=False)
    op.create_index(op.f('ix_datasets_status'), 'datasets', ['status'], unique=False)
    op.create_table('query_log',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('dataset_id', sa.String(length=36), nullable=False),
    sa.Column('question', sa.Text(), nullable=False),
    sa.Column('sql', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('row_count', sa.Integer(), nullable=True),
    sa.Column('latency_ms', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_query_log_created_at'), 'query_log', ['created_at'], unique=False)
    op.create_index(op.f('ix_query_log_dataset_id'), 'query_log', ['dataset_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_query_log_dataset_id'), table_name='query_log')
    op.drop_index(op.f('ix_query_log_created_at'), table_name='query_log')
    op.drop_table('query_log')
    op.drop_index(op.f('ix_datasets_status'), table_name='datasets')
    op.drop_index(op.f('ix_datasets_created_at'), table_name='datasets')
    op.drop_table('datasets')
