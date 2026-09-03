"""Booking a slot the caller named, without the availability token.

From a live call: check_availability returned five slots, each carrying a
~300 character JWT. Two minutes later book_appointment arrived with
availability_token set to an empty string. The assistant had read the slots
aloud and then failed to copy one back, so the booking died even though
everything else about the call was correct.

The token path still works and is still preferred. These tests cover the
fallback, and that it grants nothing the token path would not.
"""

import uuid
from datetime import date, datetime, time, timedelta

import pytest
from sqlalchemy import select
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.models.appointment import Appointment
from app.models.business_hours import BusinessHours
from app.models.patient import Patient
from app.models.phone_number import PhoneNumber
from app.models.provider import Provider
from app.models.service import Service
from app.models.workspace import Workspace


VAPI_SECRET = "test-vapi-webhook-secret"
CLINIC_LINE = "+15757289021"


@pytest.fixture(autouse=True)
def vapi_secret(monkeypatch):
    monkeypatch.setattr(settings, "vapi_tool_webhook_secret", VAPI_SECRET)


@pytest.fixture()
def clinic(db_session):
    future_date = date.today() + timedelta(days=2)
    workspace = Workspace(name="Karachi Clinic", slug=f"vapi-{uuid.uuid4().hex}", timezone="Asia/Karachi")
    db_session.add(workspace)
    db_session.flush()
    db_session.add_all(
        [
            Service(workspace_id=workspace.id, name="dental cleaning", duration_minutes=30, is_active=True),
            Provider(workspace_id=workspace.id, name="faiza", is_active=True),
            PhoneNumber(workspace_id=workspace.id, number=CLINIC_LINE),
            BusinessHours(
                workspace_id=workspace.id,
                day_of_week=future_date.weekday(),
                open_time=time(9, 0),
                close_time=time(17, 0),
                is_closed=False,
            ),
        ]
    )
    db_session.commit()
    return workspace, future_date


def post(client, tool, body):
    return client.post(
        f"/api/v1/integrations/vapi/tools/{tool}",
        json={**body, "called_number": CLINIC_LINE, "caller_number": "+923245929020"},
        headers={"Authorization": f"Bearer {VAPI_SECRET}"},
    )


def test_spoken_time_of_day_is_understood(client, clinic):
    """The assistant sent preferred_time "morning" and got a 422."""
    workspace, day = clinic
    response = post(
        client,
        "check-availability",
        {"service_name": "dental cleaning", "preferred_date": day.isoformat(), "preferred_time": "morning"},
    )
    assert response.status_code == 200, response.text
    result = response.json()["results"][0]["result"]
    assert result["success"] is True, result
    first = result["available_slots"][0]["start_time"]
    assert first.startswith(f"{day.isoformat()}T09:00")


def test_unreadable_time_falls_back_to_the_whole_day(client, clinic):
    workspace, day = clinic
    response = post(
        client,
        "check-availability",
        {"service_name": "dental cleaning", "preferred_date": day.isoformat(), "preferred_time": "whenever"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["results"][0]["result"]["success"] is True


def test_books_by_date_and_time_when_the_token_is_empty(client, clinic, db_session):
    workspace, day = clinic
    response = post(
        client,
        "book-appointment",
        {
            "availability_token": "",
            "service_name": "dental cleaning",
            "preferred_date": day.isoformat(),
            "preferred_time": "11:00",
            "patient_name": "Ayesha Malik",
            "patient_phone": "0324 5929020",
            "patient_email": "",
        },
    )
    assert response.status_code == 200, response.text
    result = response.json()["results"][0]["result"]
    assert result["success"] is True, result
    assert result["code"] == "BOOKED"

    appointment = db_session.execute(
        select(Appointment).where(Appointment.workspace_id == workspace.id)
    ).scalar_one()
    local = appointment.start_time.astimezone(ZoneInfo("Asia/Karachi"))
    assert (local.hour, local.minute) == (11, 0)

    patient = db_session.execute(
        select(Patient).where(Patient.workspace_id == workspace.id)
    ).scalar_one()
    assert patient.phone == "+923245929020"


def test_a_doctor_is_chosen_when_the_caller_names_none(client, clinic, db_session):
    workspace, day = clinic
    result = post(
        client,
        "book-appointment",
        {
            "service_name": "dental cleaning",
            "preferred_date": day.isoformat(),
            "preferred_time": "10:00",
            "patient_name": "Bilal Sheikh",
            "patient_phone": "+923009876543",
        },
    ).json()["results"][0]["result"]
    assert result["success"] is True, result
    assert result["provider"]["name"] == "faiza"


def test_outside_business_hours_is_still_refused(client, clinic):
    """The fallback must not become a way around the clinic's own hours."""
    workspace, day = clinic
    result = post(
        client,
        "book-appointment",
        {
            "service_name": "dental cleaning",
            "preferred_date": day.isoformat(),
            "preferred_time": "22:00",
            "patient_name": "Ayesha Malik",
            "patient_phone": "+923001234567",
        },
    ).json()["results"][0]["result"]
    assert result["success"] is False
    assert result["code"] in {"SLOT_TAKEN", "CONFLICT"}


def test_double_booking_the_same_slot_is_still_refused(client, clinic):
    workspace, day = clinic
    body = {
        "service_name": "dental cleaning",
        "preferred_date": day.isoformat(),
        "preferred_time": "14:00",
        "patient_phone": "+923001234567",
    }
    first = post(client, "book-appointment", {**body, "patient_name": "Ayesha Malik"}).json()
    assert first["results"][0]["result"]["success"] is True, first
    second = post(
        client, "book-appointment", {**body, "patient_name": "Bilal Sheikh", "patient_phone": "+923009876543"}
    ).json()["results"][0]["result"]
    assert second["success"] is False
    assert second["code"] == "SLOT_TAKEN"


def test_unknown_service_on_the_fallback_path_lists_the_real_ones(client, clinic):
    workspace, day = clinic
    result = post(
        client,
        "book-appointment",
        {
            "service_name": "جنرل چیک اپ",
            "preferred_date": day.isoformat(),
            "preferred_time": "11:00",
            "patient_name": "Ayesha Malik",
            "patient_phone": "+923001234567",
        },
    ).json()["results"][0]["result"]
    assert result["code"] == "SERVICE_NOT_FOUND"
    assert result["available_services"] == ["dental cleaning"]


def test_the_token_path_still_works(client, clinic, db_session):
    workspace, day = clinic
    availability = post(
        client,
        "check-availability",
        {"service_name": "dental cleaning", "preferred_date": day.isoformat()},
    ).json()["results"][0]["result"]
    token = availability["available_slots"][0]["availability_token"]

    result = post(
        client,
        "book-appointment",
        {
            "availability_token": token,
            "patient_name": "Ayesha Malik",
            "patient_phone": "+923001234567",
        },
    ).json()["results"][0]["result"]
    assert result["success"] is True, result


def test_local_number_works_with_no_country_context_at_all(client, clinic, db_session):
    """A domestic caller should never be asked to recite a country code.

    The clinic line here is a US Vapi number and the request carries no
    caller number, so the only thing left to read "0300 1234567" against is
    DEFAULT_PHONE_REGION.
    """
    workspace, day = clinic
    response = client.post(
        "/api/v1/integrations/vapi/tools/book-appointment",
        json={
            "service_name": "dental cleaning",
            "preferred_date": day.isoformat(),
            "preferred_time": "15:00",
            "patient_name": "Ayesha Malik",
            "patient_phone": "0300 1234567",
            "called_number": CLINIC_LINE,
        },
        headers={"Authorization": f"Bearer {VAPI_SECRET}"},
    )
    assert response.status_code == 200, response.text
    result = response.json()["results"][0]["result"]
    assert result["success"] is True, result

    patient = db_session.execute(
        select(Patient).where(Patient.workspace_id == workspace.id)
    ).scalar_one()
    assert patient.phone == "+923001234567"


def test_an_explicit_country_code_still_overrides_the_default(client, clinic, db_session):
    workspace, day = clinic
    result = client.post(
        "/api/v1/integrations/vapi/tools/book-appointment",
        json={
            "service_name": "dental cleaning",
            "preferred_date": day.isoformat(),
            "preferred_time": "15:30",
            "patient_name": "Bilal Sheikh",
            "patient_phone": "+1 415 555 0100",
            "called_number": CLINIC_LINE,
        },
        headers={"Authorization": f"Bearer {VAPI_SECRET}"},
    ).json()["results"][0]["result"]
    assert result["success"] is True, result

    patient = db_session.execute(
        select(Patient).where(Patient.workspace_id == workspace.id, Patient.phone == "+14155550100")
    ).scalar_one()
    assert patient.phone == "+14155550100"
