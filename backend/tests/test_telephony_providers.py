import base64
import hashlib
import hmac
import json

from app.core.config import Settings
from app.telephony.events import AudioChunk, CallEnded, CallStarted, UnknownEvent
from app.telephony.providers.factory import get_telephony_adapter
from app.telephony.providers.twilio_adapter import TwilioAdapter, build_stream_twiml
from app.telephony.providers.vapi_adapter import VapiAdapter


# -- Twilio ---------------------------------------------------------------------


def test_twilio_parses_start_event_with_custom_params():
    adapter = TwilioAdapter("ACxxx", "authtoken")
    message = json.dumps(
        {
            "event": "start",
            "start": {
                "streamSid": "MZ123",
                "callSid": "CA456",
                "mediaFormat": {"encoding": "audio/x-mulaw", "sampleRate": 8000, "channels": 1},
                "customParameters": {"From": "+15551234567", "To": "+15557654321"},
            },
            "streamSid": "MZ123",
        }
    )
    event = adapter.parse_message(message)
    assert isinstance(event, CallStarted)
    assert event.call_id == "MZ123"
    assert event.from_number == "+15551234567"
    assert event.to_number == "+15557654321"
    assert event.sample_rate == 8000


def test_twilio_parses_media_event():
    adapter = TwilioAdapter("ACxxx", "authtoken")
    raw_audio = b"\x01\x02\x03\x04"
    message = json.dumps(
        {"event": "media", "streamSid": "MZ123", "media": {"payload": base64.b64encode(raw_audio).decode()}}
    )
    event = adapter.parse_message(message)
    assert isinstance(event, AudioChunk)
    assert event.call_id == "MZ123"
    assert event.payload == raw_audio


def test_twilio_parses_stop_event():
    adapter = TwilioAdapter("ACxxx", "authtoken")
    event = adapter.parse_message(json.dumps({"event": "stop", "streamSid": "MZ123"}))
    assert isinstance(event, CallEnded)
    assert event.call_id == "MZ123"


def test_twilio_unrecognized_message_is_unknown_event():
    adapter = TwilioAdapter("ACxxx", "authtoken")
    assert isinstance(adapter.parse_message(json.dumps({"event": "connected"})), UnknownEvent)
    assert isinstance(adapter.parse_message("not json"), UnknownEvent)


def test_twilio_encode_audio_message_round_trips():
    adapter = TwilioAdapter("ACxxx", "authtoken")
    encoded = adapter.encode_audio_message("MZ123", b"\x05\x06")
    payload = json.loads(encoded)
    assert payload["event"] == "media"
    assert payload["streamSid"] == "MZ123"
    assert base64.b64decode(payload["media"]["payload"]) == b"\x05\x06"


def test_twilio_signature_validation():
    adapter = TwilioAdapter("ACxxx", "authtoken")
    url = "https://example.com/voice"
    params = {"CallSid": "CA456", "From": "+15551234567"}
    data = url + "".join(k + params[k] for k in sorted(params))
    valid_sig = base64.b64encode(hmac.new(b"authtoken", data.encode(), hashlib.sha1).digest()).decode()

    assert adapter.verify_webhook_signature(url, params, valid_sig) is True
    assert adapter.verify_webhook_signature(url, params, "tampered-signature") is False


def test_twilio_signature_validation_without_auth_token_fails_closed():
    adapter = TwilioAdapter("ACxxx", "")
    assert adapter.verify_webhook_signature("https://example.com", {}, "anything") is False


def test_build_stream_twiml_contains_stream_url_and_params():
    twiml = build_stream_twiml("wss://example.com/stream", "+15551234567", "+15557654321")
    assert "<Stream url=\"wss://example.com/stream\">" in twiml
    assert 'name="From" value="+15551234567"' in twiml
    assert 'name="To" value="+15557654321"' in twiml


def test_twilio_unavailable_without_credentials():
    assert TwilioAdapter("", "").is_available() is False
    assert TwilioAdapter("ACxxx", "authtoken").is_available() is True


# -- Vapi -------------------------------------------------------------------------


def test_vapi_parses_start_media_end():
    adapter = VapiAdapter("vapi-key")

    start = adapter.parse_message(
        json.dumps(
            {
                "type": "start",
                "call": {"id": "call-1", "customer": {"number": "+15551234567"}, "phoneNumber": {"number": "+15557654321"}},
            }
        )
    )
    assert isinstance(start, CallStarted)
    assert start.call_id == "call-1"
    assert start.from_number == "+15551234567"

    media = adapter.parse_message(
        json.dumps({"type": "media", "callId": "call-1", "payload": base64.b64encode(b"abc").decode()})
    )
    assert isinstance(media, AudioChunk)
    assert media.payload == b"abc"

    end = adapter.parse_message(json.dumps({"type": "end", "callId": "call-1"}))
    assert isinstance(end, CallEnded)


def test_vapi_unavailable_without_api_key():
    assert VapiAdapter("").is_available() is False
    assert VapiAdapter("key").is_available() is True


# -- factory / mock fallback --------------------------------------------------------


def test_factory_defaults_to_mock():
    adapter = get_telephony_adapter(cfg=Settings(_env_file=None, telephony_provider="mock"))
    assert adapter.name == "mock"


def test_factory_falls_back_to_mock_without_twilio_credentials():
    cfg = Settings(_env_file=None, telephony_provider="twilio", twilio_account_sid="", twilio_auth_token="")
    adapter = get_telephony_adapter(cfg=cfg)
    assert adapter.name == "mock"


def test_factory_falls_back_to_mock_without_vapi_credentials():
    cfg = Settings(_env_file=None, telephony_provider="vapi", vapi_api_key="")
    adapter = get_telephony_adapter(cfg=cfg)
    assert adapter.name == "mock"


def test_factory_uses_twilio_when_credentials_present():
    cfg = Settings(
        _env_file=None, telephony_provider="twilio", twilio_account_sid="ACxxx", twilio_auth_token="token"
    )
    adapter = get_telephony_adapter(cfg=cfg)
    assert adapter.name == "twilio"
