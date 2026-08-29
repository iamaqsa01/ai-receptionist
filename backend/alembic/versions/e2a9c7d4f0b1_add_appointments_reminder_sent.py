"""add appointments.reminder_sent

Revision ID: e2a9c7d4f0b1
Revises: b1f7a4c9d2e3
Create Date: 2026-08-28 00:00:00.000000

Day-of reminder state for the morning reminder job (app/jobs/reminders.py).
Additive and backward compatible: `server_default` false means every
existing appointment row is treated as "not yet reminded" and will be
picked up by the first reminder run for its day (a pre-existing past
appointment simply never matches "scheduled for today"), and no existing
data is read or rewritten by this migration.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "e2a9c7d4f0b1"
down_revision: Union[str, None] = "b1f7a4c9d2e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "appointments",
        sa.Column(
            "reminder_sent",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_index(
        "ix_appointments_reminder_sent", "appointments", ["reminder_sent"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_appointments_reminder_sent", table_name="appointments")
    op.drop_column("appointments", "reminder_sent")
