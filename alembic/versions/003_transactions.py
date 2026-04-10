"""transactions: orders, udhaar, returns, deliveries

Revision ID: 003_transactions
Revises: 002_inventory
Create Date: 2026-04-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '003_transactions'
down_revision: Union[str, Sequence[str], None] = '002_inventory'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'orders',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('order_id', sa.String(30), unique=True, nullable=False),
        sa.Column('customer_id', sa.String(36), sa.ForeignKey('customers.id')),
        sa.Column('customer_name', sa.String(255)),
        sa.Column('phone', sa.String(20)),
        sa.Column('total_amount', sa.Float, server_default='0'),
        sa.Column('gst_amount', sa.Float, server_default='0'),
        sa.Column('discount_amount', sa.Float, server_default='0'),
        sa.Column('status', sa.String(30), server_default='pending'),
        sa.Column('payment_method', sa.String(30), server_default='Cash'),
        sa.Column('source', sa.String(30), server_default='counter'),
        sa.Column('store_id', sa.String(36), sa.ForeignKey('stores.id')),
        sa.Column('timestamp', sa.Float),
    )
    op.create_index('ix_orders_order_id', 'orders', ['order_id'])
    op.create_index('ix_orders_timestamp', 'orders', ['timestamp'])
    op.create_index('ix_orders_status', 'orders', ['status'])

    op.create_table(
        'order_items',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('order_id', sa.String(36), sa.ForeignKey('orders.id'), nullable=False),
        sa.Column('sku', sa.String(30), nullable=False),
        sa.Column('product_name', sa.String(255), nullable=False),
        sa.Column('qty', sa.Integer, server_default='1'),
        sa.Column('unit_price', sa.Float, server_default='0'),
        sa.Column('total', sa.Float, server_default='0'),
    )
    op.create_index('ix_order_items_order', 'order_items', ['order_id'])

    op.create_table(
        'udhaar_ledgers',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('udhaar_id', sa.String(20), unique=True, nullable=False),
        sa.Column('customer_id', sa.String(36), sa.ForeignKey('customers.id'), nullable=False),
        sa.Column('customer_name', sa.String(255), nullable=False),
        sa.Column('phone', sa.String(20), nullable=False),
        sa.Column('total_credit', sa.Float, server_default='0'),
        sa.Column('total_paid', sa.Float, server_default='0'),
        sa.Column('balance', sa.Float, server_default='0'),
        sa.Column('credit_limit', sa.Float, server_default='5000'),
        sa.Column('last_reminder_sent', sa.String(20)),
        sa.Column('store_id', sa.String(36), sa.ForeignKey('stores.id')),
        sa.Column('created_at', sa.String(20), nullable=False),
    )
    op.create_index('ix_udhaar_ledgers_id', 'udhaar_ledgers', ['udhaar_id'])
    op.create_index('ix_udhaar_ledgers_customer', 'udhaar_ledgers', ['customer_id'])

    op.create_table(
        'udhaar_entries',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('ledger_id', sa.String(36), sa.ForeignKey('udhaar_ledgers.id'), nullable=False),
        sa.Column('order_id', sa.String(30)),
        sa.Column('entry_type', sa.String(10), nullable=False),
        sa.Column('amount', sa.Float, nullable=False),
        sa.Column('items_json', sa.Text),
        sa.Column('note', sa.Text),
        sa.Column('date', sa.String(20), nullable=False),
        sa.Column('timestamp', sa.Float),
    )
    op.create_index('ix_udhaar_entries_ledger', 'udhaar_entries', ['ledger_id'])

    op.create_table(
        'returns',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('return_id', sa.String(20), unique=True, nullable=False),
        sa.Column('order_id', sa.String(30), nullable=False),
        sa.Column('customer_id', sa.String(36), sa.ForeignKey('customers.id')),
        sa.Column('customer_name', sa.String(255), nullable=False),
        sa.Column('refund_amount', sa.Float, server_default='0'),
        sa.Column('refund_method', sa.String(30), server_default='Cash'),
        sa.Column('status', sa.String(20), server_default='pending'),
        sa.Column('store_id', sa.String(36), sa.ForeignKey('stores.id')),
        sa.Column('timestamp', sa.Float),
        sa.Column('processed_at', sa.Float),
    )
    op.create_index('ix_returns_id', 'returns', ['return_id'])

    op.create_table(
        'return_items',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('return_id', sa.String(36), sa.ForeignKey('returns.id'), nullable=False),
        sa.Column('sku', sa.String(30), nullable=False),
        sa.Column('product_name', sa.String(255), nullable=False),
        sa.Column('qty', sa.Integer, server_default='1'),
        sa.Column('unit_price', sa.Float, server_default='0'),
        sa.Column('reason', sa.String(255), server_default=''),
        sa.Column('action', sa.String(30), server_default='refund'),
    )
    op.create_index('ix_return_items_return', 'return_items', ['return_id'])

    op.create_table(
        'delivery_requests',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('request_id', sa.String(20), unique=True, nullable=False),
        sa.Column('customer_id', sa.String(36), sa.ForeignKey('customers.id')),
        sa.Column('customer_name', sa.String(255), nullable=False),
        sa.Column('phone', sa.String(20), nullable=False),
        sa.Column('address', sa.Text, nullable=False),
        sa.Column('total_amount', sa.Float, server_default='0'),
        sa.Column('status', sa.String(20), server_default='pending'),
        sa.Column('delivery_slot', sa.String(50)),
        sa.Column('notes', sa.Text),
        sa.Column('assigned_to', sa.String(36)),
        sa.Column('store_id', sa.String(36), sa.ForeignKey('stores.id')),
        sa.Column('requested_at', sa.Float),
        sa.Column('dispatched_at', sa.Float),
        sa.Column('delivered_at', sa.Float),
    )
    op.create_index('ix_delivery_requests_id', 'delivery_requests', ['request_id'])

    op.create_table(
        'delivery_items',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('delivery_id', sa.String(36), sa.ForeignKey('delivery_requests.id'), nullable=False),
        sa.Column('sku', sa.String(30), nullable=False),
        sa.Column('product_name', sa.String(255), nullable=False),
        sa.Column('qty', sa.Integer, server_default='1'),
        sa.Column('unit_price', sa.Float, server_default='0'),
    )
    op.create_index('ix_delivery_items_delivery', 'delivery_items', ['delivery_id'])


def downgrade() -> None:
    op.drop_table('delivery_items')
    op.drop_table('delivery_requests')
    op.drop_table('return_items')
    op.drop_table('returns')
    op.drop_table('udhaar_entries')
    op.drop_table('udhaar_ledgers')
    op.drop_table('order_items')
    op.drop_table('orders')
