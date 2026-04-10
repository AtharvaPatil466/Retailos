"""features & audit: notifications, promotions, loyalty, purchase orders, audit logs

Revision ID: 005_features
Revises: 004_staff_ops
Create Date: 2026-04-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '005_features'
down_revision: Union[str, Sequence[str], None] = '004_staff_ops'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'notifications',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id')),
        sa.Column('store_id', sa.String(36), sa.ForeignKey('stores.id')),
        sa.Column('channel', sa.String(20), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('body', sa.Text, nullable=False),
        sa.Column('category', sa.String(50), server_default='general'),
        sa.Column('priority', sa.String(10), server_default='normal'),
        sa.Column('is_read', sa.Boolean, server_default=sa.text('0')),
        sa.Column('sent_at', sa.Float),
        sa.Column('read_at', sa.Float),
        sa.Column('metadata_json', sa.Text),
    )
    op.create_index('ix_notifications_user_read', 'notifications', ['user_id', 'is_read'])

    op.create_table(
        'promotions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('promo_code', sa.String(30), unique=True),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('description', sa.Text),
        sa.Column('promo_type', sa.String(30), nullable=False),
        sa.Column('discount_value', sa.Float, server_default='0'),
        sa.Column('min_order_amount', sa.Float, server_default='0'),
        sa.Column('applicable_skus_json', sa.Text),
        sa.Column('applicable_categories_json', sa.Text),
        sa.Column('max_uses', sa.Integer, server_default='0'),
        sa.Column('current_uses', sa.Integer, server_default='0'),
        sa.Column('starts_at', sa.Float, nullable=False),
        sa.Column('ends_at', sa.Float, nullable=False),
        sa.Column('is_active', sa.Boolean, server_default=sa.text('1')),
        sa.Column('store_id', sa.String(36), sa.ForeignKey('stores.id')),
        sa.Column('created_at', sa.Float),
    )
    op.create_index('ix_promotions_code', 'promotions', ['promo_code'])

    op.create_table(
        'loyalty_accounts',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('customer_id', sa.String(36), sa.ForeignKey('customers.id'), unique=True),
        sa.Column('points_balance', sa.Integer, server_default='0'),
        sa.Column('lifetime_points', sa.Integer, server_default='0'),
        sa.Column('tier', sa.String(20), server_default='bronze'),
        sa.Column('created_at', sa.Float),
    )
    op.create_index('ix_loyalty_accounts_customer', 'loyalty_accounts', ['customer_id'])

    op.create_table(
        'loyalty_transactions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('account_id', sa.String(36), sa.ForeignKey('loyalty_accounts.id'), nullable=False),
        sa.Column('order_id', sa.String(30)),
        sa.Column('points', sa.Integer, nullable=False),
        sa.Column('description', sa.String(255), nullable=False),
        sa.Column('timestamp', sa.Float),
    )
    op.create_index('ix_loyalty_transactions_account', 'loyalty_transactions', ['account_id'])

    op.create_table(
        'purchase_orders',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('po_number', sa.String(30), unique=True, nullable=False),
        sa.Column('supplier_id', sa.String(36), sa.ForeignKey('suppliers.id'), nullable=False),
        sa.Column('status', sa.String(20), server_default='draft'),
        sa.Column('total_amount', sa.Float, server_default='0'),
        sa.Column('payment_status', sa.String(20), server_default='unpaid'),
        sa.Column('expected_delivery', sa.String(20)),
        sa.Column('actual_delivery', sa.String(20)),
        sa.Column('notes', sa.Text),
        sa.Column('store_id', sa.String(36), sa.ForeignKey('stores.id')),
        sa.Column('created_at', sa.Float),
    )
    op.create_index('ix_purchase_orders_number', 'purchase_orders', ['po_number'])
    op.create_index('ix_purchase_orders_supplier', 'purchase_orders', ['supplier_id'])

    op.create_table(
        'purchase_order_items',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('po_id', sa.String(36), sa.ForeignKey('purchase_orders.id'), nullable=False),
        sa.Column('sku', sa.String(30), nullable=False),
        sa.Column('product_name', sa.String(255), nullable=False),
        sa.Column('qty', sa.Integer, server_default='1'),
        sa.Column('unit_price', sa.Float, server_default='0'),
        sa.Column('total', sa.Float, server_default='0'),
        sa.Column('received_qty', sa.Integer, server_default='0'),
    )
    op.create_index('ix_purchase_order_items_po', 'purchase_order_items', ['po_id'])

    op.create_table(
        'audit_logs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('timestamp', sa.Float, nullable=False),
        sa.Column('skill', sa.String(50), nullable=False),
        sa.Column('event_type', sa.String(50), nullable=False),
        sa.Column('decision', sa.Text, nullable=False),
        sa.Column('reasoning', sa.Text, nullable=False),
        sa.Column('outcome', sa.Text, nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('metadata_json', sa.Text),
        sa.Column('store_id', sa.String(36), sa.ForeignKey('stores.id')),
    )
    op.create_index('ix_audit_logs_timestamp', 'audit_logs', ['timestamp'])
    op.create_index('ix_audit_logs_skill', 'audit_logs', ['skill'])
    op.create_index('ix_audit_logs_event_type', 'audit_logs', ['event_type'])


def downgrade() -> None:
    op.drop_table('audit_logs')
    op.drop_table('purchase_order_items')
    op.drop_table('purchase_orders')
    op.drop_table('loyalty_transactions')
    op.drop_table('loyalty_accounts')
    op.drop_table('promotions')
    op.drop_table('notifications')
