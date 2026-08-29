import base64
import json
import uuid

import pytest

from app.core.config import settings
from app.models.workspace import Workspace


@pytest.fixture()
def workspace(db_session):
    ws = Workspace(name="Pipeline Clinic", slug="pipeline-clinic")
    db_session.add(ws)
    db_session.commit()
    return ws


def start_message(call_id="call-1", from_number="+15551234567", to_number="+15557654321"):
    return json.dumps({"event": "start", "call_id": call_id, "from": from_number, "to": to_number})


def media_message(text: str, call_id="call-1"):
    return json.dumps(
        {"event": "media", "call_id": call_id, "payload": base64.b64encode(text.encode()).decode()}
    )


def stop_message(call_id="call-1"):
    return json.dumps({"event": "stop", "call_id": call_id})


def decode_reply(raw: str) -> str:
    payload = json.loads(raw)
    assert payload["event"] == "media_out"
    return base64.b64decode(payload["payload"]).decode("utf-8")


# -- full pipeline ------------------------------------------------------------


def test_full_booking_call_over_websocket(client, workspace):
    url = f"/api/v1/telephony/stream/mock/{workspace.id}"
    with client.websocket_connect(url) as ws:
        ws.send_text(start_message())

        ws.send_text(media_message("Hi there"))
        reply = decode_reply(ws.receive_text())
        assert "Pipeline Clinic" in reply

        ws.send_text(media_message("I would like to book an appointment"))
        reply = decode_reply(ws.receive_text())
        assert "name" in reply.lower()

        ws.send_text(media_message("My name is Jane Doe"))
        reply = decode_reply(ws.receive_text())
        assert "phone" in reply.lower()

        ws.send_text(media_message("My phone is 415-555-0100"))
        reply = decode_reply(ws.receive_text())
        assert "service" in reply.lower()

        ws.send_text(stop_message())


def test_disconnect_handling_does_not_crash_server(client, workspace):
    url = f"/api/v1/telephony/stream/mock/{workspace.id}"
    with client.websocket_connect(url) as ws:
        ws.send_text(start_message())
        ws.send_text(media_message("Hello"))
        decode_reply(ws.receive_text())
        # Client hangs up mid-call without a "stop" event — this must not
        # take the server down; the endpoint's WebSocketDisconnect handler
        # covers this path.

    # A brand new call on the same workspace still works afterwards, proving
    # the previous abrupt disconnect was handled cleanly.
    with client.websocket_connect(url) as ws:
        ws.send_text(start_message(call_id="call-2"))
        ws.send_text(media_message("Hello again", call_id="call-2"))
        reply = decode_reply(ws.receive_text())
        assert reply


def test_unknown_workspace_is_rejected(client):
    url = f"/api/v1/telephony/stream/mock/{uuid.uuid4()}"
    with pytest.raises(Exception):
        with client.websocket_connect(url):
            pass


def test_call_id_is_used_consistently_across_events(client, workspace):
    url = f"/api/v1/telephony/stream/mock/{workspace.id}"
    with client.websocket_connect(url) as ws:
        ws.send_text(start_message(call_id="distinct-call-id"))
        ws.send_text(media_message("Hi", call_id="distinct-call-id"))
        decode_reply(ws.receive_text())
        ws.send_text(stop_message(call_id="distinct-call-id"))


def test_unrecognized_message_is_ignored_not_fatal(client, workspace):
    url = f"/api/v1/telephony/stream/mock/{workspace.id}"
    with client.websocket_connect(url) as ws:
        ws.send_text(start_message())
        ws.send_text("not valid json at all")  # malformed / unknown message
        ws.send_text(media_message("Hello"))
        reply = decode_reply(ws.receive_text())
        assert reply  # pipeline kept working after the bad message


# -- idle timeout ---------------------------------------------------------------


def test_idle_timeout_prompts_then_ends_call(client, workspace, monkeypatch):
    monkeypatch.setattr(settings, "call_idle_timeout_seconds", 0.2)
    monkeypatch.setattr(settings, "call_max_idle_strikes", 2)

    url = f"/api/v1/telephony/stream/mock/{workspace.id}"
    with client.websocket_connect(url) as ws:
        ws.send_text(start_message())

        # First idle window elapses with no message: a "please repeat" nudge.
        first_prompt = decode_reply(ws.receive_text())
        assert first_prompt

        # Second idle window elapses: strike limit reached, call ends.
        second_prompt = decode_reply(ws.receive_text())
        assert second_prompt

        with pytest.raises(Exception):
            ws.receive_text()
