"""add notification_messages

Revision ID: d00288d5d094
Revises: 483ce4e96e62
Create Date: 2026-08-25 03:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import app.database.types

# revision identifiers, used by Alembic.
revision: str = 'd00288d5d094'
down_revision: Union[str, None] = '483ce4e96e62'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'notification_messages',
        sa.Column('appointment_id', app.database.types.GUID(), nullable=True),
        sa.Column('channel', sa.String(length=16), nullable=False),
        sa.Column('event_type', sa.String(length=48), nullable=False),
        sa.Column('audience', sa.String(length=16), nullable=False),
        sa.Column('recipient', sa.String(length=255), nullable=False),
        sa.Column('provider', sa.String(length=32), nullable=False),
        sa.Column('provider_message_id', sa.String(length=255), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('failure_reason', sa.Text(), nullable=True),
        sa.Column('subject', sa.String(length=255), nullable=True),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('id', app.database.types.GUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('workspace_id', app.database.types.GUID(), nullable=False),
        sa.ForeignKeyConstraint(['appointment_id'], ['appointments.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_notification_messages_appointment_id'), 'notification_messages', ['appointment_id'], unique=False)
    op.create_index(op.f('ix_notification_messages_audience'), 'notification_messages', ['audience'], unique=False)
    op.create_index(op.f('ix_notification_messages_channel'), 'notification_messages', ['channel'], unique=False)
    op.create_index(op.f('ix_notification_messages_event_type'), 'notification_messages', ['event_type'], unique=False)
    op.create_index(op.f('ix_notification_messages_provider_message_id'), 'notification_messages', ['provider_message_id'], unique=False)
    op.create_index(op.f('ix_notification_messages_recipient'), 'notification_messages', ['recipient'], unique=False)
    op.create_index(op.f('ix_notification_messages_status'), 'notification_messages', ['status'], unique=False)
    op.create_index(op.f('ix_notification_messages_workspace_id'), 'notification_messages', ['workspace_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_notification_messages_workspace_id'), table_name='notification_messages')
    op.drop_index(op.f('ix_notification_messages_status'), table_name='notification_messages')
    op.drop_index(op.f('ix_notification_messages_recipient'), table_name='notification_messages')
    op.drop_index(op.f('ix_notification_messages_provider_message_id'), table_name='notification_messages')
    op.drop_index(op.f('ix_notification_messages_event_type'), table_name='notification_messages')
    op.drop_index(op.f('ix_notification_messages_channel'), table_name='notification_messages')
    op.drop_index(op.f('ix_notification_messages_audience'), table_name='notification_messages')
    op.drop_index(op.f('ix_notification_messages_appointment_id'), table_name='notification_messages')
    op.drop_table('notification_messages')
