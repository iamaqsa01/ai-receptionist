from app.ai.nlu.keywords import INTENT_KEYWORDS
from app.ai.nlu.schema import Intent

# The AI Receptionist must never diagnose, prescribe, or make clinical
# decisions. This check is applied twice: (1) to classify an incoming
# caller message as a clinical request, and (2) as a defense-in-depth
# filter over any *generated* reply before it's sent to the caller, in
# case a free-form LLM completion drifts into clinical territory.
SAFETY_SYSTEM_INSTRUCTION = (
    "You must never provide a medical diagnosis, prescribe or recommend medication, "
    "interpret test/lab results, or make any clinical decision. If asked to do any of "
    "that, politely decline and offer to connect the caller with clinical staff. You "
    "only handle administrative tasks: scheduling, rescheduling, cancelling "
    "appointments, collecting caller information, and general front-desk questions."
)


def contains_clinical_content(text: str, language: str | None) -> bool:
    lowered = text.lower()
    terms = list(INTENT_KEYWORDS.get(language or "en", {}).get(Intent.CLINICAL_REQUEST, []))
    if language != "en":
        terms += INTENT_KEYWORDS.get("en", {}).get(Intent.CLINICAL_REQUEST, [])
    return any(term in lowered for term in terms)
