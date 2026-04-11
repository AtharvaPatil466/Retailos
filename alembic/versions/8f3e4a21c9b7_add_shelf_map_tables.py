"""add shelf map tables

Revision ID: 8f3e4a21c9b7
Revises: 50733d721f6c
Create Date: 2026-04-11 12:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8f3e4a21c9b7'
down_revision: Union[str, Sequence[str], None] = '50733d721f6c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'shelf_sections',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('x', sa.Float, server_default='0'),
        sa.Column('y', sa.Float, server_default='0'),
        sa.Column('width', sa.Float, server_default='200'),
        sa.Column('height', sa.Float, server_default='140'),
        sa.Column('store_id', sa.Integer),
    )

    op.create_table(
        'shelf_section_products',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('section_id', sa.Integer, sa.ForeignKey('shelf_sections.id', ondelete='CASCADE'), nullable=False),
        sa.Column('product_id', sa.String(36), sa.ForeignKey('products.id', ondelete='CASCADE'), nullable=False),
    )
    op.create_index('ix_shelf_section_products_section_id', 'shelf_section_products', ['section_id'])
    op.create_index('ix_shelf_section_products_product_id', 'shelf_section_products', ['product_id'])


def downgrade() -> None:
    op.drop_index('ix_shelf_section_products_product_id', table_name='shelf_section_products')
    op.drop_index('ix_shelf_section_products_section_id', table_name='shelf_section_products')
    op.drop_table('shelf_section_products')
    op.drop_table('shelf_sections')
