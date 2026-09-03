"""Regressions for the flat request body a live Vapi assistant actually sends.

A Vapi custom tool can be configured to POST its arguments directly rather
than inside the ``message.toolCallList`` envelope. Production assistants do
this, and the payloads below are taken verbatim from a failed call: empty
strings for optional arguments, and a year the model invented.
"""

import uuid
from datetime import date, time, timedelta

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models.appointment import Appointment
from app.models.business_hours import BusinessHours
from app.models.provider import Provider
from app.models.service import Service
from app.models.workspace import Workspace


VAPI_SECRET = "test-vapi-webhook-secret"


@pytest.fixture(autouse=True)
def vapi_secret(monkeypatch):
    monkeypatch.setattr(settings, "vapi_tool_webhook_secret", VAPI_SECRET)


@pytest.fixture()
def clinic(db_session):
    future_date = date.today() + timedelta(days=7)
    workspace = Workspace(name="Flat Clinic", slug=f"vapi-{uuid.uuid4().hex}", timezone="UTC")
    db_session.add(workspace)
    db_session.flush()
    service = Service(
        workspace_id=workspace.id, name="General Check Up", duration_minutes=30, is_active=True
    )
    provider = Provider(workspace_id=workspace.id, name="Dr. Ahmed", is_active=True)
    db_session.add_all([service, provider])
    db_session.add(
        BusinessHours(
            workspace_id=workspace.id,
            day_of_week=future_date.weekday(),
            open_time=time(9, 0),
            close_time=time(17, 0),
            is_closed=False,
        )
    )
    db_session.commit()
    return workspace, service, provider, future_date


def headers():
    return {"Authorization": f"Bearer {VAPI_SECRET}"}


def post(client, workspace, tool, body):
    return client.post(
        f"/api/v1/integrations/vapi/workspaces/{workspace.id}/tools/{tool}",
        json=body,
        headers=headers(),
    )


def test_flat_availability_body_with_empty_optionals(client, clinic):
    """The exact shape a live assistant sent, which returned HTTP 422.

    No ``message`` envelope, and empty strings where the model had nothing
    to supply. Every one of those was previously fatal.
    """
    workspace, service, provider, preferred_date = clinic
    response = post(
        client,
        workspace,
        "check-availability",
        {
            "max_slots": "",
            "service_name": "General Check Up",
            "provider_name": "",
            "preferred_date": preferred_date.isoformat(),
            "preferred_time": "16:00",
        },
    )
    assert response.status_code == 200, response.text
    result = response.json()["results"][0]["result"]
    assert result["success"] is True, result
    assert result["available_slots"]


def test_flat_body_round_trip_books_an_appointment(client, clinic, db_session):
    workspace, service, provider, preferred_date = clinic
    availability = post(
        client,
        workspace,
        "check-availability",
        {"service_name": "General Check Up", "preferred_date": preferred_date.isoformat()},
    )
    assert availability.status_code == 200, availability.text
    token = availability.json()["results"][0]["result"]["available_slots"][0]["availability_token"]

    booking = post(
        client,
        workspace,
        "book-appointment",
        {
            "availability_token": token,
            "patient_name": "Ayesha Malik",
            "patient_phone": "+923001234567",
            "patient_email": "",
            "reason": "",
        },
    )
    assert booking.status_code == 200, booking.text
    result = booking.json()["results"][0]["result"]
    assert result["success"] is True, result
    assert result["code"] == "BOOKED"

    count = len(
        db_session.execute(
            select(Appointment).where(Appointment.workspace_id == workspace.id)
        ).scalars().all()
    )
    assert count == 1


def test_two_flat_bookings_in_one_call_are_not_collapsed(client, clinic, db_session):
    workspace, service, provider, preferred_date = clinic
    availability = post(
        client,
        workspace,
        "check-availability",
        {
            "service_name": "General Check Up",
            "preferred_date": preferred_date.isoformat(),
            "max_slots": 6,
        },
    )
    tokens = [
        slot["availability_token"]
        for slot in availability.json()["results"][0]["result"]["available_slots"]
    ]
    # 15-minute slot spacing against a 30-minute service, so neighbouring
    # slots overlap. Take two that do not.
    first = post(
        client,
        workspace,
        "book-appointment",
        {
            "availability_token": tokens[0],
            "patient_name": "Ayesha Malik",
            "patient_phone": "+923001234567",
        },
    ).json()["results"][0]["result"]
    second = post(
        client,
        workspace,
        "book-appointment",
        {
            "availability_token": tokens[3],
            "patient_name": "Bilal Sheikh",
            "patient_phone": "+923009876543",
        },
    ).json()["results"][0]["result"]

    assert first["success"] is True, first
    assert second["success"] is True, second
    assert first["appointment_id"] != second["appointment_id"]
    assert second["idempotent_replay"] is False


def test_identical_flat_retry_stays_idempotent(client, clinic, db_session):
    workspace, service, provider, preferred_date = clinic
    availability = post(
        client,
        workspace,
        "check-availability",
        {"service_name": "General Check Up", "preferred_date": preferred_date.isoformat()},
    )
    token = availability.json()["results"][0]["result"]["available_slots"][0]["availability_token"]
    body = {
        "availability_token": token,
        "patient_name": "Ayesha Malik",
        "patient_phone": "+923001234567",
    }
    first = post(client, workspace, "book-appointment", body).json()["results"][0]["result"]
    second = post(client, workspace, "book-appointment", body).json()["results"][0]["result"]
    assert first["appointment_id"] == second["appointment_id"]
    assert second["idempotent_replay"] is True

    count = len(
        db_session.execute(
            select(Appointment).where(Appointment.workspace_id == workspace.id)
        ).scalars().all()
    )
    assert count == 1


def test_past_date_is_named_rather_than_reported_as_full(client, clinic):
    """The assistant sent 2024-10-06 during a call in 2026.

    A past date used to come back as "no slots available", which the
    assistant relays as a full diary. It now says what is actually wrong so
    the assistant can ask the caller which year they meant.
    """
    workspace = clinic[0]
    response = post(
        client,
        workspace,
        "check-availability",
        {"service_name": "General Check Up", "preferred_date": "2024-10-06"},
    )
    assert response.status_code == 200, response.text
    result = response.json()["results"][0]["result"]
    assert result["success"] is False
    assert result["code"] == "DATE_IN_THE_PAST"


def test_envelope_payload_still_works(client, clinic):
    """The toolCallList shape must keep working alongside the flat one."""
    workspace, service, provider, preferred_date = clinic
    response = post(
        client,
        workspace,
        "check-availability",
        {
            "message": {
                "type": "tool-calls",
                "toolCallList": [
                    {
                        "id": "availability-1",
                        "name": "check_availability",
                        "arguments": {
                            "service_id": str(service.id),
                            "preferred_date": preferred_date.isoformat(),
                        },
                    }
                ],
            },
            "call": {"id": "call-1"},
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["results"][0]["result"]["success"] is True


def test_empty_body_is_still_rejected(client, clinic):
    workspace = clinic[0]
    response = post(client, workspace, "check-availability", {})
    assert response.status_code == 422
