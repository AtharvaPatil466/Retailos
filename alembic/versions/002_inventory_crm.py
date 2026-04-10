"""inventory: products, customers, purchase_history, suppliers

Revision ID: 002_inventory
Revises: 001_core
Create Date: 2026-04-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '002_inventory'
down_revision: Union[str, Sequence[str], None] = '001_core'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'products',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('sku', sa.String(30), unique=True, nullable=False),
        sa.Column('product_name', sa.String(255), nullable=False),
        sa.Column('category', sa.String(100), nullable=False, server_default=''),
        sa.Column('image_url', sa.Text),
        sa.Column('barcode', sa.String(50)),
        sa.Column('current_stock', sa.Integer, server_default='0'),
        sa.Column('reorder_threshold', sa.Integer, server_default='0'),
        sa.Column('daily_sales_rate', sa.Float, server_default='0'),
        sa.Column('unit_price', sa.Float, server_default='0'),
        sa.Column('cost_price', sa.Float, server_default='0'),
        sa.Column('shelf_life_days', sa.Integer),
        sa.Column('last_restock_date', sa.String(20)),
        sa.Column('store_id', sa.String(36), sa.ForeignKey('stores.id')),
        sa.Column('is_active', sa.Boolean, server_default=sa.text('1')),
        sa.Column('created_at', sa.Float),
    )
    op.create_index('ix_products_sku', 'products', ['sku'])
    op.create_index('ix_products_barcode', 'products', ['barcode'])
    op.create_index('ix_products_category', 'products', ['category'])

    op.create_table(
        'customers',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('customer_code', sa.String(20), unique=True, nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('phone', sa.String(20), unique=True, nullable=False),
        sa.Column('email', sa.String(255)),
        sa.Column('whatsapp_opted_in', sa.Boolean, server_default=sa.text('0')),
        sa.Column('last_offer_timestamp', sa.Float),
        sa.Column('last_offer_category', sa.String(100)),
        sa.Column('store_id', sa.String(36), sa.ForeignKey('stores.id')),
        sa.Column('created_at', sa.Float),
    )
    op.create_index('ix_customers_code', 'customers', ['customer_code'])
    op.create_index('ix_customers_phone', 'customers', ['phone'])

    op.create_table(
        'purchase_history',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('customer_id', sa.String(36), sa.ForeignKey('customers.id'), nullable=False),
        sa.Column('product', sa.String(255), nullable=False),
        sa.Column('category', sa.String(100), server_default=''),
        sa.Column('quantity', sa.Integer, server_default='1'),
        sa.Column('price', sa.Float, server_default='0'),
        sa.Column('timestamp', sa.Float),
    )
    op.create_index('ix_purchase_history_customer', 'purchase_history', ['customer_id'])

    op.create_table(
        'suppliers',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('supplier_id', sa.String(20), unique=True, nullable=False),
        sa.Column('supplier_name', sa.String(255), nullable=False),
        sa.Column('contact_phone', sa.String(20)),
        sa.Column('whatsapp_number', sa.String(20)),
        sa.Column('products_json', sa.Text),
        sa.Column('categories_json', sa.Text),
        sa.Column('price_per_unit', sa.Float, server_default='0'),
        sa.Column('reliability_score', sa.Float, server_default='3.0'),
        sa.Column('delivery_days', sa.Integer, server_default='7'),
        sa.Column('min_order_qty', sa.Integer, server_default='1'),
        sa.Column('payment_terms', sa.String(100)),
        sa.Column('location', sa.String(255)),
        sa.Column('notes', sa.Text),
        sa.Column('is_active', sa.Boolean, server_default=sa.text('1')),
        sa.Column('store_id', sa.String(36), sa.ForeignKey('stores.id')),
        sa.Column('created_at', sa.Float),
    )
    op.create_index('ix_suppliers_id', 'suppliers', ['supplier_id'])


def downgrade() -> None:
    op.drop_table('purchase_history')
    op.drop_table('suppliers')
    op.drop_table('customers')
    op.drop_table('products')
