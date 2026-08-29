"""add integration_logs

Revision ID: 5f52213f2082
Revises: 62b810f6c887
Create Date: 2026-08-25 06:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import app.database.types
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '5f52213f2082'
down_revision: Union[str, None] = '62b810f6c887'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'integration_logs',
        sa.Column('category', sa.String(length=32), nullable=False),
        sa.Column('provider', sa.String(length=32), nullable=False),
        sa.Column('action', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('detail', sa.Text(), nullable=True),
        sa.Column('extra_data', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True),
        sa.Column('id', app.database.types.GUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('workspace_id', app.database.types.GUID(), nullable=False),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_integration_logs_category'), 'integration_logs', ['category'], unique=False)
    op.create_index(op.f('ix_integration_logs_provider'), 'integration_logs', ['provider'], unique=False)
    op.create_index(op.f('ix_integration_logs_status'), 'integration_logs', ['status'], unique=False)
    op.create_index(op.f('ix_integration_logs_workspace_id'), 'integration_logs', ['workspace_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_integration_logs_workspace_id'), table_name='integration_logs')
    op.drop_index(op.f('ix_integration_logs_status'), table_name='integration_logs')
    op.drop_index(op.f('ix_integration_logs_provider'), table_name='integration_logs')
    op.drop_index(op.f('ix_integration_logs_category'), table_name='integration_logs')
    op.drop_table('integration_logs')
