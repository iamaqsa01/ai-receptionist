import hashlib
import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai.scheduling.outcomes import BookingOutcome
from app.ai.scheduling.rules import as_aware_utc
from app.integrations.calendar.sync import CalendarSyncService
from app.integrations.notifications.service import NotificationService
from app.models.appointment import Appointment
from app.models.business_hours import BusinessHours
from app.models.patient import Patient
from app.models.provider import Provider
from app.models.service import Service
from app.models.workspace import Workspace

logger = logging.getLogger(__name__)


@dataclass
class AvailableSlot:
    provider: Provider
    start_time: datetime
    end_time: datetime


@dataclass
class AvailabilitySearchResult:
    workspace: Workspace
    service: Service
    timezone: str
    slots: list[AvailableSlot] = field(default_factory=list)
    code: str | None = None
    message: str | None = None


@dataclass
class AppointmentBookingRequest:
    workspace: Workspace
    service: Service
    provider: Provider | None
    start_time: datetime
    patient_name: str
    patient_phone: str
    patient_email: str | None = None
    notes: str | None = None
    source: str = "ai_receptionist"
    vapi_call_id: str | None = None
    vapi_tool_call_id: str | None = None
    enforce_business_hours: bool = False


@dataclass
class AppointmentBookingResult:
    outcome: BookingOutcome
    appointment: Appointment | None = None
    idempotent_replay: bool = False


class AppointmentSchedulingService:
    """Single source of truth for appointment availability and creation.

    The conversational AI and Vapi tool routes both delegate here, so
    conflict detection, service duration, patient upsert, calendar sync and
    notifications cannot drift into separate booking implementations.
    """

    SLOT_INTERVAL_MINUTES = 15

    def __init__(
        self,
        db: Session,
        *,
        calendar: CalendarSyncService | None = None,
        notifications: NotificationService | None = None,
    ) -> None:
        self.db = db
        self.calendar = calendar or CalendarSyncService(db)
        self.notifications = notifications or NotificationService(db)

    def resolve_service(
        self, workspace_id: uuid.UUID, *, service_id: uuid.UUID | None = None, service_name: str | None = None
    ) -> Service | None:
        stmt = select(Service).where(Service.workspace_id == workspace_id, Service.is_active.is_(True))
        if service_id is not None:
            stmt = stmt.where(Service.id == service_id)
        elif service_name:
            stmt = stmt.where(func.lower(Service.name) == service_name.strip().lower())
        else:
            return None
        return self.db.execute(stmt).scalar_one_or_none()

    def resolve_provider(
        self, workspace_id: uuid.UUID, *, provider_id: uuid.UUID | None = None, provider_name: str | None = None
    ) -> Provider | None:
        stmt = select(Provider).where(Provider.workspace_id == workspace_id, Provider.is_active.is_(True))
        if provider_id is not None:
            stmt = stmt.where(Provider.id == provider_id)
        elif provider_name and provider_name.strip().lower() not in {"no preference", "no_preference", "any"}:
            stmt = stmt.where(func.lower(Provider.name) == provider_name.strip().lower())
        else:
            return None
        return self.db.execute(stmt).scalar_one_or_none()

    def find_available_slots(
        self,
        workspace: Workspace,
        service: Service,
        *,
        preferred_date: date,
        preferred_time: time | None = None,
        provider: Provider | None = None,
        max_slots: int = 5,
    ) -> AvailabilitySearchResult:
        tz = self._workspace_timezone(workspace)
        result = AvailabilitySearchResult(workspace=workspace, service=service, timezone=workspace.timezone)
        hours = self._business_hours(workspace.id, preferred_date.weekday())
        if hours is None:
            result.code = "BUSINESS_HOURS_NOT_CONFIGURED"
            result.message = "The clinic has not configured business hours for that day."
            return result
        if hours.is_closed or hours.open_time is None or hours.close_time is None:
            result.code = "CLINIC_CLOSED"
            result.message = "The clinic is closed on that day."
            return result

        providers = [provider] if provider is not None else list(
            self.db.execute(
                select(Provider)
                .where(Provider.workspace_id == workspace.id, Provider.is_active.is_(True))
                .order_by(Provider.name)
            ).scalars()
        )
        if not providers:
            result.code = "NO_PROVIDERS_CONFIGURED"
            result.message = "No active provider is configured for this clinic."
            return result

        opening = datetime.combine(preferred_date, hours.open_time, tzinfo=tz)
        closing = datetime.combine(preferred_date, hours.close_time, tzinfo=tz)
        candidate = datetime.combine(preferred_date, preferred_time or hours.open_time, tzinfo=tz)
        candidate = max(candidate, opening)
        now_local = datetime.now(tz)
        duration = timedelta(minutes=service.duration_minutes)
        step = timedelta(minutes=self.SLOT_INTERVAL_MINUTES)

        while candidate + duration <= closing and len(result.slots) < max_slots:
            if candidate >= now_local:
                for candidate_provider in providers:
                    start_utc = as_aware_utc(candidate)
                    end_utc = start_utc + duration
                    if self.is_slot_available(
                        workspace,
                        service,
                        candidate_provider,
                        start_utc,
                        enforce_business_hours=False,
                    ):
                        result.slots.append(
                            AvailableSlot(provider=candidate_provider, start_time=start_utc, end_time=end_utc)
                        )
                        if len(result.slots) >= max_slots:
                            break
            candidate += step

        if not result.slots:
            result.code = "NO_SLOTS_AVAILABLE"
            result.message = "No matching appointment slots are available on that day."
        return result

    def is_slot_available(
        self,
        workspace: Workspace,
        service: Service,
        provider: Provider | None,
        start_time: datetime,
        *,
        enforce_business_hours: bool,
    ) -> bool:
        start_utc = as_aware_utc(start_time)
        end_utc = start_utc + timedelta(minutes=service.duration_minutes)
        if start_utc <= datetime.now(timezone.utc):
            return False
        if enforce_business_hours and not self._inside_business_hours(workspace, start_utc, end_utc):
            return False

        if provider is not None:
            stmt = select(Appointment.id).where(
                Appointment.workspace_id == workspace.id,
                Appointment.provider_id == provider.id,
                Appointment.status == "scheduled",
                Appointment.start_time < end_utc,
                Appointment.end_time > start_utc,
            )
            if self.db.execute(stmt.limit(1)).scalar_one_or_none() is not None:
                return False

        proposed = Appointment(start_time=start_utc, end_time=end_utc)
        return self.calendar.check_availability(workspace.id, proposed) is not False

    def book_appointment(self, request: AppointmentBookingRequest) -> AppointmentBookingResult:
        existing = self._find_idempotent_appointment(request)
        if existing is not None:
            return AppointmentBookingResult(BookingOutcome.CREATED, existing, idempotent_replay=True)

        start_utc = as_aware_utc(request.start_time)
        end_utc = start_utc + timedelta(minutes=request.service.duration_minutes)
        self._acquire_slot_lock(request.workspace.id, request.provider)

        existing = self._find_idempotent_appointment(request)
        if existing is not None:
            return AppointmentBookingResult(BookingOutcome.CREATED, existing, idempotent_replay=True)

        patient = self.db.execute(
            select(Patient).where(
                Patient.workspace_id == request.workspace.id,
                Patient.phone == request.patient_phone,
            )
        ).scalar_one_or_none()
        if patient is not None:
            duplicate = self.db.execute(
                select(Appointment.id).where(
                    Appointment.workspace_id == request.workspace.id,
                    Appointment.patient_id == patient.id,
                    Appointment.status == "scheduled",
                    Appointment.start_time < end_utc,
                    Appointment.end_time > start_utc,
                ).limit(1)
            ).scalar_one_or_none()
            if duplicate is not None:
                return AppointmentBookingResult(BookingOutcome.DUPLICATE)

        if not self.is_slot_available(
            request.workspace,
            request.service,
            request.provider,
            start_utc,
            enforce_business_hours=request.enforce_business_hours,
        ):
            return AppointmentBookingResult(BookingOutcome.CONFLICT)

        # Calendar error reporting can commit its notification. Reacquire the
        # transaction-scoped lock and recheck the database before inserting.
        self._acquire_slot_lock(request.workspace.id, request.provider)
        if self._has_provider_conflict(request.workspace.id, request.provider, start_utc, end_utc):
            return AppointmentBookingResult(BookingOutcome.CONFLICT)

        patient = self._upsert_patient(request, patient)
        note = request.notes or f"Booked via {request.source} ({request.service.name})"
        appointment = Appointment(
            workspace_id=request.workspace.id,
            patient_id=patient.id,
            provider_id=request.provider.id if request.provider else None,
            service_id=request.service.id,
            start_time=start_utc,
            end_time=end_utc,
            status="scheduled",
            notes=note,
            vapi_call_id=request.vapi_call_id,
            vapi_tool_call_id=request.vapi_tool_call_id,
        )
        self.db.add(appointment)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            existing = self._find_idempotent_appointment(request)
            if existing is not None:
                return AppointmentBookingResult(BookingOutcome.CREATED, existing, idempotent_replay=True)
            raise
        self.db.refresh(appointment)

        self.calendar.create_event(
            request.workspace.id,
            appointment,
            summary=f"{request.service.name} - {request.patient_name}",
            description=note,
        )
        # Immediate booking confirmation — the DB write above has already
        # committed, so this only ever fires for a booking that actually
        # succeeded. Notification-provider failures are swallowed inside
        # NotificationService (tracked as a "failed" NotificationMessage
        # row, retryable) and must never propagate out to break a live
        # call. `request.provider` is passed so the assigned doctor is
        # notified too when the booking business logic resolved one.
        try:
            self.notifications.notify_appointment_event(
                "appointment_confirmation",
                appointment,
                patient,
                service_summary=request.service.name,
                provider=request.provider,
            )
        except Exception:  # pragma: no cover - defensive; provider errors are already handled internally
            logger.exception(
                "appointment=%s booked but confirmation notification dispatch failed", appointment.id
            )
        return AppointmentBookingResult(BookingOutcome.CREATED, appointment)

    def _business_hours(self, workspace_id: uuid.UUID, day_of_week: int) -> BusinessHours | None:
        return self.db.execute(
            select(BusinessHours).where(
                BusinessHours.workspace_id == workspace_id,
                BusinessHours.day_of_week == day_of_week,
            )
        ).scalar_one_or_none()

    def _inside_business_hours(self, workspace: Workspace, start_utc: datetime, end_utc: datetime) -> bool:
        tz = self._workspace_timezone(workspace)
        start_local = start_utc.astimezone(tz)
        end_local = end_utc.astimezone(tz)
        if start_local.date() != end_local.date():
            return False
        hours = self._business_hours(workspace.id, start_local.weekday())
        if hours is None or hours.is_closed or hours.open_time is None or hours.close_time is None:
            return False
        return start_local.time() >= hours.open_time and end_local.time() <= hours.close_time

    @staticmethod
    def _workspace_timezone(workspace: Workspace) -> ZoneInfo:
        try:
            return ZoneInfo(workspace.timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Workspace has invalid timezone {workspace.timezone!r}") from exc

    def _has_provider_conflict(
        self, workspace_id: uuid.UUID, provider: Provider | None, start_time: datetime, end_time: datetime
    ) -> bool:
        if provider is None:
            return False
        stmt = select(Appointment.id).where(
            Appointment.workspace_id == workspace_id,
            Appointment.provider_id == provider.id,
            Appointment.status == "scheduled",
            Appointment.start_time < end_time,
            Appointment.end_time > start_time,
        )
        return self.db.execute(stmt.limit(1)).scalar_one_or_none() is not None

    def _upsert_patient(
        self, request: AppointmentBookingRequest, patient: Patient | None
    ) -> Patient:
        parts = request.patient_name.strip().split(" ", 1)
        first_name = parts[0]
        last_name = parts[1] if len(parts) > 1 else ""
        if patient is None:
            patient = Patient(
                workspace_id=request.workspace.id,
                first_name=first_name,
                last_name=last_name,
                phone=request.patient_phone,
                email=request.patient_email,
            )
            self.db.add(patient)
            self.db.flush()
            return patient
        patient.first_name = first_name
        patient.last_name = last_name
        if request.patient_email:
            patient.email = request.patient_email
        self.db.add(patient)
        self.db.flush()
        return patient

    def _find_idempotent_appointment(self, request: AppointmentBookingRequest) -> Appointment | None:
        if not request.vapi_call_id or not request.vapi_tool_call_id:
            return None
        return self.db.execute(
            select(Appointment).where(
                Appointment.workspace_id == request.workspace.id,
                Appointment.vapi_call_id == request.vapi_call_id,
                Appointment.vapi_tool_call_id == request.vapi_tool_call_id,
            )
        ).scalar_one_or_none()

    def _acquire_slot_lock(self, workspace_id: uuid.UUID, provider: Provider | None) -> None:
        bind = self.db.get_bind()
        if bind.dialect.name != "postgresql":
            return
        # Provider-wide rather than exact-start locking is intentional: a
        # 10:00 request and a 10:15 request can overlap when a service lasts
        # longer than 15 minutes. Serializing the provider's short booking
        # transaction makes the second request observe the first insert.
        raw = f"{workspace_id}:{provider.id if provider else 'any'}".encode()
        lock_key = int.from_bytes(hashlib.blake2b(raw, digest_size=8).digest(), "big", signed=True)
        self.db.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": lock_key})
