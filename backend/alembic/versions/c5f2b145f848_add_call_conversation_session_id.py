"""add calls.conversation_session_id

Revision ID: c5f2b145f848
Revises: 5f52213f2082
Create Date: 2026-08-25 06:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import app.database.types

# revision identifiers, used by Alembic.
revision: str = 'c5f2b145f848'
down_revision: Union[str, None] = '5f52213f2082'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('calls', sa.Column('conversation_session_id', app.database.types.GUID(), nullable=True))
    op.create_index(op.f('ix_calls_conversation_session_id'), 'calls', ['conversation_session_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_calls_conversation_session_id'), table_name='calls')
    op.drop_column('calls', 'conversation_session_id')
