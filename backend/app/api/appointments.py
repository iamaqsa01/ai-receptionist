import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.scheduling.outcomes import BookingOutcome
from app.api.deps import TenantContext, get_current_onboarded_tenant, require_permission
from app.database.session import get_db
from app.models.appointment import Appointment
from app.models.patient import Patient
from app.models.provider import Provider
from app.models.service import Service
from app.models.workspace import Workspace
from app.schemas.appointment import AppointmentCreate, AppointmentOut
from app.services.audit import record_audit_log
from app.services.scheduling import AppointmentBookingRequest, AppointmentSchedulingService

router = APIRouter(
    prefix="/workspaces/{workspace_id}/appointments",
    tags=["appointments"],
    dependencies=[Depends(get_current_onboarded_tenant)],
)


@router.post("", response_model=AppointmentOut, status_code=status.HTTP_201_CREATED)
def create_appointment(
    payload: AppointmentCreate,
    ctx: TenantContext = Depends(require_permission("appointments:write")),
    db: Session = Depends(get_db),
) -> Appointment:
    """Create a staff booking through the canonical scheduling service."""
    patient = db.execute(
        select(Patient).where(
            Patient.id == payload.patient_id,
            Patient.workspace_id == ctx.workspace_id,
        )
    ).scalar_one_or_none()
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

    provider = None
    if payload.provider_id is not None:
        provider = db.execute(
            select(Provider).where(
                Provider.id == payload.provider_id,
                Provider.workspace_id == ctx.workspace_id,
            )
        ).scalar_one_or_none()
        if provider is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")

    service = None
    if payload.service_id is not None:
        service = db.execute(
            select(Service).where(
                Service.id == payload.service_id,
                Service.workspace_id == ctx.workspace_id,
            )
        ).scalar_one_or_none()
        if service is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")

    workspace = db.get(Workspace, ctx.workspace_id)
    if workspace is None:  # The tenant dependency normally makes this unreachable.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

    scheduling = AppointmentSchedulingService(db)
    try:
        booking = scheduling.book_appointment(
            AppointmentBookingRequest(
                workspace=workspace,
                patient=patient,
                provider=provider,
                service=service,
                start_time=payload.start_time,
                end_time=payload.end_time,
                notes=payload.notes,
                source="dashboard",
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    if booking.outcome == BookingOutcome.DUPLICATE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The patient already has an overlapping appointment",
        )
    if booking.outcome != BookingOutcome.CREATED or booking.appointment is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The appointment slot is unavailable")

    appointment = booking.appointment
    record_audit_log(
        db,
        action="appointment.created",
        resource_type="appointment",
        workspace_id=ctx.workspace_id,
        actor_user_id=ctx.user.id,
        resource_id=appointment.id,
    )
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
            Appointment.id == appointment_id,
            Appointment.workspace_id == ctx.workspace_id,
        )
    ).scalar_one_or_none()
    if appointment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")
    return appointment
