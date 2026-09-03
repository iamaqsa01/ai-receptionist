"""Regressions for booking failures seen on live Vapi calls.

The existing Vapi suite only ever sends tidy payloads: a real email address
and a phone number already in E.164. Real assistants do neither, and each
test here reproduces a payload that failed in production.
"""

import uuid
from datetime import date, time, timedelta

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models.appointment import Appointment
from app.models.business_hours import BusinessHours
from app.models.patient import Patient
from app.models.provider import Provider
from app.models.service import Service
from app.models.workspace import Workspace


VAPI_SECRET = "test-vapi-webhook-secret"

# The caller is dialling from a Pakistani mobile. That is what lets the
# backend read back a number the caller gave without a country code.
CALLER = {"id": "call-live", "customer": {"number": "+923005550100"}}


@pytest.fixture(autouse=True)
def vapi_secret(monkeypatch):
    monkeypatch.setattr(settings, "vapi_tool_webhook_secret", VAPI_SECRET)


@pytest.fixture()
def clinic(db_session):
    future_date = date.today() + timedelta(days=7)
    workspace = Workspace(name="Regression Clinic", slug=f"vapi-{uuid.uuid4().hex}", timezone="UTC")
    db_session.add(workspace)
    db_session.flush()
    service = Service(
        workspace_id=workspace.id, name="Consultation", duration_minutes=30, is_active=True
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


def slots(client, clinic, *, max_slots=3):
    workspace, service, provider, preferred_date = clinic
    response = client.post(
        f"/api/v1/integrations/vapi/workspaces/{workspace.id}/tools/check-availability",
        json={
            "message": {
                "type": "tool-calls",
                "toolCallList": [
                    {
                        "id": "availability-1",
                        "name": "check_availability",
                        "arguments": {
                            "service_id": str(service.id),
                            "provider_id": str(provider.id),
                            "preferred_date": preferred_date.isoformat(),
                            "max_slots": max_slots,
                        },
                    }
                ],
            },
            "call": CALLER,
        },
        headers=headers(),
    )
    assert response.status_code == 200, response.text
    result = response.json()["results"][0]["result"]
    assert result["success"] is True, result
    return [slot["availability_token"] for slot in result["available_slots"]]


def booking_body(token, *, tool_call_id="booking-1", **overrides):
    arguments = {
        "availability_token": token,
        "patient_name": "Ayesha Malik",
        "patient_phone": "+923001234567",
    }
    arguments.update(overrides)
    return {
        "message": {
            "type": "tool-calls",
            "toolCallList": [
                {"id": tool_call_id, "name": "book_appointment", "arguments": arguments}
            ],
        },
        "call": CALLER,
    }


def book(client, workspace, body):
    return client.post(
        f"/api/v1/integrations/vapi/workspaces/{workspace.id}/tools/book-appointment",
        json=body,
        headers=headers(),
    )


@pytest.mark.parametrize("blank", ["", "null", "none", "N/A"])
def test_blank_email_placeholder_still_books(client, clinic, blank):
    """The assistant sends a placeholder for an email it never collected.

    This failed schema validation and returned HTTP 422, so Vapi received no
    tool result at all and the caller heard silence.
    """
    workspace = clinic[0]
    token = slots(client, clinic)[0]
    response = book(client, workspace, booking_body(token, patient_email=blank))
    assert response.status_code == 200, response.text
    result = response.json()["results"][0]["result"]
    assert result["success"] is True, result
    assert result["code"] == "BOOKED"


def test_blank_reason_placeholder_still_books(client, clinic):
    workspace = clinic[0]
    token = slots(client, clinic)[0]
    response = book(client, workspace, booking_body(token, reason="none"))
    assert response.status_code == 200, response.text
    assert response.json()["results"][0]["result"]["success"] is True


def test_local_format_phone_is_normalised(client, clinic, db_session):
    """A caller says "oh three double-oh...", not "plus nine two".

    The number is read against the caller's own country and stored E.164.
    """
    workspace = clinic[0]
    token = slots(client, clinic)[0]
    response = book(client, workspace, booking_body(token, patient_phone="0300 1234567"))
    assert response.status_code == 200, response.text
    assert response.json()["results"][0]["result"]["success"] is True

    patient = db_session.execute(
        select(Patient).where(Patient.workspace_id == workspace.id)
    ).scalar_one()
    assert patient.phone == "+923001234567"


def test_explicit_country_code_still_wins(client, clinic, db_session):
    workspace = clinic[0]
    token = slots(client, clinic)[0]
    response = book(client, workspace, booking_body(token, patient_phone="+1 415 555 0100"))
    assert response.status_code == 200, response.text
    assert response.json()["results"][0]["result"]["success"] is True
    patient = db_session.execute(
        select(Patient).where(Patient.workspace_id == workspace.id)
    ).scalar_one()
    assert patient.phone == "+14155550100"


def test_unreadable_phone_returns_a_tool_result_not_an_error(client, clinic):
    workspace = clinic[0]
    token = slots(client, clinic)[0]
    response = book(client, workspace, booking_body(token, patient_phone="12345"))
    assert response.status_code == 200, response.text
    result = response.json()["results"][0]["result"]
    assert result["success"] is False
    assert result["code"] == "INVALID_PATIENT_PHONE"


def test_booking_without_a_call_object_still_books(client, clinic):
    """The call id is only an idempotency key, not proof of a real booking.

    A payload carrying no call object used to be refused with
    MISSING_CALL_ID even though every booking detail was present.
    """
    workspace = clinic[0]
    token = slots(client, clinic)[0]
    body = booking_body(token)
    body.pop("call")
    response = book(client, workspace, body)
    assert response.status_code == 200, response.text
    result = response.json()["results"][0]["result"]
    assert result["success"] is True, result
    assert result["idempotent_replay"] is False


def test_retry_of_the_same_tool_call_is_idempotent(client, clinic, db_session):
    """Vapi retries a tool call on timeout. That must not double-book."""
    workspace = clinic[0]
    token = slots(client, clinic)[0]
    body = booking_body(token)
    first = book(client, workspace, body).json()["results"][0]["result"]
    second = book(client, workspace, body).json()["results"][0]["result"]
    assert first["success"] is True and second["success"] is True
    assert first["appointment_id"] == second["appointment_id"]
    assert second["idempotent_replay"] is True

    count = len(
        db_session.execute(
            select(Appointment).where(Appointment.workspace_id == workspace.id)
        ).scalars().all()
    )
    assert count == 1


def test_booking_still_requires_vapi_authentication(client, clinic):
    workspace = clinic[0]
    token = slots(client, clinic)[0]
    response = client.post(
        f"/api/v1/integrations/vapi/workspaces/{workspace.id}/tools/book-appointment",
        json=booking_body(token),
    )
    assert response.status_code == 401
