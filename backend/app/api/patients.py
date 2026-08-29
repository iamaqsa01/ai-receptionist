import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import TenantContext, get_current_onboarded_tenant, require_permission
from app.database.session import get_db
from app.models.patient import Patient
from app.schemas.patient import PatientCreate, PatientOut
from app.services.audit import record_audit_log

router = APIRouter(prefix="/workspaces/{workspace_id}/patients", tags=["patients"], dependencies=[Depends(get_current_onboarded_tenant)])


@router.post("", response_model=PatientOut, status_code=status.HTTP_201_CREATED)
def create_patient(
    payload: PatientCreate,
    ctx: TenantContext = Depends(require_permission("patients:write")),
    db: Session = Depends(get_db),
) -> Patient:
    patient = Patient(workspace_id=ctx.workspace_id, **payload.model_dump())
    db.add(patient)
    db.commit()
    db.refresh(patient)
    record_audit_log(
        db, action="patient.created", resource_type="patient",
        workspace_id=ctx.workspace_id, actor_user_id=ctx.user.id, resource_id=patient.id,
    )
    return patient


@router.get("", response_model=list[PatientOut])
def list_patients(
    ctx: TenantContext = Depends(require_permission("patients:read")),
    db: Session = Depends(get_db),
) -> list[Patient]:
    return list(db.execute(select(Patient).where(Patient.workspace_id == ctx.workspace_id)).scalars())


@router.get("/{patient_id}", response_model=PatientOut)
def get_patient(
    patient_id: uuid.UUID,
    ctx: TenantContext = Depends(require_permission("patients:read")),
    db: Session = Depends(get_db),
) -> Patient:
    patient = db.execute(
        select(Patient).where(Patient.id == patient_id, Patient.workspace_id == ctx.workspace_id)
    ).scalar_one_or_none()
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
    return patient
