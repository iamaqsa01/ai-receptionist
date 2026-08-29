from app.ai.nlu.schema import Intent

# Multilingual, keyword-based intent signals. This is the extension point for
# rule-based classification in a new language: add a language key here (and
# to app.ai.language.catalog) — no other code changes needed. Real LLM
# providers additionally refine this with a model call; the mock provider
# and the fallback path rely on this table alone.
INTENT_KEYWORDS: dict[str, dict[Intent, list[str]]] = {
    "en": {
        Intent.CLINICAL_REQUEST: [
            "diagnose", "diagnosis", "prescribe", "prescription", "medication dosage",
            "what's wrong with me", "is this cancer", "medical advice", "what disease",
        ],
        Intent.HUMAN_TRANSFER: [
            "speak to a person", "human", "receptionist", "representative",
            "talk to someone", "real person", "front desk",
        ],
        Intent.UNSUPPORTED_REQUEST: [
            "billing question", "insurance claim", "file a complaint", "legal matter",
            "speak to a lawyer", "refund request", "invoice dispute",
        ],
        Intent.APPOINTMENT_CANCELLATION: ["cancel"],
        Intent.APPOINTMENT_RESCHEDULE: ["reschedule", "move my appointment", "change my appointment", "change the time"],
        Intent.APPOINTMENT_BOOKING: ["book", "schedule", "make an appointment", "set up an appointment", "appointment"],
        Intent.GREETING: ["hello", "hi ", "hi,", "good morning", "good afternoon", "hey"],
    },
    "es": {
        Intent.CLINICAL_REQUEST: [
            "diagnóstico", "diagnosticar", "recetar", "receta", "qué medicamento",
            "es cáncer", "consejo médico", "qué enfermedad",
        ],
        Intent.HUMAN_TRANSFER: ["hablar con una persona", "humano", "recepcionista", "representante", "persona real"],
        Intent.UNSUPPORTED_REQUEST: [
            "pregunta de facturación", "reclamo de seguro", "presentar una queja", "asunto legal", "reembolso",
        ],
        Intent.APPOINTMENT_CANCELLATION: ["cancelar"],
        Intent.APPOINTMENT_RESCHEDULE: ["reprogramar", "cambiar mi cita", "mover mi cita"],
        Intent.APPOINTMENT_BOOKING: ["reservar", "agendar", "programar una cita", "cita", "hacer una cita"],
        Intent.GREETING: ["hola", "buenos días", "buenas tardes", "buenas"],
    },
    "fr": {
        Intent.CLINICAL_REQUEST: [
            "diagnostic", "diagnostiquer", "prescrire", "ordonnance", "quel médicament",
            "est-ce un cancer", "conseil médical", "quelle maladie",
        ],
        Intent.HUMAN_TRANSFER: ["parler à une personne", "humain", "réceptionniste", "représentant"],
        Intent.UNSUPPORTED_REQUEST: [
            "question de facturation", "réclamation d'assurance", "déposer une plainte", "affaire juridique", "remboursement",
        ],
        Intent.APPOINTMENT_CANCELLATION: ["annuler"],
        Intent.APPOINTMENT_RESCHEDULE: ["reprogrammer", "déplacer mon rendez-vous", "changer mon rendez-vous"],
        Intent.APPOINTMENT_BOOKING: ["réserver", "prendre rendez-vous", "rendez-vous", "planifier"],
        Intent.GREETING: ["bonjour", "salut", "bonsoir"],
    },
    "de": {
        Intent.CLINICAL_REQUEST: [
            "diagnose", "diagnostizieren", "verschreiben", "rezept", "welches medikament",
            "ist das krebs", "medizinischen rat", "welche krankheit",
        ],
        Intent.HUMAN_TRANSFER: ["mit einer person sprechen", "mensch", "empfang", "mitarbeiter"],
        Intent.UNSUPPORTED_REQUEST: [
            "frage zur abrechnung", "versicherungsanspruch", "beschwerde einreichen", "rechtliche angelegenheit", "rückerstattung",
        ],
        Intent.APPOINTMENT_CANCELLATION: ["stornieren", "absagen"],
        Intent.APPOINTMENT_RESCHEDULE: ["verschieben", "termin ändern", "umbuchen"],
        Intent.APPOINTMENT_BOOKING: ["buchen", "termin vereinbaren", "termin", "reservieren"],
        Intent.GREETING: ["hallo", "guten tag", "guten morgen"],
    },
}

# Priority order matters: safety-critical intents are checked first so a
# message that mentions both, e.g., "cancel" and "prescription" is treated
# as clinical (the higher-stakes classification) rather than administrative.
INTENT_PRIORITY = [
    Intent.CLINICAL_REQUEST,
    Intent.UNSUPPORTED_REQUEST,
    Intent.HUMAN_TRANSFER,
    Intent.APPOINTMENT_CANCELLATION,
    Intent.APPOINTMENT_RESCHEDULE,
    Intent.APPOINTMENT_BOOKING,
    Intent.GREETING,
]
