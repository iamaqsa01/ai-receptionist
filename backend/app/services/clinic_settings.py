import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.business_hours import BusinessHours
from app.models.provider import Provider
from app.models.service import Service
from app.schemas.clinic_settings import ClinicSettingsUpdate


def sync_booking_configuration(
    db: Session, workspace_id: uuid.UUID, settings: ClinicSettingsUpdate
) -> None:
    """Synchronize onboarding settings into the real scheduling tables.

    Clinic settings remain the editable knowledge-base representation used
    by the dashboard and prompt builder. Providers, services and business
    hours are the operational representation used by availability and
    booking. This function keeps both representations aligned in the same
    transaction as the settings save and onboarding-state change.

    Existing rows are matched case-insensitively by name so retries and
    subsequent edits are idempotent. Removed providers/services are made
    inactive rather than deleted because historical appointments may still
    reference them.
    """

    _sync_providers(db, workspace_id, settings)
    _sync_services(db, workspace_id, settings)
    if settings.business_hours:
        _sync_business_hours(db, workspace_id, settings)


def _sync_providers(db: Session, workspace_id: uuid.UUID, settings: ClinicSettingsUpdate) -> None:
    existing = list(
        db.execute(select(Provider).where(Provider.workspace_id == workspace_id)).scalars()
    )
    by_name: dict[str, Provider] = {}
    for provider in existing:
        key = provider.name.strip().casefold()
        if key in by_name:
            provider.is_active = False
        else:
            by_name[key] = provider

    active_names: set[str] = set()
    for doctor in settings.doctors:
        key = doctor.name.strip().casefold()
        active_names.add(key)
        provider = by_name.get(key)
        if provider is None:
            provider = Provider(workspace_id=workspace_id, name=doctor.name.strip())
            db.add(provider)
            by_name[key] = provider
        provider.name = doctor.name.strip()
        provider.title = doctor.specialty.strip() if doctor.specialty else None
        provider.is_active = True

    for provider in existing:
        if provider.name.strip().casefold() not in active_names:
            provider.is_active = False


def _sync_services(db: Session, workspace_id: uuid.UUID, settings: ClinicSettingsUpdate) -> None:
    existing = list(
        db.execute(select(Service).where(Service.workspace_id == workspace_id)).scalars()
    )
    by_name: dict[str, Service] = {}
    for service in existing:
        key = service.name.strip().casefold()
        if key in by_name:
            service.is_active = False
        else:
            by_name[key] = service

    active_names: set[str] = set()
    duration = settings.appointment_settings.default_slot_duration_minutes
    for configured_name in settings.services:
        name = configured_name.strip()
        key = name.casefold()
        active_names.add(key)
        service = by_name.get(key)
        if service is None:
            service = Service(workspace_id=workspace_id, name=name)
            db.add(service)
            by_name[key] = service
        service.name = name
        service.duration_minutes = duration
        service.is_active = True

    for service in existing:
        if service.name.strip().casefold() not in active_names:
            service.is_active = False


def _sync_business_hours(
    db: Session, workspace_id: uuid.UUID, settings: ClinicSettingsUpdate
) -> None:
    existing = {
        row.day_of_week: row
        for row in db.execute(
            select(BusinessHours).where(BusinessHours.workspace_id == workspace_id)
        ).scalars()
    }
    configured = {row.day_of_week: row for row in settings.business_hours}

    # Store a complete seven-day week. A missing day is explicitly closed,
    # which makes availability deterministic and avoids interpreting absence
    # as either "closed" or "not configured" depending on the caller.
    for day_of_week in range(7):
        row = existing.get(day_of_week)
        if row is None:
            row = BusinessHours(workspace_id=workspace_id, day_of_week=day_of_week)
            db.add(row)

        incoming = configured.get(day_of_week)
        if incoming is None or incoming.is_closed:
            row.open_time = None
            row.close_time = None
            row.is_closed = True
        else:
            row.open_time = incoming.open_time
            row.close_time = incoming.close_time
            row.is_closed = False
