from enum import Enum


class BookingOutcome(str, Enum):
    """What actually happened when the backend tried to write an
    appointment change to the database — this, and only this, is what
    ConversationEngine is allowed to base a "confirmed"/"cancelled"/
    "rescheduled" reply on. The engine never speaks success before
    receptionist_service reports one of these back."""

    CREATED = "created"
    CONFLICT = "conflict"  # the provider is already booked at that time
    DUPLICATE = "duplicate"  # this same caller already has an overlapping appointment

    CANCELLED = "cancelled"
    NOT_FOUND = "not_found"  # no matching appointment to cancel/reschedule

    RESCHEDULED = "rescheduled"
    RESCHEDULE_CONFLICT = "reschedule_conflict"
