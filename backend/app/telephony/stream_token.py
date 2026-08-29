"""Short-lived, signed tokens that gate the Twilio Media Stream WebSocket
endpoint (app.api.telephony: telephony_stream).

Why this exists: the voice webhook (POST .../voice) now verifies Twilio's
own X-Twilio-Signature before minting a stream URL (see app.api.telephony),
but the WebSocket endpoint that URL points to has no equivalent way to
verify a Media Streams *connection* the same way (Twilio doesn't sign the
WS handshake the same way it signs the HTTP webhook). Without this token,
anyone who learned or guessed a workspace_id could connect to the stream
endpoint directly — bypassing the signature check entirely — and interact
with the AI Receptionist as if they were a real caller (cost abuse, prompt
injection). Minting the token only after the signature check passes closes
that gap for the one real, internet-facing provider (Twilio); the mock
adapter (used by the test suite and local/dev tooling, never reachable by
a real caller) is intentionally left as-is.
"""

import hashlib
import hmac
import time
import uuid

from app.core.config import settings

_TOKEN_TTL_SECONDS = 300  # long enough for Twilio to open the stream promptly after the webhook response


def create_stream_token(workspace_id: uuid.UUID) -> str:
    expires_at = int(time.time()) + _TOKEN_TTL_SECONDS
    return f"{expires_at}.{_sign(workspace_id, expires_at)}"


def verify_stream_token(token: str, workspace_id: uuid.UUID) -> bool:
    if not token or "." not in token:
        return False
    expires_at_raw, _, signature = token.partition(".")
    try:
        expires_at = int(expires_at_raw)
    except ValueError:
        return False
    if expires_at < int(time.time()):
        return False
    return hmac.compare_digest(_sign(workspace_id, expires_at), signature)


def _sign(workspace_id: uuid.UUID, expires_at: int) -> str:
    payload = f"{workspace_id}:{expires_at}"
    return hmac.new(settings.secret_key.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
