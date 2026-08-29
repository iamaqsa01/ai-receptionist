import uuid

import pytest

from app.models.workspace import Workspace


@pytest.fixture()
def workspace(db_session):
    ws = Workspace(name="Webhook Clinic", slug="webhook-clinic")
    db_session.add(ws)
    db_session.commit()
    return ws


def test_twilio_voice_webhook_returns_twiml_with_stream_url(client, workspace):
    resp = client.post(
        f"/api/v1/telephony/twilio/{workspace.id}/voice",
        data={"From": "+15551234567", "To": "+15557654321", "CallSid": "CA123"},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/xml")
    body = resp.text
    assert "<Connect>" in body
    assert f"/telephony/stream/twilio/{workspace.id}" in body
    assert 'name="From" value="+15551234567"' in body


def test_twilio_voice_webhook_unknown_workspace_returns_404(client):
    resp = client.post(
        f"/api/v1/telephony/twilio/{uuid.uuid4()}/voice",
        data={"From": "+15551234567", "To": "+15557654321"},
    )
    assert resp.status_code == 404
