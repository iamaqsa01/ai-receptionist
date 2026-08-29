"""Plain-text message content for each notification event. Kept as pure
string-building functions (no I/O, no DB) so they're trivially testable and
reusable across both channels — WhatsApp sends the body as-is; email pairs
it with a short subject line."""

from datetime import datetime

# Appointment reminders and confirmations are ONLY ever generated in English
# or Urdu, regardless of the language the call itself was conducted in (a
# caller who spoke Punjabi/Saraiki/Sindhi/Pashto still gets an en/ur
# reminder). This is deliberate — see requirement 3.
NOTIFICATION_LANGUAGES = ("en", "ur")


def normalize_notification_language(code: str | None) -> str:
    """Collapses any language code onto the only two the notification layer
    supports. Anything that isn't Urdu becomes English."""
    return "ur" if (code or "").strip().lower() == "ur" else "en"


def _format_when(start: datetime) -> str:
    # "%-I"/"%-d" aren't portable on Windows; strip a leading zero instead.
    return start.strftime("%A, %B %d at %I:%M %p").replace(" 0", " ")


def _format_time(start: datetime) -> str:
    return start.strftime("%I:%M %p").replace(" 0", " ").lstrip("0")


def appointment_confirmation_body(patient_name: str, service_summary: str, start: datetime) -> str:
    return f"Hi {patient_name}, your appointment for {service_summary} is confirmed for {_format_when(start)}."


def appointment_cancellation_body(patient_name: str, service_summary: str, start: datetime) -> str:
    return (
        f"Hi {patient_name}, your appointment for {service_summary} on {_format_when(start)} "
        "has been cancelled."
    )


def appointment_reschedule_body(patient_name: str, service_summary: str, start: datetime) -> str:
    return (
        f"Hi {patient_name}, your appointment for {service_summary} has been rescheduled to "
        f"{_format_when(start)}."
    )


def clinic_notification_body(event_label: str, patient_name: str, service_summary: str, start: datetime) -> str:
    return f"{event_label}: {patient_name} — {service_summary} on {_format_when(start)}."


EMAIL_SUBJECTS = {
    "appointment_confirmation": "Your appointment is confirmed",
    "appointment_cancellation": "Your appointment has been cancelled",
    "appointment_reschedule": "Your appointment has been rescheduled",
    "appointment_reminder": "Appointment reminder",
}

CLINIC_EVENT_LABELS = {
    "appointment_confirmation": "New appointment booked",
    "appointment_cancellation": "Appointment cancelled",
    "appointment_reschedule": "Appointment rescheduled",
    "appointment_reminder": "Appointment reminder",
}

# -- day-of reminders (English / Urdu only) -----------------------------------

_REMINDER_EMAIL_SUBJECTS = {
    "en": "Appointment reminder",
    "ur": "اپائنٹمنٹ یاد دہانی",
}


def reminder_email_subject(language: str) -> str:
    return _REMINDER_EMAIL_SUBJECTS[normalize_notification_language(language)]


def patient_reminder_body(language: str, doctor_name: str, clinic_name: str, start: datetime) -> str:
    """Patient-facing day-of reminder. `doctor_name` should already be a
    plain name (no "Dr." prefix); `clinic_name` the workspace name. All
    values are interpolated from live appointment data by the caller."""
    lang = normalize_notification_language(language)
    time_str = _format_time(start)
    if lang == "ur":
        return (
            f"یاد دہانی: ڈاکٹر {doctor_name} کے ساتھ {clinic_name} میں آپ کی اپائنٹمنٹ "
            f"آج {time_str} بجے طے ہے۔"
        )
    return (
        f"Reminder: Your appointment with Dr. {doctor_name} at {clinic_name} is "
        f"scheduled for today at {time_str}."
    )


def doctor_reminder_body(language: str, patient_name: str, start: datetime) -> str:
    """Doctor-facing day-of reminder."""
    lang = normalize_notification_language(language)
    time_str = _format_time(start)
    if lang == "ur":
        return f"یاد دہانی: آج {time_str} بجے آپ کی {patient_name} کے ساتھ اپائنٹمنٹ ہے۔"
    return f"Reminder: You have an appointment with {patient_name} today at {time_str}."
