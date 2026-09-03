"""Phone-number helpers shared by the management API and Vapi call routing.

Both paths need one thing: turn whatever string arrived into a canonical
E.164 form so a stored number and an inbound dialed number compare equal.
"""

from phonenumbers import PhoneNumberFormat, format_number, is_possible_number, parse


def normalize_e164(raw: str | None) -> str | None:
    """Return `raw` as an E.164 string (``+<countrycode><number>``), or None.

    Returns None when the input is empty, cannot be parsed, or is not a
    possible number. The input must carry its country code (a leading ``+``)
    — there is no default region — so both a clinic saving its line and Vapi
    reporting a dialed number describe the same digits the same way.
    """
    if not raw or not raw.strip():
        return None
    try:
        parsed = parse(raw.strip(), None)
    except Exception:
        return None
    if not is_possible_number(parsed):
        return None
    return format_number(parsed, PhoneNumberFormat.E164)
