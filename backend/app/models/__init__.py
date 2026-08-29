"""Import every model so they register on Base.metadata (needed for Alembic
autogenerate and for metadata.create_all in tests)."""

from app.database.base import Base
from app.models.user import User
from app.models.auth_session import AuthSession
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from app.models.patient import Patient
from app.models.lead import Lead
from app.models.provider import Provider
from app.models.service import Service
from app.models.business_hours import BusinessHours
from app.models.ai_agent import AIAgent
from app.models.call import Call
from app.models.call_transcript import CallTranscript
from app.models.call_summary import CallSummary
from app.models.appointment import Appointment
from app.models.integration import Integration
from app.models.notification import Notification
from app.models.notification_message import NotificationMessage
from app.models.human_handoff import HumanHandoff
from app.models.integration_log import IntegrationLog
from app.models.audit_log import AuditLog

__all__ = [
    "Base",
    "User",
    "AuthSession",
    "Workspace",
    "WorkspaceMember",
    "Patient",
    "Lead",
    "Provider",
    "Service",
    "BusinessHours",
    "AIAgent",
    "Call",
    "CallTranscript",
    "CallSummary",
    "Appointment",
    "Integration",
    "Notification",
    "NotificationMessage",
    "HumanHandoff",
    "IntegrationLog",
    "AuditLog",
]
