"""Phase 13 — analytics: compute_analytics_summary() aggregates the tracked
metrics (total/answered calls, average duration, qualified leads,
appointments, conversion rate, AI resolution rate, Receptionist transfers,
integration failures) from real rows, scoped to one workspace and
optionally a date range."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models.appointment import Appointment
from app.models.call import Call
from app.models.human_handoff import HumanHandoff
from app.models.integration_log import IntegrationLog
from app.models.lead import Lead
from app.models.patient import Patient
from app.models.workspace import Workspace
from app.services.analytics import compute_analytics_summary


@pytest.fixture()
def workspace(db_session):
    ws = Workspace(name="Analytics Clinic", slug="analytics-clinic")
    db_session.add(ws)
    db_session.commit()
    return ws


def test_empty_workspace_returns_zeroed_summary(db_session, workspace):
    summary = compute_analytics_summary(db_session, workspace.id)
    assert summary.total_calls == 0
    assert summary.answered_calls == 0
    assert summary.average_duration_seconds is None
    assert summary.qualified_leads == 0
    assert summary.appointments == 0
    assert summary.conversion_rate is None
    assert summary.ai_resolution_rate is None
    assert summary.receptionist_transfers == 0
    assert summary.integration_failures == 0


def test_call_metrics(db_session, workspace):
    now = datetime.now(timezone.utc)
    db_session.add_all([
        Call(workspace_id=workspace.id, direction="inbound", status="completed", started_at=now, duration_seconds=120),
        Call(workspace_id=workspace.id, direction="inbound", status="completed", started_at=now, duration_seconds=180),
        Call(workspace_id=workspace.id, direction="inbound", status="in_progress", started_at=now),
    ])
    db_session.commit()

    summary = compute_analytics_summary(db_session, workspace.id)
    assert summary.total_calls == 3
    assert summary.answered_calls == 3
    assert summary.average_duration_seconds == 150.0  # only the two rows with a duration count


def test_lead_conversion_rate(db_session, workspace):
    db_session.add_all([
        Lead(workspace_id=workspace.id, phone="1", status="new"),
        Lead(workspace_id=workspace.id, phone="2", status="qualifying"),
        Lead(workspace_id=workspace.id, phone="3", status="converted"),
        Lead(workspace_id=workspace.id, phone="4", status="converted"),
    ])
    db_session.commit()

    summary = compute_analytics_summary(db_session, workspace.id)
    assert summary.total_leads == 4
    assert summary.qualified_leads == 3  # qualifying + converted
    assert summary.conversion_rate == 0.5  # 2 converted / 4 total


def test_appointments_count(db_session, workspace):
    patient = Patient(workspace_id=workspace.id, first_name="Jane", last_name="Doe")
    db_session.add(patient)
    db_session.flush()
    start = datetime.now(timezone.utc) + timedelta(days=1)
    db_session.add(Appointment(workspace_id=workspace.id, patient_id=patient.id, start_time=start, end_time=start + timedelta(minutes=30)))
    db_session.commit()

    summary = compute_analytics_summary(db_session, workspace.id)
    assert summary.appointments == 1


def test_receptionist_transfers_and_ai_resolution_rate(db_session, workspace):
    session_with_handoff = uuid.uuid4()
    session_without_handoff = uuid.uuid4()
    now = datetime.now(timezone.utc)

    db_session.add_all([
        Call(workspace_id=workspace.id, direction="inbound", status="completed", started_at=now, conversation_session_id=session_with_handoff),
        Call(workspace_id=workspace.id, direction="inbound", status="completed", started_at=now, conversation_session_id=session_without_handoff),
    ])
    db_session.add(
        HumanHandoff(
            workspace_id=workspace.id, conversation_session_id=session_with_handoff,
            trigger="caller_request", reason="Caller asked for a human", conversation_context=[], call_state={},
        )
    )
    db_session.commit()

    summary = compute_analytics_summary(db_session, workspace.id)
    assert summary.receptionist_transfers == 1
    assert summary.total_calls == 2
    assert summary.ai_resolution_rate == 0.5  # 1 of 2 calls resolved without a human


def test_integration_failures(db_session, workspace):
    db_session.add_all([
        IntegrationLog(workspace_id=workspace.id, category="calendar", provider="google", action="create_event", status="success"),
        IntegrationLog(workspace_id=workspace.id, category="whatsapp", provider="twilio_whatsapp", action="send", status="failure"),
        IntegrationLog(workspace_id=workspace.id, category="whatsapp", provider="twilio_whatsapp", action="send", status="failure"),
    ])
    db_session.commit()

    summary = compute_analytics_summary(db_session, workspace.id)
    assert summary.integration_attempts == 3
    assert summary.integration_failures == 2


def test_date_range_filters_out_older_rows(db_session, workspace):
    old = datetime.now(timezone.utc) - timedelta(days=30)
    recent = datetime.now(timezone.utc)
    db_session.add_all([
        Call(workspace_id=workspace.id, direction="inbound", status="completed", started_at=old, duration_seconds=60),
        Call(workspace_id=workspace.id, direction="inbound", status="completed", started_at=recent, duration_seconds=90),
    ])
    db_session.commit()

    summary = compute_analytics_summary(db_session, workspace.id, since=recent - timedelta(hours=1))
    assert summary.total_calls == 1
    assert summary.average_duration_seconds == 90.0


def test_metrics_are_scoped_to_the_workspace(db_session, workspace):
    other = Workspace(name="Other Clinic", slug="other-clinic")
    db_session.add(other)
    db_session.flush()
    db_session.add(Call(workspace_id=other.id, direction="inbound", status="completed", started_at=datetime.now(timezone.utc)))
    db_session.commit()

    summary = compute_analytics_summary(db_session, workspace.id)
    assert summary.total_calls == 0
