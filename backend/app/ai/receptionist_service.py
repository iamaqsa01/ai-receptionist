import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.conversation.effects import (
    BookAppointmentEffect,
    CancelAppointmentEffect,
    Effect,
    RescheduleAppointmentEffect,
    TransferToHumanEffect,
    UpsertLeadEffect,
)
from app.ai.conversation.engine import ConversationEngine, EngineResult
from app.ai.conversation.instructions import WorkspaceAIProfile, load_workspace_profile
from app.ai.conversation.state import ConversationState, ConversationStatus
from app.ai.conversation.store import ConversationStore, default_conversation_store
from app.ai.llm.base import LLMProvider
from app.ai.llm.factory import get_llm_provider
from app.ai.nlu.engine import NLUEngine
from app.ai.qualification.validators import next_lead_status
from app.ai.scheduling.outcomes import BookingOutcome
from app.integrations.calendar.base import CalendarProvider
from app.integrations.calendar.sync import CalendarSyncService
from app.integrations.notifications.base import EmailProvider, WhatsAppProvider
from app.integrations.notifications.service import NotificationService
from app.models.appointment import Appointment
from app.models.human_handoff import HumanHandoff
from app.models.lead import Lead
from app.models.notification import Notification
from app.models.patient import Patient
from app.models.service import Service
from app.models.workspace import Workspace
from app.services.integration_log import record_integration_log
from app.services.scheduling import AppointmentBookingRequest, AppointmentSchedulingService
from app.telephony.providers.base import TelephonyAdapter

logger = logging.getLogger(__name__)

class UnknownConversationSessionError(Exception):
    pass


class ReceptionistService:
    """The AI Receptionist as seen from the outside: a thin façade over
    ConversationEngine that resolves workspace-specific instructions and
    applies the engine's structured effects to the real database — creating
    or matching a Patient, writing an Appointment, or raising a Notification
    for a human handoff. This is where "business logic" (persistence,
    tenant scoping, availability/conflict/duplicate checking) lives; the
    engine and LLM layers underneath know nothing about SQLAlchemy or the
    database.

    Crucially: for booking/cancellation/reschedule effects, the engine's
    reply text is only ever a provisional placeholder ("One moment
    please.") — it cannot know whether the database write will succeed
    before it happens. This class always overwrites that placeholder with
    an outcome-aware reply (via ConversationEngine.render_*_outcome)
    computed *after* the write actually happened, which is what guarantees
    the caller is never told "confirmed" before the backend confirms it."""

    def __init__(
        self,
        db: Session,
        llm: LLMProvider | None = None,
        store: ConversationStore | None = None,
        calendar_provider: CalendarProvider | None = None,
        whatsapp_provider: WhatsAppProvider | None = None,
        email_provider: EmailProvider | None = None,
    ) -> None:
        self.db = db
        self.llm = llm or get_llm_provider()
        self.store = store or default_conversation_store
        self.engine = ConversationEngine(nlu=NLUEngine(self.llm), llm=self.llm)
        self.calendar = CalendarSyncService(db=db, provider=calendar_provider)
        # Phase 15 fix: this was built in Phase 9 but never actually wired
        # into the booking flow below — appointments were created without
        # ever sending the WhatsApp/email confirmation the notification
        # system exists for. See _book_appointment / _cancel_appointment /
        # _reschedule_appointment.
        self.notifications = NotificationService(db=db, whatsapp=whatsapp_provider, email=email_provider)
        self.scheduling = AppointmentSchedulingService(
            db=db, calendar=self.calendar, notifications=self.notifications
        )

    def start_session(self, workspace_id: uuid.UUID) -> ConversationState:
        return self.store.create(workspace_id)

    def handle_message(
        self,
        workspace_id: uuid.UUID,
        session_id: uuid.UUID,
        message: str,
        *,
        telephony_adapter: TelephonyAdapter | None = None,
        provider_call_id: str | None = None,
    ) -> EngineResult:
        """`telephony_adapter`/`provider_call_id` are only ever passed by
        CallSession (a live phone call) — they're what a human handoff uses
        to actually attempt a live transfer (Phase 10). Both are None for a
        text-only caller (e.g. the staff dashboard's "try it" demo), in
        which case a handoff is still recorded, just with no live transfer
        attempted."""
        state = self.store.get(session_id)
        if state is None or state.workspace_id != workspace_id:
            # Tenant isolation applies to conversation sessions too: a
            # session created under one workspace can't be driven from
            # another workspace's URL, mirroring the Phase 3 pattern.
            raise UnknownConversationSessionError(session_id)

        profile = load_workspace_profile(self.db, workspace_id)
        try:
            result = self.engine.handle_message(state, message, profile)
        except Exception:
            # "Technical failure requires human assistance" (Phase 10): a
            # bug or an unexpected error in the AI Receptionist's own logic
            # must never leave the caller hanging — hand off to a human
            # instead of propagating the exception up through the call.
            logger.exception(
                "workspace_id=%s session_id=%s AI Receptionist failed to process caller message",
                workspace_id,
                session_id,
            )
            result = self._handle_technical_failure(
                workspace_id, session_id, state, profile, telephony_adapter, provider_call_id
            )
            self.store.save(result.state)
            return result

        override_reply = self._apply_effects(
            workspace_id, session_id, result.effects, result.state, profile, telephony_adapter, provider_call_id
        )
        if override_reply is not None:
            result.reply = override_reply
        self.store.save(result.state)
        return result

    def _handle_technical_failure(
        self,
        workspace_id: uuid.UUID,
        session_id: uuid.UUID,
        state: ConversationState,
        profile: WorkspaceAIProfile,
        telephony_adapter: TelephonyAdapter | None,
        provider_call_id: str | None,
    ) -> EngineResult:
        state.status = ConversationStatus.NEEDS_HUMAN
        effect = TransferToHumanEffect(
            reason="An internal error occurred while the AI Receptionist was processing the caller's message",
            trigger="technical_failure",
        )
        self._raise_human_handoff(workspace_id, session_id, effect, state, profile, telephony_adapter, provider_call_id)
        reply = self.engine.render_transfer_reply(state.language)
        state.add_turn("assistant", reply, language=state.language)
        return EngineResult(state=state, reply=reply, effects=[effect])

    def _apply_effects(
        self,
        workspace_id: uuid.UUID,
        session_id: uuid.UUID,
        effects: list[Effect],
        state: ConversationState,
        profile: WorkspaceAIProfile,
        telephony_adapter: TelephonyAdapter | None,
        provider_call_id: str | None,
    ) -> str | None:
        """Applies every effect from this turn. For booking/cancellation/
        reschedule effects — the ones with a real success/failure outcome —
        returns the reply that must replace the engine's provisional one.
        Returns None when nothing needs overriding (a lead upsert or a
        transfer notification carry no caller-facing outcome of their own)."""
        override_reply = None
        for effect in effects:
            if isinstance(effect, BookAppointmentEffect):
                outcome = self._book_appointment(workspace_id, effect)
                override_reply = self.engine.render_booking_outcome(state, outcome)
            elif isinstance(effect, CancelAppointmentEffect):
                outcome = self._cancel_appointment(workspace_id, effect)
                override_reply = self.engine.render_cancellation_outcome(state, outcome)
            elif isinstance(effect, RescheduleAppointmentEffect):
                outcome = self._reschedule_appointment(workspace_id, effect)
                override_reply = self.engine.render_reschedule_outcome(state, outcome)
            elif isinstance(effect, TransferToHumanEffect):
                self._raise_human_handoff(
                    workspace_id, session_id, effect, state, profile, telephony_adapter, provider_call_id
                )
            elif isinstance(effect, UpsertLeadEffect):
                self._upsert_lead(workspace_id, effect)
        return override_reply

    def _upsert_lead(self, workspace_id: uuid.UUID, effect: UpsertLeadEffect) -> None:
        lead = self.db.execute(
            select(Lead).where(Lead.workspace_id == workspace_id, Lead.phone == effect.phone)
        ).scalar_one_or_none()

        if lead is None:
            lead = Lead(
                workspace_id=workspace_id,
                phone=effect.phone,
                name=effect.name,
                source=effect.source,
                status=effect.status,
                notes=effect.notes,
            )
            self.db.add(lead)
            self.db.commit()
            return

        # Status only ever escalates (new -> qualifying -> converted) — a
        # later turn that happens to look less advanced (e.g. the caller
        # says "hi" again) can never downgrade a lead that already
        # progressed further. Contact details/notes are always refreshed
        # to whatever the caller most recently said, though.
        lead.status = next_lead_status(lead.status, effect.status)
        if effect.name:
            lead.name = effect.name
        if effect.notes:
            lead.notes = effect.notes
        self.db.add(lead)
        self.db.commit()

    def _find_latest_upcoming_appointment(self, workspace_id: uuid.UUID, phone: str) -> Appointment | None:
        patient = self.db.execute(
            select(Patient).where(Patient.workspace_id == workspace_id, Patient.phone == phone)
        ).scalar_one_or_none()
        if patient is None:
            return None

        return self.db.execute(
            select(Appointment)
            .where(
                Appointment.workspace_id == workspace_id,
                Appointment.patient_id == patient.id,
                Appointment.status == "scheduled",
            )
            .order_by(Appointment.start_time)
        ).scalars().first()

    def _book_appointment(self, workspace_id: uuid.UUID, effect: BookAppointmentEffect) -> BookingOutcome:
        """Availability checking, conflict detection, and duplicate-booking
        prevention — the actual database write happens only if all three
        pass. Never called until the caller has already said "yes" to the
        confirmation prompt (see ConversationEngine._handle_pending_confirmation)."""
        workspace = self.db.get(Workspace, workspace_id)
        service = self.scheduling.resolve_service(workspace_id, service_name=effect.service)
        if workspace is None or service is None:
            return BookingOutcome.CONFLICT
        provider = self.scheduling.resolve_provider(workspace_id, provider_name=effect.provider)
        note = f"Booked via AI Receptionist ({effect.service})"
        if effect.department:
            note += f" - {effect.department}"
        if provider is not None:
            note += f" with {provider.name}"
        booking = self.scheduling.book_appointment(
            AppointmentBookingRequest(
                workspace=workspace,
                service=service,
                provider=provider,
                start_time=effect.when,
                patient_name=effect.caller_name,
                patient_phone=effect.phone,
                notes=note,
                source="AI Receptionist",
            )
        )
        if booking.outcome != BookingOutcome.CREATED:
            return booking.outcome

        # This booking is what turns a prospect into a confirmed patient —
        # escalate their lead (if any) to "converted" now that it's real.
        self._upsert_lead(
            workspace_id,
            UpsertLeadEffect(phone=effect.phone, name=effect.caller_name, status="converted"),
        )
        return BookingOutcome.CREATED

    def _cancel_appointment(self, workspace_id: uuid.UUID, effect: CancelAppointmentEffect) -> BookingOutcome:
        appointment = self._find_latest_upcoming_appointment(workspace_id, effect.phone)
        if appointment is None:
            return BookingOutcome.NOT_FOUND
        appointment.status = "cancelled"
        self.db.add(appointment)
        self.db.commit()
        self.calendar.cancel_event(workspace_id, appointment)
        patient = self.db.get(Patient, appointment.patient_id)
        if patient is not None:
            self.notifications.notify_appointment_event(
                "appointment_cancellation", appointment, patient, service_summary=self._service_summary_for(appointment)
            )
        return BookingOutcome.CANCELLED

    def _reschedule_appointment(
        self, workspace_id: uuid.UUID, effect: RescheduleAppointmentEffect
    ) -> BookingOutcome:
        appointment = self._find_latest_upcoming_appointment(workspace_id, effect.phone)
        if appointment is None:
            return BookingOutcome.NOT_FOUND

        return self.scheduling.reschedule_appointment(appointment, effect.new_when).outcome

    def _service_summary_for(self, appointment: Appointment) -> str:
        if appointment.service_id is None:
            return "your appointment"
        service = self.db.get(Service, appointment.service_id)
        return service.name if service is not None else "your appointment"

    def _raise_human_handoff(
        self,
        workspace_id: uuid.UUID,
        session_id: uuid.UUID,
        effect: TransferToHumanEffect,
        state: ConversationState,
        profile: WorkspaceAIProfile,
        telephony_adapter: TelephonyAdapter | None,
        provider_call_id: str | None,
    ) -> None:
        """Phase 10 human-Receptionist escalation. Before anything else,
        the conversation context, transfer reason, and call state are
        durably recorded in PostgreSQL (HumanHandoff) — that write always
        happens, whether or not a live telephony transfer is even possible.
        A staff-facing Notification is raised the same way calendar sync
        failures are (see CalendarSyncService), and — only if this call is
        on a live telephony channel that supports it and the workspace has
        a transfer number configured — an actual live transfer is then
        attempted and its outcome recorded back onto the same row."""
        handoff = HumanHandoff(
            workspace_id=workspace_id,
            conversation_session_id=session_id,
            trigger=effect.trigger,
            reason=effect.reason,
            conversation_context=_serialize_conversation_context(state),
            call_state=_serialize_call_state(state),
            status="pending",
        )
        self.db.add(handoff)
        self.db.commit()
        self.db.refresh(handoff)

        notification = Notification(
            workspace_id=workspace_id,
            type="ai_handoff",
            title="AI Receptionist requested a human transfer",
            message=effect.reason,
        )
        self.db.add(notification)
        self.db.commit()

        self._attempt_live_transfer(handoff, profile, telephony_adapter, provider_call_id)

    def _attempt_live_transfer(
        self,
        handoff: HumanHandoff,
        profile: WorkspaceAIProfile,
        telephony_adapter: TelephonyAdapter | None,
        provider_call_id: str | None,
    ) -> None:
        if telephony_adapter is None or not telephony_adapter.supports_live_transfer():
            return  # not a live call, or this provider has no transfer capability
        target = profile.human_transfer_number if profile else None
        if not target or not provider_call_id:
            return  # workspace hasn't configured a number to transfer to

        result = telephony_adapter.transfer_call(provider_call_id, target)
        handoff.transfer_target = target
        handoff.transfer_detail = result.detail
        handoff.status = "transferred" if result.success else "failed"
        handoff.transferred_at = datetime.now(timezone.utc) if result.success else None
        self.db.add(handoff)
        self.db.commit()
        record_integration_log(
            self.db, workspace_id=handoff.workspace_id, category="telephony_transfer",
            provider=telephony_adapter.name, action="transfer_call",
            status="success" if result.success else "failure", detail=result.detail,
        )


def _serialize_conversation_context(state: ConversationState) -> list[dict]:
    return [
        {"role": turn.role, "text": turn.text, "language": turn.language, "timestamp": turn.timestamp.isoformat()}
        for turn in state.history
    ]


def _serialize_call_state(state: ConversationState) -> dict:
    return {
        "session_id": str(state.session_id),
        "status": state.status.value,
        "intent": state.intent.value if state.intent else None,
        "language": state.language,
        "caller_name": state.caller.name,
        "caller_phone": state.caller.phone,
        "missing_fields": list(state.missing_fields),
        "appointment": {
            "service": state.appointment.service,
            "department": state.appointment.department,
            "provider": state.appointment.provider,
            "when": state.appointment.when.isoformat() if state.appointment.when else None,
            "new_when": state.appointment.new_when.isoformat() if state.appointment.new_when else None,
        },
    }
