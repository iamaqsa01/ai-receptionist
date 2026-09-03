"""Phone-number routing for the flat tool body used across multiple clinics.

A Vapi custom tool posting a flat body carries no call object, so the
dynamic (phone-number routed) endpoints had nothing to resolve a workspace
from. Vapi's Static Body Fields supply the numbers instead, filled from
call signalling rather than by the model, so a caller cannot talk their way
into another clinic's diary.
"""

import uuid
from datetime import date, time, timedelta

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models.appointment import Appointment
from app.models.business_hours import BusinessHours
from app.models.phone_number import PhoneNumber
from app.models.provider import Provider
from app.models.service import Service
from app.models.workspace import Workspace


VAPI_SECRET = "test-vapi-webhook-secret"


@pytest.fixture(autouse=True)
def vapi_secret(monkeypatch):
    monkeypatch.setattr(settings, "vapi_tool_webhook_secret", VAPI_SECRET)


def make_clinic(db_session, *, name, service_name, provider_name, clinic_line):
    future_date = date.today() + timedelta(days=7)
    workspace = Workspace(name=name, slug=f"vapi-{uuid.uuid4().hex}", timezone="UTC")
    db_session.add(workspace)
    db_session.flush()
    db_session.add_all(
        [
            Service(
                workspace_id=workspace.id,
                name=service_name,
                duration_minutes=30,
                is_active=True,
            ),
            Provider(workspace_id=workspace.id, name=provider_name, is_active=True),
            PhoneNumber(workspace_id=workspace.id, number=clinic_line),
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


@pytest.fixture()
def two_clinics(db_session):
    first = make_clinic(
        db_session,
        name="North Clinic",
        service_name="Dental Cleaning",
        provider_name="Dr. North",
        clinic_line="+15550001111",
    )
    second = make_clinic(
        db_session,
        name="South Clinic",
        service_name="Eye Test",
        provider_name="Dr. South",
        clinic_line="+15550002222",
    )
    return first, second


def headers():
    return {"Authorization": f"Bearer {VAPI_SECRET}"}


def post(client, tool, body):
    return client.post(f"/api/v1/integrations/vapi/tools/{tool}", json=body, headers=headers())


def test_static_body_fields_route_to_the_dialled_clinic(client, two_clinics):
    (north, north_date), (south, south_date) = two_clinics

    response = post(
        client,
        "check-availability",
        {
            "service_name": "Dental Cleaning",
            "preferred_date": north_date.isoformat(),
            "called_number": "+15550001111",
            "caller_number": "+923005550100",
            "call_id": "call-north-1",
        },
    )
    assert response.status_code == 200, response.text
    result = response.json()["results"][0]["result"]
    assert result["success"] is True, result


def test_the_other_clinics_service_is_not_reachable_on_this_line(client, two_clinics):
    """Routing decides the tenant, so the diary must not leak across clinics."""
    (north, north_date), (south, south_date) = two_clinics

    response = post(
        client,
        "check-availability",
        {
            "service_name": "Eye Test",
            "preferred_date": north_date.isoformat(),
            "called_number": "+15550001111",
        },
    )
    assert response.status_code == 200, response.text
    result = response.json()["results"][0]["result"]
    assert result["success"] is False
    assert result["code"] == "SERVICE_NOT_FOUND"
    assert result["available_services"] == ["Dental Cleaning"]


def test_flat_body_routes_and_books_end_to_end(client, two_clinics, db_session):
    (north, north_date), _ = two_clinics
    availability = post(
        client,
        "check-availability",
        {
            "service_name": "Dental Cleaning",
            "preferred_date": north_date.isoformat(),
            "called_number": "+15550001111",
            "caller_number": "+923005550100",
            "call_id": "call-north-2",
        },
    )
    token = availability.json()["results"][0]["result"]["available_slots"][0]["availability_token"]

    booking = post(
        client,
        "book-appointment",
        {
            "availability_token": token,
            "patient_name": "Ayesha Malik",
            "patient_phone": "0300 1234567",
            "patient_email": "",
            "called_number": "+15550001111",
            "caller_number": "+923005550100",
            "call_id": "call-north-2",
        },
    )
    assert booking.status_code == 200, booking.text
    result = booking.json()["results"][0]["result"]
    assert result["success"] is True, result

    appointment = db_session.execute(
        select(Appointment).where(Appointment.workspace_id == north.id)
    ).scalar_one()
    assert appointment.status == "scheduled"


def test_caller_number_lets_a_local_patient_number_be_read(client, two_clinics, db_session):
    """caller_number is what supplies the country for a local-format number."""
    (north, north_date), _ = two_clinics
    availability = post(
        client,
        "check-availability",
        {
            "service_name": "Dental Cleaning",
            "preferred_date": north_date.isoformat(),
            "called_number": "+15550001111",
            "caller_number": "+923005550100",
        },
    )
    token = availability.json()["results"][0]["result"]["available_slots"][0]["availability_token"]
    post(
        client,
        "book-appointment",
        {
            "availability_token": token,
            "patient_name": "Ayesha Malik",
            "patient_phone": "0300 1234567",
            "called_number": "+15550001111",
            "caller_number": "+923005550100",
        },
    )
    from app.models.patient import Patient

    patient = db_session.execute(
        select(Patient).where(Patient.workspace_id == north.id)
    ).scalar_one()
    assert patient.phone == "+923001234567"


def test_flat_body_without_any_routing_field_is_refused(client, two_clinics):
    response = post(
        client,
        "check-availability",
        {"service_name": "Dental Cleaning", "preferred_date": date.today().isoformat()},
    )
    assert response.status_code == 400


def test_routing_fields_are_not_treated_as_tool_arguments(client, two_clinics):
    """They must not leak into the arguments the tool schemas validate."""
    from app.schemas.vapi import VapiToolRequest

    payload = VapiToolRequest.model_validate(
        {
            "service_name": "Dental Cleaning",
            "preferred_date": "2030-01-01",
            "called_number": "+15550001111",
            "caller_number": "+923005550100",
            "call_id": "call-1",
        }
    )
    arguments = payload.message.tool_call_list[0].arguments
    assert "called_number" not in arguments
    assert "caller_number" not in arguments
    assert "call_id" not in arguments
    assert payload.call_id == "call-1"
    assert payload.routing_phone_numbers == ["+15550001111", "+923005550100"]
