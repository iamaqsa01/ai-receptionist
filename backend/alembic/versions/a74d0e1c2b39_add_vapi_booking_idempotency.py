"""add Vapi booking idempotency fields

Revision ID: a74d0e1c2b39
Revises: c5f2b145f848
Create Date: 2026-08-25 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a74d0e1c2b39"
down_revision: Union[str, None] = "c5f2b145f848"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("appointments", sa.Column("vapi_call_id", sa.String(length=255), nullable=True))
    op.add_column("appointments", sa.Column("vapi_tool_call_id", sa.String(length=255), nullable=True))
    op.create_index(op.f("ix_appointments_vapi_call_id"), "appointments", ["vapi_call_id"], unique=False)
    op.create_index(op.f("ix_appointments_vapi_tool_call_id"), "appointments", ["vapi_tool_call_id"], unique=False)
    op.create_unique_constraint(
        "uq_appointments_vapi_tool_call",
        "appointments",
        ["workspace_id", "vapi_call_id", "vapi_tool_call_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_appointments_vapi_tool_call", "appointments", type_="unique")
    op.drop_index(op.f("ix_appointments_vapi_tool_call_id"), table_name="appointments")
    op.drop_index(op.f("ix_appointments_vapi_call_id"), table_name="appointments")
    op.drop_column("appointments", "vapi_tool_call_id")
    op.drop_column("appointments", "vapi_call_id")
