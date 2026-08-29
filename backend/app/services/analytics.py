import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.appointment import Appointment
from app.models.call import Call
from app.models.human_handoff import HumanHandoff
from app.models.integration_log import IntegrationLog
from app.models.lead import Lead

# A lead counts as "qualified" once the caller has given enough to act on —
# past the bare "new" stage, whether or not they've actually converted yet.
_QUALIFIED_LEAD_STATUSES = ("qualifying", "converted")
# Every status a Call row can currently have represents a call the AI
# actually answered (CallSession only ever creates a Call row once the
# telephony pipeline picks up — see app.telephony.session._create_call_row).
# There is no "missed"/"no_answer" tracking yet (that would require knowing
# about calls that never reached the AI at all, which is out of this
# system's visibility), so answered_calls is every non-failed row.
_ANSWERED_CALL_STATUSES = ("in_progress", "completed")


@dataclass
class AnalyticsSummary:
    workspace_id: uuid.UUID
    since: datetime | None
    until: datetime | None

    total_calls: int
    answered_calls: int
    average_duration_seconds: float | None
    qualified_leads: int
    total_leads: int
    appointments: int
    conversion_rate: float | None
    ai_resolution_rate: float | None
    receptionist_transfers: int
    integration_failures: int
    integration_attempts: int


def _in_range(column, since: datetime | None, until: datetime | None):
    clauses = []
    if since is not None:
        clauses.append(column >= since)
    if until is not None:
        clauses.append(column <= until)
    return clauses


def compute_analytics_summary(
    db: Session,
    workspace_id: uuid.UUID,
    *,
    since: datetime | None = None,
    until: datetime | None = None,
) -> AnalyticsSummary:
    """Aggregates the Phase 13 metrics for one workspace, optionally scoped
    to a date range (each metric is windowed on the timestamp most relevant
    to it — Call.started_at for calls, Lead.created_at for leads,
    Appointment.created_at for appointments, HumanHandoff.created_at for
    transfers, IntegrationLog.created_at for integration health)."""

    call_filters = [Call.workspace_id == workspace_id, *_in_range(Call.started_at, since, until)]
    total_calls = db.execute(select(func.count()).select_from(Call).where(*call_filters)).scalar_one()
    answered_calls = db.execute(
        select(func.count()).select_from(Call).where(*call_filters, Call.status.in_(_ANSWERED_CALL_STATUSES))
    ).scalar_one()
    average_duration = db.execute(
        select(func.avg(Call.duration_seconds)).where(*call_filters, Call.duration_seconds.isnot(None))
    ).scalar_one()

    lead_filters = [Lead.workspace_id == workspace_id, *_in_range(Lead.created_at, since, until)]
    total_leads = db.execute(select(func.count()).select_from(Lead).where(*lead_filters)).scalar_one()
    qualified_leads = db.execute(
        select(func.count()).select_from(Lead).where(*lead_filters, Lead.status.in_(_QUALIFIED_LEAD_STATUSES))
    ).scalar_one()
    converted_leads = db.execute(
        select(func.count()).select_from(Lead).where(*lead_filters, Lead.status == "converted")
    ).scalar_one()
    conversion_rate = (converted_leads / total_leads) if total_leads else None

    appointment_filters = [Appointment.workspace_id == workspace_id, *_in_range(Appointment.created_at, since, until)]
    appointments = db.execute(select(func.count()).select_from(Appointment).where(*appointment_filters)).scalar_one()

    handoff_filters = [HumanHandoff.workspace_id == workspace_id, *_in_range(HumanHandoff.created_at, since, until)]
    receptionist_transfers = db.execute(
        select(func.count()).select_from(HumanHandoff).where(*handoff_filters)
    ).scalar_one()

    # A call "needed a human" if any HumanHandoff shares its conversation
    # session id — joined via Call.conversation_session_id, set when the
    # Call row is created (see app.telephony.session._create_call_row).
    calls_needing_human = db.execute(
        select(func.count(func.distinct(Call.id)))
        .select_from(Call)
        .join(HumanHandoff, HumanHandoff.conversation_session_id == Call.conversation_session_id)
        .where(*call_filters, Call.conversation_session_id.isnot(None))
    ).scalar_one()
    ai_resolution_rate = ((total_calls - calls_needing_human) / total_calls) if total_calls else None

    integration_filters = [
        IntegrationLog.workspace_id == workspace_id, *_in_range(IntegrationLog.created_at, since, until)
    ]
    integration_attempts = db.execute(
        select(func.count()).select_from(IntegrationLog).where(*integration_filters)
    ).scalar_one()
    integration_failures = db.execute(
        select(func.count()).select_from(IntegrationLog).where(*integration_filters, IntegrationLog.status == "failure")
    ).scalar_one()

    return AnalyticsSummary(
        workspace_id=workspace_id,
        since=since,
        until=until,
        total_calls=total_calls,
        answered_calls=answered_calls,
        average_duration_seconds=float(average_duration) if average_duration is not None else None,
        qualified_leads=qualified_leads,
        total_leads=total_leads,
        appointments=appointments,
        conversion_rate=conversion_rate,
        ai_resolution_rate=ai_resolution_rate,
        receptionist_transfers=receptionist_transfers,
        integration_failures=integration_failures,
        integration_attempts=integration_attempts,
    )
