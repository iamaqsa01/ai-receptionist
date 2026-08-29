from dataclasses import dataclass, field

from app.ai.conversation.effects import (
    BookAppointmentEffect,
    CancelAppointmentEffect,
    Effect,
    RescheduleAppointmentEffect,
    TransferToHumanEffect,
    UpsertLeadEffect,
)
from app.ai.conversation.instructions import WorkspaceAIProfile, render_system_prompt
from app.ai.conversation.state import AppointmentDraft, ConversationState, ConversationStatus
from app.ai.language.catalog import get_language
from app.ai.language.detector import detect_language, match_language_mention, normalize_language_code
from app.ai.llm.base import LLMMessage, LLMProvider
from app.ai.nlu.confirmation import classify_confirmation
from app.ai.nlu.engine import NLUEngine
from app.ai.nlu.safety import contains_clinical_content
from app.ai.nlu.schema import Intent, NLUResult
from app.ai.qualification.validators import (
    resolve_department,
    validate_future_datetime,
    validate_name,
    validate_phone,
    validate_service,
)
from app.ai.scheduling.outcomes import BookingOutcome
from app.core.config import settings

# Intents for which the caller is an existing patient being identified by
# phone (cancel/reschedule/transfer) rather than a prospect — these never
# produce a Lead record.
_NON_LEAD_INTENTS = (
    Intent.APPOINTMENT_CANCELLATION,
    Intent.APPOINTMENT_RESCHEDULE,
    Intent.HUMAN_TRANSFER,
    Intent.UNSUPPORTED_REQUEST,
)

_LOW_CONFIDENCE_TRANSFER_THRESHOLD = 2

# "AI repeatedly fails to understand" (Phase 10): consecutive turns the NLU
# engine could only classify as a low-confidence GENERAL_INQUIRY (its
# catch-all fallback — see NLUEngine._classify_intent) before giving up and
# handing off to a human, rather than looping the caller through more
# guesses forever. 0.35 sits just above _RULE_BASED_CONFIDENCE_DEFAULT
# (0.3) in app.ai.nlu.engine, i.e. this only fires on that exact fallback,
# never on a confidently-classified GENERAL_INQUIRY question.
_UNCLEAR_INTENT_CONFIDENCE_THRESHOLD = 0.35
_UNCLEAR_INTENT_TRANSFER_THRESHOLD = 3

# Switching *away from* an already-established language mid-call requires
# much stronger evidence than accepting a language on the very first turn.
# Short slot-filling replies ("Jane Doe", "Cleaning", digits, ...) are
# routinely misdetected as some other language by a statistical detector at
# moderate — even high — confidence; without these guards, the conversation
# would keep derailing into "please choose a supported language" on
# ordinary answers.
_LANGUAGE_SWITCH_CONFIDENCE = 0.95
# Statistical language ID needs enough text to be meaningful. A caller
# actually switching languages mid-call says something substantive ("Can we
# continue in Spanish?"), not a two-word slot answer — so short messages
# never trigger a language re-check once a language is already established.
_MIN_WORDS_FOR_LANGUAGE_SWITCH = 5


@dataclass
class EngineResult:
    state: ConversationState
    reply: str
    effects: list[Effect] = field(default_factory=list)


class ConversationEngine:
    """The core AI Receptionist dialogue orchestrator: pure business logic
    with no I/O of its own. It takes conversation state + one caller message
    and a workspace's AI profile, and returns updated state, the reply to
    speak/send back, and a list of structured `Effect`s for the caller
    (receptionist_service.py) to actually apply to the database. Keeping
    persistence out of here makes conversations fully testable in memory —
    "simulated conversations" don't need a database at all."""

    def __init__(self, nlu: NLUEngine, llm: LLMProvider) -> None:
        self._nlu = nlu
        self._llm = llm

    def handle_message(
        self, state: ConversationState, message: str, profile: WorkspaceAIProfile
    ) -> EngineResult:
        state.add_turn("caller", message, language=state.language)

        language_result = self._resolve_language(state, message, profile)
        if language_result is not None:
            state.add_turn("assistant", language_result, language=state.language)
            effects = []
            if state.status == ConversationStatus.NEEDS_HUMAN:
                # _resolve_language sets this once low_confidence_strikes
                # crosses its threshold — same "repeated misunderstanding"
                # transfer as the general-intent path below, just triggered
                # by repeated language-detection uncertainty instead.
                effects = [
                    TransferToHumanEffect(
                        reason="AI repeatedly failed to understand the caller's spoken language",
                        trigger="repeated_misunderstanding",
                    )
                ]
            return EngineResult(state=state, reply=language_result, effects=effects)

        escalation = self._maybe_escalate_on_clinic_rule(state, message, profile)
        if escalation is not None:
            return escalation

        if state.pending_booking_confirmation:
            return self._handle_pending_confirmation(state, message)

        nlu_result = self._nlu.analyze(
            message,
            state.language or "en",
            profile.services,
            known_providers=profile.providers,
            timezone_name=profile.timezone,
        )

        is_clinical = nlu_result.intent == Intent.CLINICAL_REQUEST or contains_clinical_content(
            message, state.language
        )
        if is_clinical:
            reply = self._t(state.language, "clinical_refusal")
            state.add_turn("assistant", reply, language=state.language)
            return EngineResult(state=state, reply=reply, effects=[])

        # Only counts before any real request has been identified for this
        # call (state.intent is None) — once state.intent is set, every
        # subsequent turn is a slot-filling answer ("Jane Doe", "Cleaning",
        # a phone number...) that legitimately has no intent keywords of
        # its own and would otherwise misfire this as "confusion" on a
        # perfectly normal booking flow. _route() only ever reaches
        # _handle_open_ended (the GENERAL_INQUIRY path this guards) while
        # state.intent is still None, so this mirrors that exactly. The very
        # first turn of the call is also excluded: a bare opener ("Hi")
        # routinely misses the GREETING keyword list (which expects a
        # trailing space/comma, e.g. "hi ") and falls through to
        # GENERAL_INQUIRY too, but _handle_open_ended already special-cases
        # it into the normal greeting reply — it was never "the AI failing
        # to understand" in the first place.
        if state.intent is None and len(state.history) > 1:
            if nlu_result.intent == Intent.GENERAL_INQUIRY and nlu_result.confidence <= _UNCLEAR_INTENT_CONFIDENCE_THRESHOLD:
                state.unclear_intent_strikes += 1
            else:
                state.unclear_intent_strikes = 0

        if state.intent is None and state.unclear_intent_strikes >= _UNCLEAR_INTENT_TRANSFER_THRESHOLD:
            state.status = ConversationStatus.NEEDS_HUMAN
            reply = self._t(state.language, "low_confidence_offer_transfer")
            state.add_turn("assistant", reply, language=state.language)
            return EngineResult(
                state=state,
                reply=reply,
                effects=[
                    TransferToHumanEffect(
                        reason="AI repeatedly failed to understand the caller's request",
                        trigger="repeated_misunderstanding",
                    )
                ],
            )

        if nlu_result.intent in (
            Intent.APPOINTMENT_BOOKING,
            Intent.APPOINTMENT_CANCELLATION,
            Intent.APPOINTMENT_RESCHEDULE,
            Intent.HUMAN_TRANSFER,
            Intent.UNSUPPORTED_REQUEST,
        ):
            state.intent = nlu_result.intent

        validation_issues = self._merge_entities(state, nlu_result, profile)

        # A validation failure gets its own explanatory reply rather than
        # silently falling through to a generic "what's the date/time?" —
        # the caller gets told *why* what they said wasn't accepted.
        if "in_the_past" in validation_issues:
            reply = self._t(state.language, "invalid_datetime_past")
            state.add_turn("assistant", reply, language=state.language)
            return EngineResult(state=state, reply=reply, effects=[])

        reply, effects = self._route(state, profile)
        reply = self._apply_safety_filter(reply, state.language)

        state.add_turn("assistant", reply, language=state.language)
        return EngineResult(state=state, reply=reply, effects=effects)

    # -- clinic-configured escalation rules ---------------------------------

    def _maybe_escalate_on_clinic_rule(
        self, state: ConversationState, message: str, profile: WorkspaceAIProfile
    ) -> EngineResult | None:
        """Phase 10 "clinic escalation rule" trigger: a workspace can
        configure its own keyword list (ai_agents.config["escalation_keywords"],
        e.g. "emergency", "in pain now") that transfers to a human
        immediately, on top of — and checked before — every other intent.
        Returns None if nothing matched, in which case the turn proceeds
        through normal NLU routing."""
        lowered = message.lower()
        for keyword in profile.escalation_keywords:
            if keyword and keyword.lower() in lowered:
                state.status = ConversationStatus.NEEDS_HUMAN
                reply = self._t(state.language, "transfer_to_human")
                state.add_turn("assistant", reply, language=state.language)
                return EngineResult(
                    state=state,
                    reply=reply,
                    effects=[
                        TransferToHumanEffect(
                            reason=f"Caller's message matched a clinic escalation rule: '{keyword}'",
                            trigger="clinic_rule",
                        )
                    ],
                )
        return None

    # -- language handling -------------------------------------------------

    def _resolve_language(
        self, state: ConversationState, message: str, profile: WorkspaceAIProfile
    ) -> str | None:
        """Returns a reply string if the turn should stop here (unsupported
        language / needs repeat), or None if a usable language was
        established and the caller message should proceed to NLU."""
        detection = detect_language(message)
        usable_languages = [code for code in profile.supported_languages if get_language(code)] or ["en"]
        detected_code = normalize_language_code(detection.code, usable_languages)

        if state.language:
            # A language is already established for this call: only
            # reconsider it on a high-confidence signal from a substantial
            # message (a deliberate language switch), not on the routine
            # ambiguity of short slot-filling answers.
            long_enough = len(message.split()) >= _MIN_WORDS_FOR_LANGUAGE_SWITCH

            # An explicit "let's continue in X" is the only reliable way to
            # switch *between* the Perso-Arabic languages (their scripts are
            # statistically inseparable), so it's honoured even when the
            # statistical detector disagrees — as long as the message is
            # substantial enough to be a deliberate request.
            if long_enough:
                mentioned = match_language_mention(message, usable_languages)
                if mentioned is not None and mentioned != state.language:
                    state.language = mentioned
                    state.low_confidence_strikes = 0
                    state.status = ConversationStatus.ACTIVE
                    return None

            if (
                long_enough
                and detection.confidence >= _LANGUAGE_SWITCH_CONFIDENCE
                and detected_code != state.language
            ):
                if detected_code in usable_languages:
                    state.language = detected_code
                    state.low_confidence_strikes = 0
                    return None
                names = ", ".join(get_language(code).name for code in usable_languages if get_language(code))
                state.status = ConversationStatus.AWAITING_LANGUAGE_CHOICE
                return self._t(state.language, "unsupported_language", languages=names)
            return None

        # No language established yet (first turn of the call). A one- or
        # two-word opener ("Hi", "Hola") is too short for statistical
        # language ID to be trustworthy — it routinely misfires on common
        # greeting words. Rather than risk an unwarranted "I don't support
        # that language" on the very first thing the caller says, default
        # to the workspace's primary language; it will still correct itself
        # on the caller's next, more substantial message if needed.
        if len(message.split()) < _MIN_WORDS_FOR_LANGUAGE_SWITCH:
            state.language = usable_languages[0]
            state.low_confidence_strikes = 0
            state.status = ConversationStatus.ACTIVE
            return None

        if detection.confidence >= settings.language_detection_min_confidence and detected_code:
            if detected_code in usable_languages:
                state.language = detected_code
                state.low_confidence_strikes = 0
                state.status = ConversationStatus.ACTIVE
                return None

            # Confidently detected, but this workspace doesn't support it.
            state.status = ConversationStatus.AWAITING_LANGUAGE_CHOICE
            names = ", ".join(get_language(code).name for code in usable_languages if get_language(code))
            return self._t(usable_languages[0], "unsupported_language", languages=names)

        # Low confidence and no language established: ask the caller to
        # repeat, defaulting to the workspace's first supported language.
        fallback_language = usable_languages[0]
        state.low_confidence_strikes += 1
        if state.low_confidence_strikes >= _LOW_CONFIDENCE_TRANSFER_THRESHOLD:
            state.status = ConversationStatus.NEEDS_HUMAN
            return self._t(fallback_language, "low_confidence_offer_transfer")
        return self._t(fallback_language, "low_confidence_repeat")

    # -- entity merging ------------------------------------------------------

    def _merge_entities(
        self, state: ConversationState, nlu_result: NLUResult, profile: WorkspaceAIProfile
    ) -> list[str]:
        """Validates each extracted entity (business rules, no LLM
        involved — see app.ai.qualification.validators) before merging it
        into state. A value that fails validation is simply never written
        into state, so state only ever holds real, caller-provided,
        validated information — never a fabricated or unchecked value.
        Returns the list of validation-failure reason codes encountered."""
        entities = nlu_result.entities
        issues: list[str] = []

        if entities.caller_name:
            name_check = validate_name(entities.caller_name)
            if name_check:
                state.caller.name = entities.caller_name
            else:
                issues.append(name_check.reason)

        if entities.phone_number:
            phone_check = validate_phone(entities.phone_number)
            if phone_check:
                state.caller.phone = entities.phone_number
            else:
                issues.append(phone_check.reason)

        if entities.service:
            # extract_service only ever returns a name already present in
            # the workspace's own service list, so this is defense-in-depth
            # rather than the primary gate — but it's what actually
            # resolves the department, never a guess.
            service_check = validate_service(entities.service, profile.services)
            if service_check:
                state.appointment.service = entities.service
                state.appointment.department = resolve_department(
                    entities.service, profile.service_departments
                )
            else:
                issues.append(service_check.reason)

        if entities.provider:
            # extract_provider only ever returns a name from the workspace's
            # own provider list, or the "no_preference" sentinel — no
            # separate validator needed, both are already-safe values.
            state.appointment.provider = entities.provider

        if entities.appointment_datetime:
            datetime_check = validate_future_datetime(entities.appointment_datetime)
            if datetime_check:
                # A reschedule's date/time always means "move it to this
                # new time" — there is no local record of the *existing*
                # appointment's original time to disambiguate against (that
                # lives in the database, which the engine itself never
                # touches).
                if state.intent == Intent.APPOINTMENT_RESCHEDULE:
                    state.appointment.new_when = entities.appointment_datetime
                else:
                    state.appointment.when = entities.appointment_datetime
            else:
                issues.append(datetime_check.reason)

        return issues

    # -- booking confirmation gate --------------------------------------------

    def _handle_pending_confirmation(self, state: ConversationState, message: str) -> EngineResult:
        """The caller has already been asked "shall I go ahead and book
        it?" — this turn is their yes/no answer, not a new request. On
        "yes", the BookAppointmentEffect is emitted here, but the reply
        text is only a provisional placeholder: receptionist_service.py
        MUST overwrite it with the real outcome once the database write
        actually happens (see render_booking_outcome) — this method itself
        has no way to know whether the booking will actually succeed."""
        answer = classify_confirmation(message, state.language)

        if answer == "yes":
            state.pending_booking_confirmation = False
            effect = BookAppointmentEffect(
                caller_name=state.caller.name,
                phone=state.caller.phone,
                service=state.appointment.service,
                when=state.appointment.when,
                department=state.appointment.department,
                provider=state.appointment.provider,
            )
            reply = self._t(state.language, "processing_request")
            state.add_turn("assistant", reply, language=state.language)
            return EngineResult(state=state, reply=reply, effects=[effect])

        if answer == "no":
            state.pending_booking_confirmation = False
            state.appointment.when = None
            state.missing_fields = ["datetime"]
            reply = self._t(state.language, "ask_datetime")
            state.add_turn("assistant", reply, language=state.language)
            return EngineResult(state=state, reply=reply, effects=[])

        reply = self._t(state.language, "confirmation_unclear")
        state.add_turn("assistant", reply, language=state.language)
        return EngineResult(state=state, reply=reply, effects=[])

    # -- outcome-driven replies (called by receptionist_service.py AFTER the --
    # -- database write actually happens — never before) ---------------------

    def render_booking_outcome(self, state: ConversationState, outcome: BookingOutcome) -> str:
        if outcome == BookingOutcome.CREATED:
            reply = self._t(
                state.language,
                "confirm_booking",
                name=state.caller.name,
                service=state.appointment.service,
                when=_format_when(state.appointment.when),
            )
            state.appointment = AppointmentDraft()
            state.missing_fields = []
            return reply

        if outcome == BookingOutcome.CONFLICT:
            state.appointment.when = None
            state.missing_fields = ["datetime"]
            return self._t(state.language, "booking_conflict")

        if outcome == BookingOutcome.DUPLICATE:
            state.appointment.when = None
            state.missing_fields = ["datetime"]
            return self._t(state.language, "booking_duplicate")

        return self._t(state.language, "processing_request")

    def render_cancellation_outcome(self, state: ConversationState, outcome: BookingOutcome) -> str:
        if outcome == BookingOutcome.CANCELLED:
            return self._t(state.language, "confirm_cancellation")
        if outcome == BookingOutcome.NOT_FOUND:
            return self._t(state.language, "no_appointment_found")
        return self._t(state.language, "processing_request")

    def render_reschedule_outcome(self, state: ConversationState, outcome: BookingOutcome) -> str:
        if outcome == BookingOutcome.RESCHEDULED:
            reply = self._t(state.language, "confirm_reschedule", when=_format_when(state.appointment.new_when))
            state.appointment.new_when = None
            state.missing_fields = []
            return reply
        if outcome == BookingOutcome.NOT_FOUND:
            return self._t(state.language, "no_appointment_found")
        if outcome == BookingOutcome.RESCHEDULE_CONFLICT:
            state.appointment.new_when = None
            state.missing_fields = ["new_datetime"]
            return self._t(state.language, "booking_conflict")
        return self._t(state.language, "processing_request")

    def render_transfer_reply(self, language: str | None) -> str:
        """Used by receptionist_service.py for the "technical failure"
        transfer trigger: the engine itself raised an exception, so there's
        no normal reply/effects pair to fall back on — just the standard
        transfer wording in whatever language was established."""
        return self._t(language, "transfer_to_human")

    # -- intent routing ------------------------------------------------------

    def _route(self, state: ConversationState, profile: WorkspaceAIProfile) -> tuple[str, list[Effect]]:
        intent = state.intent

        if intent == Intent.HUMAN_TRANSFER:
            state.status = ConversationStatus.NEEDS_HUMAN
            return self._t(state.language, "transfer_to_human"), [
                TransferToHumanEffect(reason="Caller requested a human receptionist", trigger="caller_request")
            ]

        if intent == Intent.UNSUPPORTED_REQUEST:
            state.status = ConversationStatus.NEEDS_HUMAN
            return self._t(state.language, "transfer_to_human"), [
                TransferToHumanEffect(
                    reason="Caller's request (e.g. billing, insurance, legal) is outside the AI "
                    "Receptionist's supported scope",
                    trigger="unsupported_request",
                )
            ]

        if intent == Intent.APPOINTMENT_BOOKING:
            reply, effects = self._handle_booking(state, profile)
            booking_completed = any(isinstance(e, BookAppointmentEffect) for e in effects)
            lead_effect = self._maybe_lead_effect(state, booking_completed=booking_completed)
            if lead_effect is not None:
                effects = [*effects, lead_effect]
            return reply, effects

        if intent == Intent.APPOINTMENT_CANCELLATION:
            return self._handle_cancellation(state)

        if intent == Intent.APPOINTMENT_RESCHEDULE:
            return self._handle_reschedule(state)

        reply = self._handle_open_ended(state, profile)
        lead_effect = self._maybe_lead_effect(state, booking_completed=False)
        return reply, ([lead_effect] if lead_effect is not None else [])

    def _maybe_lead_effect(self, state: ConversationState, *, booking_completed: bool) -> UpsertLeadEffect | None:
        """A caller becomes a Lead the moment we know how to reach them (a
        phone number) and they aren't already an identified existing
        patient (cancel/reschedule/transfer callers are looked up by phone
        directly — they're never treated as prospects). Status only ever
        escalates (new -> qualifying -> converted); receptionist_service.py
        enforces that via qualification.next_lead_status so a later,
        less-informative turn can't downgrade it."""
        if state.intent in _NON_LEAD_INTENTS or not state.caller.phone:
            return None

        if state.intent == Intent.APPOINTMENT_BOOKING:
            status = "converted" if booking_completed else "qualifying"
        else:
            status = "new"

        notes = None
        if state.appointment.service:
            notes = f"Interested in {state.appointment.service}"
            if state.appointment.department:
                notes += f" ({state.appointment.department})"

        return UpsertLeadEffect(phone=state.caller.phone, name=state.caller.name, status=status, notes=notes)

    def _handle_booking(
        self, state: ConversationState, profile: WorkspaceAIProfile
    ) -> tuple[str, list[Effect]]:
        """Collects and validates every booking requirement (caller info,
        service, provider if the workspace has any configured, date/time),
        then — once everything is present — asks the caller to confirm
        before anything is written anywhere. No effect is emitted from this
        method: the actual booking attempt only happens once the caller
        answers "yes" (see _handle_pending_confirmation), and even then the
        reply isn't allowed to say "confirmed" until receptionist_service.py
        reports the database write actually succeeded."""
        missing = []
        if not state.caller.name:
            missing.append("name")
        if not state.caller.phone:
            missing.append("phone")
        if not state.appointment.service:
            missing.append("service")
        if profile.providers and not state.appointment.provider:
            missing.append("provider")
        if not state.appointment.when:
            missing.append("datetime")
        state.missing_fields = missing

        if missing:
            return self._ask_for(state.language, missing[0], profile), []

        state.pending_booking_confirmation = True
        reply = self._t(
            state.language,
            "confirm_booking_prompt",
            service=state.appointment.service,
            when=_format_when(state.appointment.when),
        )
        return reply, []

    def _handle_cancellation(self, state: ConversationState) -> tuple[str, list[Effect]]:
        if not state.caller.phone:
            state.missing_fields = ["phone"]
            return self._t(state.language, "ask_phone"), []

        state.missing_fields = []
        # Provisional only — receptionist_service.py overrides this with
        # render_cancellation_outcome() once it knows whether a matching
        # appointment actually existed and was cancelled.
        reply = self._t(state.language, "processing_request")
        return reply, [CancelAppointmentEffect(phone=state.caller.phone)]

    def _handle_reschedule(self, state: ConversationState) -> tuple[str, list[Effect]]:
        missing = []
        if not state.caller.phone:
            missing.append("phone")
        if not state.appointment.new_when:
            missing.append("new_datetime")
        state.missing_fields = missing

        if missing:
            return self._ask_for(state.language, missing[0], None), []

        # Provisional only — receptionist_service.py overrides this with
        # render_reschedule_outcome() once it knows whether the appointment
        # existed and the new slot was actually free.
        reply = self._t(state.language, "processing_request")
        effect = RescheduleAppointmentEffect(phone=state.caller.phone, new_when=state.appointment.new_when)
        return reply, [effect]

    def _handle_open_ended(self, state: ConversationState, profile: WorkspaceAIProfile) -> str:
        # Full clinic-aware system prompt (doctors, services, appointment
        # rules, general info, emergency protocol, tone, preferred language)
        # from the workspace's saved settings — same builder as
        # generate_system_prompt(clinic_id).
        system = (
            f"{render_system_prompt(profile)}\n\n"
            f"Respond in this language code: {state.language}. Keep replies short (1-2 sentences)."
        )
        messages = [LLMMessage(role="system", content=system)]
        for turn in state.history[-6:]:
            role = "assistant" if turn.role == "assistant" else "user"
            messages.append(LLMMessage(role=role, content=turn.text))

        if len(state.history) <= 1:
            return self._t(state.language, "greeting", clinic_name=profile.clinic_name)

        response = self._llm.complete(messages)
        return response.content.strip()

    # -- helpers ---------------------------------------------------------

    def _ask_for(self, language: str, field_name: str, profile: WorkspaceAIProfile | None) -> str:
        if field_name == "name":
            return self._t(language, "ask_name")
        if field_name == "phone":
            return self._t(language, "ask_phone")
        if field_name == "service":
            services = ", ".join(profile.services) if profile and profile.services else ""
            return self._t(language, "ask_service", services=services)
        if field_name == "provider":
            providers = ", ".join(profile.providers) if profile and profile.providers else ""
            return self._t(language, "ask_provider", providers=providers)
        if field_name in ("datetime", "new_datetime"):
            key = "ask_new_datetime" if field_name == "new_datetime" else "ask_datetime"
            return self._t(language, key)
        return self._t(language, "ask_phone")

    def _apply_safety_filter(self, reply: str, language: str | None) -> str:
        if contains_clinical_content(reply, language):
            return self._t(language, "clinical_refusal")
        return reply

    def _t(self, language: str | None, key: str, **kwargs) -> str:
        profile = get_language(language or "en") or get_language("en")
        template = profile.templates[key]
        try:
            return template.format(**kwargs)
        except KeyError:
            return template


def _format_when(when) -> str:
    if when is None:
        return ""
    return when.strftime("%A, %B %d at %I:%M %p").replace(" 0", " ")
