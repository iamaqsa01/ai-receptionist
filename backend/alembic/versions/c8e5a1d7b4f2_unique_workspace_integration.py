"""enforce one integration row per workspace and provider

Revision ID: c8e5a1d7b4f2
Revises: f3b7c1a9d4e2
Create Date: 2026-08-31 15:00:00.000000
"""

from typing import Sequence, Union

from alembic import op


revision: str = "c8e5a1d7b4f2"
down_revision: Union[str, None] = "f3b7c1a9d4e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_integrations_workspace_provider",
        "integrations",
        ["workspace_id", "provider"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_integrations_workspace_provider",
        "integrations",
        type_="unique",
    )
