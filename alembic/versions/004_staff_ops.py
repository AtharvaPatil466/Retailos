"""staff & store ops: staff_members, shifts, attendance, shelf zones

Revision ID: 004_staff_ops
Revises: 003_transactions
Create Date: 2026-04-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '004_staff_ops'
down_revision: Union[str, Sequence[str], None] = '003_transactions'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'staff_members',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('staff_code', sa.String(20), unique=True, nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('phone', sa.String(20)),
        sa.Column('role', sa.String(50), server_default='cashier'),
        sa.Column('hourly_rate', sa.Float, server_default='0'),
        sa.Column('is_active', sa.Boolean, server_default=sa.text('1')),
        sa.Column('store_id', sa.String(36), sa.ForeignKey('stores.id')),
        sa.Column('joined_at', sa.Float),
    )
    op.create_index('ix_staff_members_code', 'staff_members', ['staff_code'])

    op.create_table(
        'staff_shifts_v2',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('staff_id', sa.String(36), sa.ForeignKey('staff_members.id'), nullable=False),
        sa.Column('shift_date', sa.String(20), nullable=False),
        sa.Column('start_hour', sa.Integer, nullable=False),
        sa.Column('end_hour', sa.Integer, nullable=False),
        sa.Column('status', sa.String(20), server_default='scheduled'),
    )
    op.create_index('ix_staff_shifts_staff', 'staff_shifts_v2', ['staff_id'])
    op.create_index('ix_staff_shifts_date', 'staff_shifts_v2', ['shift_date'])

    op.create_table(
        'attendance_records',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('staff_id', sa.String(36), sa.ForeignKey('staff_members.id'), nullable=False),
        sa.Column('date', sa.String(20), nullable=False),
        sa.Column('clock_in', sa.Float),
        sa.Column('clock_out', sa.Float),
        sa.Column('status', sa.String(20), server_default='present'),
        sa.Column('hours_worked', sa.Float, server_default='0'),
        sa.UniqueConstraint('staff_id', 'date', name='uq_attendance_staff_date'),
    )
    op.create_index('ix_attendance_staff', 'attendance_records', ['staff_id'])

    op.create_table(
        'shelf_zones',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('zone_id', sa.String(10), unique=True, nullable=False),
        sa.Column('zone_name', sa.String(100), nullable=False),
        sa.Column('zone_type', sa.String(30), nullable=False),
        sa.Column('total_slots', sa.Integer, server_default='10'),
        sa.Column('store_id', sa.String(36), sa.ForeignKey('stores.id')),
    )
    op.create_index('ix_shelf_zones_id', 'shelf_zones', ['zone_id'])

    op.create_table(
        'shelf_products',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('zone_id', sa.String(36), sa.ForeignKey('shelf_zones.id'), nullable=False),
        sa.Column('sku', sa.String(30), nullable=False),
        sa.Column('product_name', sa.String(255), nullable=False),
        sa.Column('shelf_level', sa.String(20), server_default='lower'),
        sa.Column('placed_date', sa.String(20)),
        sa.Column('days_here', sa.Integer, server_default='0'),
    )
    op.create_index('ix_shelf_products_zone', 'shelf_products', ['zone_id'])


def downgrade() -> None:
    op.drop_table('shelf_products')
    op.drop_table('shelf_zones')
    op.drop_table('attendance_records')
    op.drop_table('staff_shifts_v2')
    op.drop_table('staff_members')
