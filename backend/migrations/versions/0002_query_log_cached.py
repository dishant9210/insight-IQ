"""query log: cached flag

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-05
"""
from alembic import op
import sqlalchemy as sa


revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('query_log', sa.Column('cached', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    with op.batch_alter_table('query_log') as batch:
        batch.drop_column('cached')
