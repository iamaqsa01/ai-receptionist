import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.language.catalog import get_language
from app.ai.nlu.safety import SAFETY_SYSTEM_INSTRUCTION
from app.core.config import settings
from app.database.session import SessionLocal
from app.models.ai_agent import AIAgent
from app.models.provider import Provider
from app.models.service import Service
from app.models.workspace import Workspace

DEFAULT_INSTRUCTIONS = (
    "You are a professional, warm medical office receptionist assistant. You help "
    "callers book, reschedule, or cancel appointments, collect their contact details, "
    "and answer general administrative questions about the clinic. Keep replies brief "
    "and natural, as if spoken on a phone call."
)


@dataclass
class WorkspaceAIProfile:
    """Workspace-specific configuration for the AI Receptionist, loaded from
    that workspace's ai_agents row (falling back to sensible defaults). This
    is the "workspace-specific AI instructions" requirement: each clinic can
    customize its persona/instructions, supported languages, and service
    list without any code change."""

    workspace_id: uuid.UUID
    clinic_name: str
    instructions: str
    supported_languages: list[str]
    services: list[str]
    # Maps a service name to the department that handles it, e.g.
    # {"Cleaning": "Hygiene", "Root Canal": "Endodontics"}. Configured per
    # workspace (ai_agents.config["service_departments"]); services with no
    # entry simply have no resolvable department — never guessed.
    service_departments: dict[str, str] = field(default_factory=dict)
    # Active providers a caller can choose between. Empty means the
    # workspace hasn't configured providers — provider selection is then
    # skipped entirely rather than forced.
    providers: list[str] = field(default_factory=list)
    # IANA timezone the clinic operates in (e.g. "America/New_York"),
    # straight from workspace.timezone — every caller-stated time is
    # interpreted in this zone, never the server's own.
    timezone: str = "UTC"
    # Keyword-triggered escalation rules a clinic can configure — any
    # caller message containing one of these (case-insensitive substring
    # match) transfers to a human immediately, regardless of intent
    # classification (ai_agents.config["escalation_keywords"]).
    escalation_keywords: list[str] = field(default_factory=list)
    # Phone number a live call is transferred to on any human handoff, when
    # the telephony provider supports live transfer
    # (ai_agents.config["human_transfer_number"]). None means no live
    # transfer is attempted — the handoff is still recorded either way.
    human_transfer_number: str | None = None
    # --- Clinic settings / AI knowledge base (ai_agents.config["clinic_settings"],
    # saved from the dashboard via PUT /workspaces/{id}/clinic-settings). All
    # optional: an unconfigured clinic simply omits the section from the prompt.
    doctors: list[dict] = field(default_factory=list)
    clinic_services: list[str] = field(default_factory=list)
    appointment_settings: dict = field(default_factory=dict)
    general_info: dict = field(default_factory=dict)
    emergency_protocol: str | None = None
    tone: str | None = None
    preferred_language: str | None = None


def load_workspace_profile(db: Session, workspace_id: uuid.UUID) -> WorkspaceAIProfile:
    workspace = db.get(Workspace, workspace_id)
    clinic_name = workspace.name if workspace else "our clinic"
    workspace_timezone = workspace.timezone if workspace else "UTC"

    agent = db.execute(
        select(AIAgent)
        .where(AIAgent.workspace_id == workspace_id, AIAgent.is_active.is_(True))
        .order_by(AIAgent.created_at)
    ).scalars().first()
    config = agent.config if agent else {}

    supported_languages = config.get("supported_languages") or settings.default_supported_languages_list
    instructions = config.get("instructions") or DEFAULT_INSTRUCTIONS
    service_departments = config.get("service_departments") or {}
    escalation_keywords = config.get("escalation_keywords") or []
    human_transfer_number = config.get("human_transfer_number")

    clinic_settings = config.get("clinic_settings") or {}
    appointment_settings = clinic_settings.get("appointment_settings") or {}
    general_info = clinic_settings.get("general_info") or {}

    services = list(
        db.execute(
            select(Service.name).where(Service.workspace_id == workspace_id, Service.is_active.is_(True))
        ).scalars()
    )
    providers = list(
        db.execute(
            select(Provider.name).where(Provider.workspace_id == workspace_id, Provider.is_active.is_(True))
        ).scalars()
    )

    return WorkspaceAIProfile(
        workspace_id=workspace_id,
        clinic_name=clinic_name,
        instructions=instructions,
        supported_languages=supported_languages,
        services=services,
        service_departments=service_departments,
        providers=providers,
        timezone=workspace_timezone,
        escalation_keywords=escalation_keywords,
        human_transfer_number=human_transfer_number,
        doctors=clinic_settings.get("doctors") or [],
        clinic_services=clinic_settings.get("services") or [],
        appointment_settings=appointment_settings,
        general_info=general_info,
        emergency_protocol=clinic_settings.get("emergency_protocol"),
        tone=clinic_settings.get("agent_tone"),
        preferred_language=clinic_settings.get("preferred_language"),
    )


def generate_system_prompt(clinic_id: uuid.UUID, db: Session | None = None) -> str:
    """Build the AI Receptionist's full system prompt for one clinic
    (``clinic_id`` is the workspace id), dynamically folding in that
    clinic's saved settings: doctors, services, appointment rules, general
    information, emergency protocol, tone, and preferred language.

    Pass ``db`` to reuse an open session; otherwise a short-lived one is
    opened and closed here."""
    if db is not None:
        return render_system_prompt(load_workspace_profile(db, clinic_id))

    session = SessionLocal()
    try:
        return render_system_prompt(load_workspace_profile(session, clinic_id))
    finally:
        session.close()


def _language_policy_lines(profile: "WorkspaceAIProfile") -> list[str]:
    """Multilingual live-voice policy folded into the system prompt. The
    detected conversation language is enforced separately by the
    ConversationEngine (it always renders replies via that language's
    template set); this block governs the free-form LLM replies
    (general-inquiry answers) so they stay in the caller's language and
    dialect too."""
    codes = [code for code in (profile.supported_languages or []) if get_language(code)]
    if not codes:
        return []

    described: list[str] = []
    for code in codes:
        lang = get_language(code)
        label = lang.native_name or lang.name
        if lang.name and lang.name.lower() not in label.lower():
            label = f"{lang.name} ({label})"
        if lang.dialect_note:
            label = f"{label} — {lang.dialect_note.rstrip('.')}"
        described.append(label)

    lines = ["", "Language policy (spoken phone call):"]
    lines.append("- Supported languages: " + "; ".join(described) + ".")
    lines.append(
        "- Detect the language the caller is CURRENTLY speaking and reply only in that "
        "same language, matching its dialect/register where noted above."
    )
    lines.append(
        "- Do not switch to English (or any other language) unless the caller does first. "
        "Keep the caller's language for the whole call unless they clearly change it "
        "themselves, then follow the change."
    )
    lines.append(
        "- Never claim to support a language that is not in the list above. If the caller "
        "uses an unsupported language, say so briefly and offer to continue in a supported "
        "one or transfer to front-desk staff."
    )
    return lines


def render_system_prompt(profile: "WorkspaceAIProfile") -> str:
    lines: list[str] = [profile.instructions.strip(), "", SAFETY_SYSTEM_INSTRUCTION, ""]

    lines.append(f"Clinic name: {profile.clinic_name}.")
    lines.append(f"Operating timezone: {profile.timezone}.")

    if profile.tone:
        lines.append(f"Speak in a {profile.tone} tone at all times.")
    language = profile.preferred_language
    if language:
        lines.append(
            f"Speak and reply in {language}. If the caller clearly uses a different "
            f"supported language, follow their language instead."
        )

    lines.extend(_language_policy_lines(profile))

    gi = profile.general_info or {}
    general_bits: list[str] = []
    if gi.get("address"):
        general_bits.append(f"Address: {gi['address']}")
    if gi.get("google_maps_link"):
        general_bits.append(f"Google Maps: {gi['google_maps_link']}")
    parking = gi.get("parking_available")
    if parking is not None:
        general_bits.append("Parking is available on site" if parking else "No on-site parking is available")
    if gi.get("accepted_payment_methods"):
        general_bits.append("Accepted payment methods: " + ", ".join(gi["accepted_payment_methods"]))
    if general_bits:
        lines.append("")
        lines.append("General information:")
        lines.extend(f"- {bit}" for bit in general_bits)

    if profile.doctors:
        lines.append("")
        lines.append("Doctors:")
        for doc in profile.doctors:
            parts = [str(doc.get("name") or "").strip() or "Unnamed doctor"]
            if doc.get("specialty"):
                parts.append(f"specialty: {doc['specialty']}")
            if doc.get("timings"):
                parts.append(f"timings: {doc['timings']}")
            fee = doc.get("consultation_fee")
            if fee is not None:
                parts.append(f"consultation fee: {fee}")
            lines.append("- " + "; ".join(parts))

    services = profile.clinic_services or profile.services
    lines.append("")
    lines.append("Available services: " + (", ".join(services) if services else "not listed"))

    if profile.providers:
        lines.append("Bookable providers: " + ", ".join(profile.providers))

    appt = profile.appointment_settings or {}
    appt_bits: list[str] = []
    if appt.get("default_slot_duration_minutes"):
        appt_bits.append(f"default appointment slot is {appt['default_slot_duration_minutes']} minutes")
    if appt.get("max_daily_bookings") is not None:
        appt_bits.append(f"at most {appt['max_daily_bookings']} bookings can be made per day")
    if appt_bits:
        lines.append("")
        lines.append("Appointment rules: " + "; ".join(appt_bits) + ".")

    lines.append("")
    lines.append("EMERGENCY PROTOCOL (critical):")
    if profile.emergency_protocol:
        lines.append(profile.emergency_protocol.strip())
    else:
        lines.append(
            "If a caller indicates a medical emergency, immediately advise them to call "
            "their local emergency number or go to the nearest emergency department, and "
            "offer to connect them to clinic staff."
        )
    lines.append(
        "If a caller indicates a medical emergency, you MUST follow the emergency protocol "
        "above. Do NOT attempt to diagnose the caller and do NOT provide any independent "
        "medical treatment instructions."
    )

    lines.append("")
    lines.append("Keep replies brief and natural, as if spoken on a phone call.")

    return "\n".join(lines)
