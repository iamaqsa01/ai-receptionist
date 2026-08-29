"""Phase 10 — human Receptionist escalation, at the ReceptionistService
layer: every TransferToHumanEffect (whatever triggered it) is recorded as a
HumanHandoff row in PostgreSQL — reason, trigger, timestamp, conversation
context, and call state — before any live telephony transfer is even
attempted. Live transfer itself (Twilio/Vapi) is exercised via
MockTelephonyAdapter, which records every attempted transfer_call() in
memory."""

import uuid

import pytest
from sqlalchemy import select

from app.ai.conversation.store import InMemoryConversationStore
from app.ai.llm.mock_provider import MockLLMProvider
from app.ai.receptionist_service import ReceptionistService
from app.models.ai_agent import AIAgent
from app.models.human_handoff import HumanHandoff
from app.models.notification import Notification
from app.models.service import Service
from app.models.workspace import Workspace
from app.telephony.providers.mock_adapter import MockTelephonyAdapter


@pytest.fixture()
def workspace(db_session):
    ws = Workspace(name="Sunrise Dental", slug="sunrise-dental-handoff")
    db_session.add(ws)
    db_session.flush()
    db_session.add(Service(workspace_id=ws.id, name="Cleaning", is_active=True))
    db_session.add(
        AIAgent(
            workspace_id=ws.id,
            name="Front Desk AI",
            is_active=True,
            config={"instructions": "Be concise.", "supported_languages": ["en"]},
        )
    )
    db_session.commit()
    return ws


@pytest.fixture()
def workspace_with_transfer_number(db_session):
    ws = Workspace(name="Sunrise Dental 2", slug="sunrise-dental-handoff-2")
    db_session.add(ws)
    db_session.flush()
    db_session.add(Service(workspace_id=ws.id, name="Cleaning", is_active=True))
    db_session.add(
        AIAgent(
            workspace_id=ws.id,
            name="Front Desk AI",
            is_active=True,
            config={
                "instructions": "Be concise.",
                "supported_languages": ["en"],
                "human_transfer_number": "+15559990000",
            },
        )
    )
    db_session.commit()
    return ws


@pytest.fixture()
def service(db_session):
    return ReceptionistService(db=db_session, llm=MockLLMProvider(), store=InMemoryConversationStore())


def run_turns(service, workspace_id, session_id, turns, **kwargs):
    result = None
    for turn in turns:
        result = service.handle_message(workspace_id, session_id, turn, **kwargs)
    return result


# -- caller request --------------------------------------------------------------


def test_caller_request_transfer_is_recorded_in_postgres(db_session, workspace, service):
    state = service.start_session(workspace.id)
    run_turns(service, workspace.id, state.session_id, ["Hi", "Can I speak to a human please"])

    handoff = db_session.execute(
        select(HumanHandoff).where(HumanHandoff.workspace_id == workspace.id)
    ).scalar_one()
    assert handoff.trigger == "caller_request"
    assert handoff.reason
    assert handoff.created_at is not None  # the "timestamp" requirement
    assert handoff.conversation_session_id == state.session_id
    assert handoff.status == "pending"  # no telephony_adapter passed -> no live transfer attempted


def test_conversation_context_and_call_state_are_saved_before_transfer(db_session, workspace, service):
    state = service.start_session(workspace.id)
    run_turns(
        service,
        workspace.id,
        state.session_id,
        ["Hi", "My name is Jane Doe", "My phone is 415-555-0100", "Can I speak to a human please"],
    )

    handoff = db_session.execute(
        select(HumanHandoff).where(HumanHandoff.workspace_id == workspace.id)
    ).scalar_one()

    # Conversation context: every turn spoken so far, in order.
    assert len(handoff.conversation_context) >= 8  # 4 caller turns + 4 assistant replies
    assert handoff.conversation_context[0]["role"] == "caller"
    assert handoff.conversation_context[0]["text"] == "Hi"
    assert all("timestamp" in turn for turn in handoff.conversation_context)

    # Call state: a snapshot of what the AI Receptionist knew at the moment of transfer.
    assert handoff.call_state["caller_name"] == "Jane Doe"
    assert handoff.call_state["caller_phone"] == "+14155550100"
    assert handoff.call_state["status"] == "needs_human"
    assert handoff.call_state["session_id"] == str(state.session_id)


def test_staff_notification_is_also_raised(db_session, workspace, service):
    state = service.start_session(workspace.id)
    run_turns(service, workspace.id, state.session_id, ["Hi", "Can I speak to a human please"])

    notification = db_session.execute(
        select(Notification).where(Notification.workspace_id == workspace.id, Notification.type == "ai_handoff")
    ).scalar_one()
    assert notification.title


# -- the other four triggers -------------------------------------------------------


def test_unsupported_request_is_recorded_with_correct_trigger(db_session, workspace, service):
    state = service.start_session(workspace.id)
    run_turns(service, workspace.id, state.session_id, ["Hi", "I have a billing question about an invoice"])

    handoff = db_session.execute(
        select(HumanHandoff).where(HumanHandoff.workspace_id == workspace.id)
    ).scalar_one()
    assert handoff.trigger == "unsupported_request"


def test_repeated_misunderstanding_is_recorded_with_correct_trigger(db_session, workspace, service):
    state = service.start_session(workspace.id)
    run_turns(
        service,
        workspace.id,
        state.session_id,
        ["Hi", "asdkfj qwoeiru random one", "another confusing thing zzz", "still not making sense blah"],
    )

    handoff = db_session.execute(
        select(HumanHandoff).where(HumanHandoff.workspace_id == workspace.id)
    ).scalar_one()
    assert handoff.trigger == "repeated_misunderstanding"


def test_clinic_rule_is_recorded_with_correct_trigger(db_session):
    ws = Workspace(name="Rule Clinic", slug="rule-clinic")
    db_session.add(ws)
    db_session.flush()
    db_session.add(Service(workspace_id=ws.id, name="Cleaning", is_active=True))
    db_session.add(
        AIAgent(
            workspace_id=ws.id,
            name="AI",
            is_active=True,
            config={"supported_languages": ["en"], "escalation_keywords": ["emergency"]},
        )
    )
    db_session.commit()

    service = ReceptionistService(db=db_session, llm=MockLLMProvider(), store=InMemoryConversationStore())
    state = service.start_session(ws.id)
    run_turns(service, ws.id, state.session_id, ["Hi", "This is an emergency, please help"])

    handoff = db_session.execute(select(HumanHandoff).where(HumanHandoff.workspace_id == ws.id)).scalar_one()
    assert handoff.trigger == "clinic_rule"


def test_technical_failure_is_recorded_and_caller_still_gets_a_reply(db_session, workspace, service, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("simulated internal engine bug")

    monkeypatch.setattr(service.engine, "handle_message", boom)

    state = service.start_session(workspace.id)
    result = service.handle_message(workspace.id, state.session_id, "Hi")

    assert result.reply  # caller still gets a spoken reply, never a raised exception
    assert result.state.status.value == "needs_human"

    handoff = db_session.execute(
        select(HumanHandoff).where(HumanHandoff.workspace_id == workspace.id)
    ).scalar_one()
    assert handoff.trigger == "technical_failure"


# -- live telephony transfer integration --------------------------------------------


def test_live_transfer_is_attempted_and_recorded_when_adapter_and_number_are_available(
    db_session, workspace_with_transfer_number
):
    adapter = MockTelephonyAdapter()
    service = ReceptionistService(db=db_session, llm=MockLLMProvider(), store=InMemoryConversationStore())
    state = service.start_session(workspace_with_transfer_number.id)

    run_turns(
        service,
        workspace_with_transfer_number.id,
        state.session_id,
        ["Hi", "Can I speak to a human please"],
        telephony_adapter=adapter,
        provider_call_id="CA123",
    )

    assert adapter.transfers == [{"provider_call_id": "CA123", "target_number": "+15559990000"}]

    handoff = db_session.execute(
        select(HumanHandoff).where(HumanHandoff.workspace_id == workspace_with_transfer_number.id)
    ).scalar_one()
    assert handoff.status == "transferred"
    assert handoff.transfer_target == "+15559990000"
    assert handoff.transferred_at is not None


def test_no_live_transfer_attempted_without_a_configured_number(db_session, workspace):
    """workspace fixture has no human_transfer_number configured — even
    with a live telephony adapter available, no transfer is attempted, but
    the handoff is still recorded (status stays "pending")."""
    adapter = MockTelephonyAdapter()
    service = ReceptionistService(db=db_session, llm=MockLLMProvider(), store=InMemoryConversationStore())
    state = service.start_session(workspace.id)

    run_turns(
        service,
        workspace.id,
        state.session_id,
        ["Hi", "Can I speak to a human please"],
        telephony_adapter=adapter,
        provider_call_id="CA123",
    )

    assert adapter.transfers == []
    handoff = db_session.execute(
        select(HumanHandoff).where(HumanHandoff.workspace_id == workspace.id)
    ).scalar_one()
    assert handoff.status == "pending"
