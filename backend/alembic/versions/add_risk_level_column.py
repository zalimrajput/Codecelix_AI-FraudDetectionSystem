"""Add risk_level column to transactions

Revision ID: add_risk_level_column
Revises: 
Create Date: 2024-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_risk_level_column'
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column('transactions', sa.Column('risk_level', sa.String(16), nullable=True))

def downgrade() -> None:
    op.drop_column('transactions', 'risk_level')