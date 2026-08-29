import uuid
from datetime import date, datetime, time, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.models.appointment import Appointment
from app.models.business_hours import BusinessHours
from app.models.integration import Integration
from app.models.patient import Patient
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
    workspace = Workspace(name="Vapi Clinic", slug=f"vapi-{uuid.uuid4().hex}", timezone="UTC")
    db_session.add(workspace)
    db_session.flush()
    service = Service(
        workspace_id=workspace.id,
        name="Extended Consultation",
        duration_minutes=45,
        is_active=True,
    )
    provider = Provider(workspace_id=workspace.id, name="Dr. Rivera", is_active=True)
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
    db_session.add(
        Integration(
            workspace_id=workspace.id,
            provider="google_calendar",
            is_active=True,
            config={"calendar_id": f"{workspace.id}@example.com"},
        )
    )
    db_session.commit()
    return workspace, service, provider, future_date


def headers(secret=VAPI_SECRET):
    return {"Authorization": f"Bearer {secret}"}


def availability_payload(service, provider, preferred_date, *, tool_call_id="availability-1"):
    return {
        "message": {
            "type": "tool-calls",
            "toolCallList": [
                {
                    "id": tool_call_id,
                    "name": "check_availability",
                    "arguments": {
                        "service_id": str(service.id),
                        "provider_id": str(provider.id),
                        "preferred_date": preferred_date.isoformat(),
                        "preferred_time": "10:00",
                        "max_slots": 3,
                    },
                }
            ],
        },
        "call": {"id": "call-availability"},
    }


def booking_payload(token, *, call_id="call-booking", tool_call_id="booking-1", phone="+14155550100"):
    return {
        "message": {
            "type": "tool-calls",
            "toolCallList": [
                {
                    "id": tool_call_id,
                    "name": "book_appointment",
                    "arguments": {
                        "availability_token": token,
                        "patient_name": "Jane Patient",
                        "patient_phone": phone,
                        "patient_email": "jane@example.com",
                    },
                }
            ],
        },
        "call": {"id": call_id},
    }


def get_token(client, clinic):
    workspace, service, provider, preferred_date = clinic
    response = client.post(
        f"/api/v1/integrations/vapi/workspaces/{workspace.id}/tools/check-availability",
        headers=headers(),
        json=availability_payload(service, provider, preferred_date),
    )
    assert response.status_code == 200, response.text
    result = response.json()["results"][0]["result"]
    assert result["success"] is True
    return result["available_slots"][0]["availability_token"], result


def test_vapi_tool_rejects_invalid_authentication(client, clinic):
    workspace, service, provider, preferred_date = clinic
    response = client.post(
        f"/api/v1/integrations/vapi/workspaces/{workspace.id}/tools/check-availability",
        headers=headers("wrong-secret"),
        json=availability_payload(service, provider, preferred_date),
    )
    assert response.status_code == 401


def test_valid_vapi_availability_request_returns_duration_slots_and_token(client, clinic):
    _, result = get_token(client, clinic)
    assert result["timezone"] == "UTC"
    assert result["service"]["name"] == "Extended Consultation"
    assert result["service"]["duration_minutes"] == 45
    assert len(result["available_slots"]) == 3
    first = result["available_slots"][0]
    assert datetime.fromisoformat(first["end_time"]) - datetime.fromisoformat(first["start_time"]) == timedelta(minutes=45)
    assert first["availability_token"]


def test_successful_vapi_booking_creates_patient_appointment_calendar_and_notifications(client, db_session, clinic):
    workspace, service, provider, _ = clinic
    token, _ = get_token(client, clinic)
    response = client.post(
        f"/api/v1/integrations/vapi/workspaces/{workspace.id}/tools/book-appointment",
        headers=headers(),
        json=booking_payload(token),
    )
    assert response.status_code == 200, response.text
    result = response.json()["results"][0]
    assert result["toolCallId"] == "booking-1"
    assert result["result"]["success"] is True
    assert result["result"]["calendar_synced"] is True

    appointment = db_session.execute(
        select(Appointment).where(Appointment.workspace_id == workspace.id)
    ).scalar_one()
    assert appointment.provider_id == provider.id
    assert appointment.service_id == service.id
    assert appointment.end_time - appointment.start_time == timedelta(minutes=45)
    assert appointment.external_calendar_event_id is not None
    patient = db_session.get(Patient, appointment.patient_id)
    assert patient.phone == "+14155550100"
    assert patient.email == "jane@example.com"


def test_vapi_booking_retry_is_idempotent(client, db_session, clinic):
    workspace, _, _, _ = clinic
    token, _ = get_token(client, clinic)
    payload = booking_payload(token, call_id="same-call", tool_call_id="same-tool")

    first = client.post(
        f"/api/v1/integrations/vapi/workspaces/{workspace.id}/tools/book-appointment",
        headers=headers(),
        json=payload,
    )
    second = client.post(
        f"/api/v1/integrations/vapi/workspaces/{workspace.id}/tools/book-appointment",
        headers=headers(),
        json=payload,
    )
    assert first.json()["results"][0]["result"]["success"] is True
    assert second.json()["results"][0]["result"]["success"] is True
    assert second.json()["results"][0]["result"]["idempotent_replay"] is True
    count = db_session.execute(
        select(func.count()).select_from(Appointment).where(Appointment.workspace_id == workspace.id)
    ).scalar_one()
    assert count == 1


def test_vapi_booking_prevents_overlapping_patient_duplicate(client, db_session, clinic):
    workspace, _, _, _ = clinic
    token, _ = get_token(client, clinic)
    first = client.post(
        f"/api/v1/integrations/vapi/workspaces/{workspace.id}/tools/book-appointment",
        headers=headers(),
        json=booking_payload(token, call_id="call-one", tool_call_id="tool-one"),
    )
    second = client.post(
        f"/api/v1/integrations/vapi/workspaces/{workspace.id}/tools/book-appointment",
        headers=headers(),
        json=booking_payload(token, call_id="call-two", tool_call_id="tool-two"),
    )
    assert first.json()["results"][0]["result"]["success"] is True
    assert second.json()["results"][0]["result"]["success"] is False
    assert second.json()["results"][0]["result"]["code"] == "DUPLICATE_BOOKING"


def test_vapi_booking_rechecks_and_rejects_slot_conflict(client, db_session, clinic):
    workspace, service, provider, _ = clinic
    token, availability = get_token(client, clinic)
    selected = availability["available_slots"][0]
    start = datetime.fromisoformat(selected["start_time"]).astimezone(timezone.utc)
    end = start + timedelta(minutes=service.duration_minutes)
    blocking_patient = Patient(
        workspace_id=workspace.id,
        first_name="Existing",
        last_name="Patient",
        phone="+14155550199",
    )
    db_session.add(blocking_patient)
    db_session.flush()
    db_session.add(
        Appointment(
            workspace_id=workspace.id,
            patient_id=blocking_patient.id,
            provider_id=provider.id,
            service_id=service.id,
            start_time=start,
            end_time=end,
            status="scheduled",
        )
    )
    db_session.commit()

    response = client.post(
        f"/api/v1/integrations/vapi/workspaces/{workspace.id}/tools/book-appointment",
        headers=headers(),
        json=booking_payload(token, phone="+14155550155"),
    )
    result = response.json()["results"][0]["result"]
    assert result["success"] is False
    assert result["code"] == "SLOT_TAKEN"
