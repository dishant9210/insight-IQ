"""accounts, refresh tokens, dataset owners, question history

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-05
"""
from alembic import op
import sqlalchemy as sa


revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'users',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('email', sa.String(length=320), nullable=False, unique=True),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        'refresh_tokens',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.String(length=36),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('family', sa.String(length=36), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False, unique=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_refresh_tokens_user_id', 'refresh_tokens', ['user_id'])
    op.create_index('ix_refresh_tokens_family', 'refresh_tokens', ['family'])

    with op.batch_alter_table('datasets') as batch:
        batch.add_column(sa.Column('owner_id', sa.String(length=36), nullable=True))
        batch.create_foreign_key('fk_datasets_owner_id', 'users', ['owner_id'], ['id'], ondelete='CASCADE')
        batch.create_index('ix_datasets_owner_id', ['owner_id'])

    op.add_column('query_log', sa.Column('user_id', sa.String(length=36), nullable=True))
    op.add_column('query_log', sa.Column('insight', sa.Text(), nullable=True))
    op.add_column('query_log', sa.Column('chart_type', sa.String(length=16), nullable=True))
    op.create_index('ix_query_log_user_id', 'query_log', ['user_id'])


def downgrade():
    op.drop_index('ix_query_log_user_id', table_name='query_log')
    with op.batch_alter_table('query_log') as batch:
        for col in ('chart_type', 'insight', 'user_id'):
            batch.drop_column(col)
    with op.batch_alter_table('datasets') as batch:
        batch.drop_index('ix_datasets_owner_id')
        batch.drop_constraint('fk_datasets_owner_id', type_='foreignkey')
        batch.drop_column('owner_id')
    op.drop_table('refresh_tokens')
    op.drop_table('users')
