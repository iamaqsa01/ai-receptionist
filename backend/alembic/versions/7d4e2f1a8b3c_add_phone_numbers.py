"""add phone number workspace mappings

Additive only: creates the ``phone_numbers`` table used to route an inbound
Vapi call to a workspace by its dialed number. No existing table, column or
row is touched.

Revision ID: 7d4e2f1a8b3c
Revises: c8e5a1d7b4f2
Create Date: 2026-09-03
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

import app.database.types

revision: str = "7d4e2f1a8b3c"
down_revision: Union[str, None] = "c8e5a1d7b4f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "phone_numbers",
        sa.Column("number", sa.String(length=32), nullable=False),
        sa.Column("workspace_id", app.database.types.GUID(), nullable=False),
        sa.Column("id", app.database.types.GUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("number", name="uq_phone_numbers_number"),
    )
    op.create_index(op.f("ix_phone_numbers_number"), "phone_numbers", ["number"], unique=False)
    op.create_index(
        op.f("ix_phone_numbers_workspace_id"), "phone_numbers", ["workspace_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_phone_numbers_workspace_id"), table_name="phone_numbers")
    op.drop_index(op.f("ix_phone_numbers_number"), table_name="phone_numbers")
    op.drop_table("phone_numbers")
