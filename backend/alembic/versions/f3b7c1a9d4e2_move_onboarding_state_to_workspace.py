"""move onboarding state from user to workspace

Revision ID: f3b7c1a9d4e2
Revises: e2a9c7d4f0b1
Create Date: 2026-09-01 00:00:00.000000

Onboarding is now a property of the Workspace, not the User. A user who
owns several workspaces (e.g. branches) onboards each one independently:

    Workspace A -> is_onboarded = true
    Workspace B -> is_onboarded = false

upgrade():
  1. Add ``workspaces.is_onboarded`` (NOT NULL, server_default false).
  2. Backfill so no existing tenant is locked out. A workspace is marked
     onboarded if EITHER:
       (a) it already has clinic settings saved — any of its ``ai_agents``
           rows has a ``clinic_settings`` key in ``config`` (this is the
           historical onboarding-completion signal), OR
       (b) as a safety net for the "1 user : 1 workspace" world this app
           has produced, an OWNER member of the workspace had
           ``users.is_onboarded = true``.
  3. Drop ``users.is_onboarded`` (only after the backfill has read it).

downgrade():
  1. Re-add ``users.is_onboarded`` (NOT NULL, server_default false).
  2. Backfill: mark a user onboarded if they are a member of ANY onboarded
     workspace — the faithful inverse of "completed onboarding somewhere".
  3. Drop ``workspaces.is_onboarded``.

Postgres is the deployment target (as with every migration here). The data
steps use portable SQLAlchemy Core so they also run on SQLite. No column
other than the two ``is_onboarded`` flags is read or written.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import app.database.types

# revision identifiers, used by Alembic.
revision: str = "f3b7c1a9d4e2"
down_revision: Union[str, None] = "e2a9c7d4f0b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_GUID = app.database.types.GUID


def _t_workspaces() -> sa.Table:
    return sa.table(
        "workspaces",
        sa.column("id", _GUID()),
        sa.column("is_onboarded", sa.Boolean()),
    )


def _t_users() -> sa.Table:
    return sa.table(
        "users",
        sa.column("id", _GUID()),
        sa.column("is_onboarded", sa.Boolean()),
    )


def _t_ai_agents() -> sa.Table:
    return sa.table(
        "ai_agents",
        sa.column("workspace_id", _GUID()),
        sa.column("config", sa.JSON()),
    )


def _t_members() -> sa.Table:
    return sa.table(
        "workspace_members",
        sa.column("workspace_id", _GUID()),
        sa.column("user_id", _GUID()),
        sa.column("role", sa.String()),
    )


def upgrade() -> None:
    op.add_column(
        "workspaces",
        sa.Column("is_onboarded", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    bind = op.get_bind()
    workspaces = _t_workspaces()
    users = _t_users()
    ai_agents = _t_ai_agents()
    members = _t_members()

    onboarded_ws: set = set()

    # (a) workspaces whose AI-agent config already holds clinic_settings
    for workspace_id, config in bind.execute(
        sa.select(ai_agents.c.workspace_id, ai_agents.c.config)
    ):
        if isinstance(config, dict) and "clinic_settings" in config:
            onboarded_ws.add(workspace_id)

    # (b) safety net — workspaces whose OWNER had users.is_onboarded = true
    onboarded_user_ids = {
        row[0]
        for row in bind.execute(sa.select(users.c.id).where(users.c.is_onboarded.is_(True)))
    }
    if onboarded_user_ids:
        for workspace_id, user_id, role in bind.execute(
            sa.select(members.c.workspace_id, members.c.user_id, members.c.role)
        ):
            if role == "owner" and user_id in onboarded_user_ids:
                onboarded_ws.add(workspace_id)

    if onboarded_ws:
        bind.execute(
            workspaces.update()
            .where(workspaces.c.id.in_(list(onboarded_ws)))
            .values(is_onboarded=True)
        )

    op.drop_column("users", "is_onboarded")


def downgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_onboarded", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    bind = op.get_bind()
    workspaces = _t_workspaces()
    users = _t_users()
    members = _t_members()

    onboarded_ws_ids = {
        row[0]
        for row in bind.execute(sa.select(workspaces.c.id).where(workspaces.c.is_onboarded.is_(True)))
    }
    if onboarded_ws_ids:
        user_ids = {
            row[0]
            for row in bind.execute(
                sa.select(members.c.user_id).where(
                    members.c.workspace_id.in_(list(onboarded_ws_ids))
                )
            )
        }
        if user_ids:
            bind.execute(
                users.update().where(users.c.id.in_(list(user_ids))).values(is_onboarded=True)
            )

    op.drop_column("workspaces", "is_onboarded")
