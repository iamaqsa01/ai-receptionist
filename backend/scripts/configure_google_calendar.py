"""Configure one workspace to use its own Google Calendar.

Run from the backend directory after setting DATABASE_URL (or POSTGRES_*):

    python -m scripts.configure_google_calendar \
        --workspace-slug my-clinic \
        --calendar-id clinic@example.com

Service-account credentials remain server-level environment variables. This
script stores only the non-secret calendar ID in the existing integrations
table.
"""

from __future__ import annotations

import argparse
import uuid

from sqlalchemy import select

from app.database.session import SessionLocal
from app.models.integration import Integration
from app.models.workspace import Workspace


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    workspace = parser.add_mutually_exclusive_group(required=True)
    workspace.add_argument("--workspace-id", type=uuid.UUID)
    workspace.add_argument("--workspace-slug")
    parser.add_argument("--calendar-id", required=True)
    return parser.parse_args()


def main() -> None:
    args = _arguments()
    calendar_id = args.calendar_id.strip()
    if not calendar_id:
        raise SystemExit("--calendar-id cannot be blank")

    with SessionLocal() as db:
        workspace_stmt = select(Workspace)
        if args.workspace_id:
            workspace_stmt = workspace_stmt.where(Workspace.id == args.workspace_id)
        else:
            workspace_stmt = workspace_stmt.where(Workspace.slug == args.workspace_slug)
        workspace = db.execute(workspace_stmt).scalar_one_or_none()
        if workspace is None:
            raise SystemExit("Workspace not found")

        integrations = list(
            db.execute(
                select(Integration).where(
                    Integration.workspace_id == workspace.id,
                    Integration.provider == "google_calendar",
                )
            ).scalars()
        )
        if len(integrations) > 1:
            raise SystemExit(
                "Multiple Google Calendar integrations exist for this workspace; "
                "resolve the duplicates before configuration"
            )

        if integrations:
            integration = integrations[0]
            integration.config = {**integration.config, "calendar_id": calendar_id}
            integration.is_active = True
            action = "updated"
        else:
            integration = Integration(
                workspace_id=workspace.id,
                provider="google_calendar",
                config={"calendar_id": calendar_id},
                is_active=True,
            )
            action = "created"

        db.add(integration)
        db.commit()
        print(
            f"Google Calendar integration {action}: "
            f"workspace={workspace.slug!r}, calendar_id={calendar_id!r}"
        )


if __name__ == "__main__":
    main()
