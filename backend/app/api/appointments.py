import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import TenantContext, get_current_onboarded_tenant, require_permission
from app.database.session import SessionLocal, get_db
from app.integrations.notifications.service import NotificationService
from app.models.appointment import Appointment
from app.models.patient import Patient
from app.models.provider import Provider
from app.models.service import Service
from app.schemas.appointment import AppointmentCreate, AppointmentOut
from app.services.audit import record_audit_log

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workspaces/{workspace_id}/appointments", tags=["appointments"], dependencies=[Depends(get_current_onboarded_tenant)])


def _send_booking_confirmation(appointment_id: uuid.UUID) -> None:
    """Runs after the HTTP response is sent (FastAPI BackgroundTasks) on
    its own short-lived DB session. Only ever invoked once the appointment
    row is committed, so it never notifies for a booking that failed. A
    messaging-provider outage is contained here — it's recorded as a
    "failed" NotificationMessage row (retryable) and never surfaced to the
    caller."""
    db = SessionLocal()
    try:
        appointment = db.get(Appointment, appointment_id)
        if appointment is None:
            return
        patient = db.get(Patient, appointment.patient_id)
        if patient is None:
            return
        provider = db.get(Provider, appointment.provider_id) if appointment.provider_id else None
        service = db.get(Service, appointment.service_id) if appointment.service_id else None
        summary = service.name if service is not None else "your appointment"
        NotificationService(db=db).notify_appointment_event(
            "appointment_confirmation", appointment, patient, service_summary=summary, provider=provider
        )
    except Exception:
        logger.exception("failed to dispatch booking confirmation for appointment=%s", appointment_id)
    finally:
        db.close()


@router.post("", response_model=AppointmentOut, status_code=status.HTTP_201_CREATED)
def create_appointment(
    payload: AppointmentCreate,
    background_tasks: BackgroundTasks,
    ctx: TenantContext = Depends(require_permission("appointments:write")),
    db: Session = Depends(get_db),
) -> Appointment:
    # Every referenced foreign key must belong to this same workspace —
    # otherwise a caller could link an appointment to another tenant's
    # patient/provider/service record (tenant-isolation / IDOR).
    patient = db.execute(
        select(Patient).where(Patient.id == payload.patient_id, Patient.workspace_id == ctx.workspace_id)
    ).scalar_one_or_none()
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

    if payload.provider_id is not None:
        provider = db.execute(
            select(Provider).where(Provider.id == payload.provider_id, Provider.workspace_id == ctx.workspace_id)
        ).scalar_one_or_none()
        if provider is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")

    if payload.service_id is not None:
        service = db.execute(
            select(Service).where(Service.id == payload.service_id, Service.workspace_id == ctx.workspace_id)
        ).scalar_one_or_none()
        if service is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")

    appointment = Appointment(workspace_id=ctx.workspace_id, status="scheduled", **payload.model_dump())
    db.add(appointment)
    db.commit()
    db.refresh(appointment)
    record_audit_log(
        db, action="appointment.created", resource_type="appointment",
        workspace_id=ctx.workspace_id, actor_user_id=ctx.user.id, resource_id=appointment.id,
    )
    # DB write is committed above — trigger the confirmation immediately,
    # off the request path so a messaging-provider outage can't fail the
    # booking response.
    background_tasks.add_task(_send_booking_confirmation, appointment.id)
    return appointment


@router.get("", response_model=list[AppointmentOut])
def list_appointments(
    ctx: TenantContext = Depends(require_permission("appointments:read")),
    db: Session = Depends(get_db),
) -> list[Appointment]:
    return list(
        db.execute(select(Appointment).where(Appointment.workspace_id == ctx.workspace_id)).scalars()
    )


@router.get("/{appointment_id}", response_model=AppointmentOut)
def get_appointment(
    appointment_id: uuid.UUID,
    ctx: TenantContext = Depends(require_permission("appointments:read")),
    db: Session = Depends(get_db),
) -> Appointment:
    appointment = db.execute(
        select(Appointment).where(
            Appointment.id == appointment_id, Appointment.workspace_id == ctx.workspace_id
        )
    ).scalar_one_or_none()
    if appointment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")
    return appointment
