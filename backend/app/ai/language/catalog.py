from dataclasses import dataclass, field


@dataclass
class LanguageProfile:
    code: str
    name: str
    # Template key -> str.format()-style template. Every profile must define
    # the same set of keys (TEMPLATE_KEYS) so the conversation engine can
    # render any state in any supported language interchangeably.
    templates: dict[str, str] = field(default_factory=dict)
    # --- live-voice metadata (Phase 16 multilingual) ------------------------
    # Endonym, shown to the caller/agent when listing supported languages.
    native_name: str = ""
    # Short note on the dialect/register the AI Receptionist should keep
    # when speaking this language — folded into the system prompt.
    dialect_note: str = ""
    # "Latin" | "Perso-Arabic" | ... Used by the language detector: several
    # of the supported South-Asian languages share the Perso-Arabic script
    # and are not separable by statistical text ID, so detection leans on
    # the STT provider's own language hint for those.
    script: str = "Latin"
    perso_arabic: bool = False
    # Locale/language codes handed to the speech providers as-is. `None`
    # means "let the provider auto-detect / use its multilingual default".
    stt_locale: str | None = None
    tts_locale: str | None = None


TEMPLATE_KEYS = [
    "greeting",
    "ask_name",
    "ask_phone",
    "ask_service",
    "ask_datetime",
    "confirm_booking",
    "no_appointment_found",
    "confirm_cancellation",
    "ask_new_datetime",
    "confirm_reschedule",
    "transfer_to_human",
    "clinical_refusal",
    "unsupported_language",
    "low_confidence_repeat",
    "low_confidence_offer_transfer",
    "invalid_datetime_past",
    "ask_provider",
    "confirm_booking_prompt",
    "confirmation_unclear",
    "processing_request",
    "booking_conflict",
    "booking_duplicate",
]

_REGISTRY: dict[str, LanguageProfile] = {}


def register_language(profile: LanguageProfile) -> None:
    """Adds (or replaces) a supported language at runtime. This is the whole
    extension point: supporting a new language is calling this once with a
    fully-populated LanguageProfile — no other code changes anywhere in the
    conversation engine, NLU, or API layer."""
    missing = [key for key in TEMPLATE_KEYS if key not in profile.templates]
    if missing:
        raise ValueError(f"LanguageProfile '{profile.code}' is missing templates: {missing}")
    _REGISTRY[profile.code] = profile


def get_language(code: str) -> LanguageProfile | None:
    return _REGISTRY.get(code)


def list_registered_languages() -> list[str]:
    return sorted(_REGISTRY.keys())


register_language(
    LanguageProfile(
        code="en",
        name="English",
        templates={
            "greeting": "Hello! Thanks for calling {clinic_name}. How can I help you today?",
            "ask_name": "Could I get your full name, please?",
            "ask_phone": "And what's the best phone number to reach you at?",
            "ask_service": "What service would you like to book? We offer: {services}.",
            "ask_datetime": "What day and time work best for you?",
            "confirm_booking": "You're all set, {name} — I've booked {service} on {when}. Anything else?",
            "no_appointment_found": "I couldn't find an upcoming appointment under that phone number.",
            "confirm_cancellation": "Done — I've cancelled that appointment for you.",
            "ask_new_datetime": "What day and time would you like to move it to?",
            "confirm_reschedule": "All set — I've moved your appointment to {when}.",
            "transfer_to_human": "Of course, let me connect you with our front desk staff now.",
            "clinical_refusal": (
                "I'm not able to give medical advice, diagnoses, or prescriptions — only our "
                "clinical staff can help with that. Would you like me to transfer you to them?"
            ),
            "unsupported_language": (
                "Sorry, I don't yet support that language. I can help you in: {languages}. "
                "Please choose one, or I can transfer you to our front desk staff."
            ),
            "low_confidence_repeat": "Sorry, I didn't quite catch that — could you repeat it?",
            "low_confidence_offer_transfer": (
                "I'm having trouble understanding — would you like me to transfer you to our "
                "front desk staff instead?"
            ),
            "invalid_datetime_past": "That time's already passed — could you give me a day and time in the future?",
            "ask_provider": "Which provider would you like to see? We have: {providers}. Or just let me know if you have no preference.",
            "confirm_booking_prompt": "I have you down for {service} on {when} — shall I go ahead and book it?",
            "confirmation_unclear": "Sorry, was that a yes or a no?",
            "processing_request": "One moment please.",
            "booking_conflict": "I'm sorry, that time is no longer available. What other day or time would work?",
            "booking_duplicate": "It looks like you already have an appointment scheduled around that time.",
        },
    )
)

register_language(
    LanguageProfile(
        code="es",
        name="Español",
        templates={
            "greeting": "¡Hola! Gracias por llamar a {clinic_name}. ¿En qué puedo ayudarle hoy?",
            "ask_name": "¿Podría darme su nombre completo, por favor?",
            "ask_phone": "¿Cuál es el mejor número de teléfono para contactarle?",
            "ask_service": "¿Qué servicio le gustaría reservar? Ofrecemos: {services}.",
            "ask_datetime": "¿Qué día y hora le funcionan mejor?",
            "confirm_booking": "Listo, {name} — he reservado {service} el {when}. ¿Algo más?",
            "no_appointment_found": "No encontré ninguna cita próxima con ese número de teléfono.",
            "confirm_cancellation": "Hecho — he cancelado esa cita.",
            "ask_new_datetime": "¿A qué día y hora le gustaría cambiarla?",
            "confirm_reschedule": "Listo — he movido su cita al {when}.",
            "transfer_to_human": "Claro, le comunico con nuestro personal de recepción ahora mismo.",
            "clinical_refusal": (
                "No puedo dar consejos médicos, diagnósticos ni recetar medicamentos — solo "
                "nuestro personal clínico puede ayudar con eso. ¿Le gustaría que le transfiera?"
            ),
            "unsupported_language": (
                "Lo siento, aún no puedo atender en ese idioma. Puedo ayudarle en: {languages}. "
                "Por favor elija uno, o puedo transferirle con nuestro personal de recepción."
            ),
            "low_confidence_repeat": "Perdón, no entendí bien — ¿podría repetirlo?",
            "low_confidence_offer_transfer": (
                "Estoy teniendo dificultades para entender — ¿le gustaría que le transfiera con "
                "nuestro personal de recepción?"
            ),
            "invalid_datetime_past": "Esa hora ya pasó — ¿podría darme un día y hora en el futuro?",
            "ask_provider": "¿Con qué proveedor le gustaría atenderse? Tenemos: {providers}. O dígame si no tiene preferencia.",
            "confirm_booking_prompt": "Le tengo anotado {service} el {when} — ¿procedo a reservarlo?",
            "confirmation_unclear": "Perdón, ¿eso fue un sí o un no?",
            "processing_request": "Un momento, por favor.",
            "booking_conflict": "Lo siento, ese horario ya no está disponible. ¿Qué otro día u hora le vendría bien?",
            "booking_duplicate": "Parece que ya tiene una cita programada cerca de ese horario.",
        },
    )
)

register_language(
    LanguageProfile(
        code="fr",
        name="Français",
        templates={
            "greeting": "Bonjour ! Merci d'avoir appelé {clinic_name}. Comment puis-je vous aider ?",
            "ask_name": "Pourrais-je avoir votre nom complet, s'il vous plaît ?",
            "ask_phone": "Quel est le meilleur numéro de téléphone pour vous joindre ?",
            "ask_service": "Quel service souhaitez-vous réserver ? Nous proposons : {services}.",
            "ask_datetime": "Quel jour et quelle heure vous conviendraient le mieux ?",
            "confirm_booking": "C'est noté, {name} — j'ai réservé {service} le {when}. Autre chose ?",
            "no_appointment_found": "Je n'ai trouvé aucun rendez-vous à venir avec ce numéro.",
            "confirm_cancellation": "C'est fait — j'ai annulé ce rendez-vous.",
            "ask_new_datetime": "À quel jour et quelle heure souhaitez-vous le déplacer ?",
            "confirm_reschedule": "C'est fait — votre rendez-vous a été déplacé au {when}.",
            "transfer_to_human": "Bien sûr, je vous mets en relation avec notre accueil.",
            "clinical_refusal": (
                "Je ne peux pas donner de conseils médicaux, de diagnostic ni prescrire de "
                "médicaments — seul notre personnel clinique le peut. Voulez-vous que je vous transfère ?"
            ),
            "unsupported_language": (
                "Désolé, je ne prends pas encore en charge cette langue. Je peux vous aider en : "
                "{languages}. Merci d'en choisir une, ou je peux vous transférer à l'accueil."
            ),
            "low_confidence_repeat": "Désolé, je n'ai pas bien compris — pouvez-vous répéter ?",
            "low_confidence_offer_transfer": (
                "J'ai du mal à comprendre — souhaitez-vous que je vous transfère à notre accueil ?"
            ),
            "invalid_datetime_past": "Cette heure est déjà passée — pouvez-vous me donner un jour et une heure futurs ?",
            "ask_provider": "Quel praticien souhaitez-vous voir ? Nous avons : {providers}. Ou dites-moi si vous n'avez pas de préférence.",
            "confirm_booking_prompt": "J'ai noté {service} le {when} — dois-je procéder à la réservation ?",
            "confirmation_unclear": "Désolé, était-ce un oui ou un non ?",
            "processing_request": "Un instant, s'il vous plaît.",
            "booking_conflict": "Désolé, ce créneau n'est plus disponible. Quel autre jour ou heure vous conviendrait ?",
            "booking_duplicate": "Il semble que vous ayez déjà un rendez-vous prévu à ce moment-là.",
        },
    )
)

register_language(
    LanguageProfile(
        code="de",
        name="Deutsch",
        templates={
            "greeting": "Hallo! Danke für Ihren Anruf bei {clinic_name}. Wie kann ich Ihnen helfen?",
            "ask_name": "Könnte ich bitte Ihren vollständigen Namen haben?",
            "ask_phone": "Unter welcher Telefonnummer erreichen wir Sie am besten?",
            "ask_service": "Welchen Termin möchten Sie buchen? Wir bieten an: {services}.",
            "ask_datetime": "Welcher Tag und welche Uhrzeit passen Ihnen am besten?",
            "confirm_booking": "Alles erledigt, {name} — ich habe {service} am {when} gebucht. Sonst noch etwas?",
            "no_appointment_found": "Ich konnte unter dieser Telefonnummer keinen anstehenden Termin finden.",
            "confirm_cancellation": "Erledigt — ich habe diesen Termin storniert.",
            "ask_new_datetime": "Auf welchen Tag und welche Uhrzeit möchten Sie ihn verschieben?",
            "confirm_reschedule": "Erledigt — Ihr Termin wurde auf {when} verschoben.",
            "transfer_to_human": "Gerne, ich verbinde Sie jetzt mit unserem Empfangsteam.",
            "clinical_refusal": (
                "Ich kann keine medizinische Beratung, Diagnosen oder Rezepte anbieten — das kann "
                "nur unser klinisches Personal. Möchten Sie, dass ich Sie verbinde?"
            ),
            "unsupported_language": (
                "Entschuldigung, diese Sprache unterstütze ich noch nicht. Ich kann Ihnen helfen "
                "auf: {languages}. Bitte wählen Sie eine, oder ich verbinde Sie mit dem Empfang."
            ),
            "low_confidence_repeat": "Entschuldigung, das habe ich nicht ganz verstanden — können Sie das wiederholen?",
            "low_confidence_offer_transfer": (
                "Ich habe Schwierigkeiten, Sie zu verstehen — soll ich Sie mit unserem "
                "Empfangsteam verbinden?"
            ),
            "invalid_datetime_past": "Diese Zeit liegt bereits in der Vergangenheit — können Sie mir einen zukünftigen Tag und Uhrzeit nennen?",
            "ask_provider": "Welchen Anbieter möchten Sie sehen? Wir haben: {providers}. Oder sagen Sie mir, wenn Sie keine Präferenz haben.",
            "confirm_booking_prompt": "Ich habe {service} am {when} notiert — soll ich das jetzt buchen?",
            "confirmation_unclear": "Entschuldigung, war das ein Ja oder ein Nein?",
            "processing_request": "Einen Moment bitte.",
            "booking_conflict": "Es tut mir leid, dieser Termin ist nicht mehr verfügbar. Welcher andere Tag oder welche andere Uhrzeit würde passen?",
            "booking_duplicate": "Es sieht so aus, als hätten Sie bereits einen Termin zu dieser Zeit.",
        },
    )
)
