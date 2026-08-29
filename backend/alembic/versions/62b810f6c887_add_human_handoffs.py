"""add human_handoffs

Revision ID: 62b810f6c887
Revises: d00288d5d094
Create Date: 2026-08-25 04:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import app.database.types
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '62b810f6c887'
down_revision: Union[str, None] = 'd00288d5d094'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'human_handoffs',
        sa.Column('call_id', app.database.types.GUID(), nullable=True),
        sa.Column('conversation_session_id', app.database.types.GUID(), nullable=True),
        sa.Column('trigger', sa.String(length=32), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('conversation_context', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
        sa.Column('call_state', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('transfer_target', sa.String(length=64), nullable=True),
        sa.Column('transfer_detail', sa.Text(), nullable=True),
        sa.Column('transferred_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('id', app.database.types.GUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('workspace_id', app.database.types.GUID(), nullable=False),
        sa.ForeignKeyConstraint(['call_id'], ['calls.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_human_handoffs_call_id'), 'human_handoffs', ['call_id'], unique=False)
    op.create_index(op.f('ix_human_handoffs_conversation_session_id'), 'human_handoffs', ['conversation_session_id'], unique=False)
    op.create_index(op.f('ix_human_handoffs_status'), 'human_handoffs', ['status'], unique=False)
    op.create_index(op.f('ix_human_handoffs_trigger'), 'human_handoffs', ['trigger'], unique=False)
    op.create_index(op.f('ix_human_handoffs_workspace_id'), 'human_handoffs', ['workspace_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_human_handoffs_workspace_id'), table_name='human_handoffs')
    op.drop_index(op.f('ix_human_handoffs_trigger'), table_name='human_handoffs')
    op.drop_index(op.f('ix_human_handoffs_status'), table_name='human_handoffs')
    op.drop_index(op.f('ix_human_handoffs_conversation_session_id'), table_name='human_handoffs')
    op.drop_index(op.f('ix_human_handoffs_call_id'), table_name='human_handoffs')
    op.drop_table('human_handoffs')
