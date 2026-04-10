"""core: stores and users

Revision ID: 001_core
Revises:
Create Date: 2026-04-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '001_core'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'stores',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('store_name', sa.String(255), nullable=False),
        sa.Column('phone', sa.String(20)),
        sa.Column('address', sa.Text),
        sa.Column('gstin', sa.String(20)),
        sa.Column('hours_json', sa.Text),
        sa.Column('holiday_note', sa.Text),
        sa.Column('created_at', sa.Float),
    )

    op.create_table(
        'users',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('username', sa.String(80), unique=True, nullable=False),
        sa.Column('email', sa.String(255), unique=True, nullable=False),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('full_name', sa.String(255), nullable=False),
        sa.Column('role', sa.String(20), nullable=False, server_default='staff'),
        sa.Column('phone', sa.String(20)),
        sa.Column('is_active', sa.Boolean, server_default=sa.text('1')),
        sa.Column('store_id', sa.String(36), sa.ForeignKey('stores.id')),
        sa.Column('created_at', sa.Float),
        sa.Column('last_login', sa.Float),
    )
    op.create_index('ix_users_username', 'users', ['username'])
    op.create_index('ix_users_email', 'users', ['email'])


def downgrade() -> None:
    op.drop_table('users')
    op.drop_table('stores')
