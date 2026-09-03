import inspect
import uuid

from app.core.config import Settings
from app.database.session import get_db
from app.models import (
    AIAgent,
    Appointment,
    AuditLog,
    Base,
    BusinessHours,
    Call,
    CallSummary,
    CallTranscript,
    HumanHandoff,
    Integration,
    IntegrationLog,
    Lead,
    Notification,
    NotificationMessage,
    Patient,
    PhoneNumber,
    Provider,
    Service,
    User,
    Workspace,
    WorkspaceMember,
)

EXPECTED_TABLES = {
    "users",
    "auth_sessions",
    "workspaces",
    "workspace_members",
    "phone_numbers",
    "patients",
    "leads",
    "calls",
    "call_transcripts",
    "call_summaries",
    "appointments",
    "providers",
    "services",
    "business_hours",
    "ai_agents",
    "integrations",
    "notifications",
    "notification_messages",
    "human_handoffs",
    "integration_logs",
    "audit_logs",
}

TENANT_OWNED_MODELS = [
    WorkspaceMember,
    PhoneNumber,
    Patient,
    Lead,
    Provider,
    Service,
    BusinessHours,
    AIAgent,
    Call,
    CallTranscript,
    CallSummary,
    Appointment,
    Integration,
    Notification,
    NotificationMessage,
    HumanHandoff,
    IntegrationLog,
]


def test_all_expected_tables_registered() -> None:
    assert set(Base.metadata.tables.keys()) == EXPECTED_TABLES


def test_database_url_assembled_from_discrete_settings_without_hardcoded_creds() -> None:
    settings = Settings(
        _env_file=None,
        database_url="",
        postgres_user="alice",
        postgres_password="s3cret",
        postgres_host="db.internal",
        postgres_port=5433,
        postgres_db="ai_receptionist_test",
    )
    url = settings.sqlalchemy_database_url
    assert url == "postgresql+psycopg2://alice:s3cret@db.internal:5433/ai_receptionist_test"


def test_explicit_database_url_takes_precedence() -> None:
    settings = Settings(_env_file=None, database_url="postgresql+psycopg2://x:y@z/db")
    assert settings.sqlalchemy_database_url == "postgresql+psycopg2://x:y@z/db"


def test_get_db_is_a_generator_dependency() -> None:
    assert inspect.isgeneratorfunction(get_db)


def test_primary_keys_are_uuid() -> None:
    for model in [User, Workspace, *TENANT_OWNED_MODELS, AuditLog]:
        col = model.__table__.c.id
        assert col.primary_key
        assert col.default.is_callable
        assert col.default.arg.__name__ == uuid.uuid4.__name__


def test_tenant_owned_models_have_indexed_workspace_id_fk() -> None:
    for model in TENANT_OWNED_MODELS:
        col = model.__table__.c.workspace_id
        assert col.index is True
        assert col.nullable is False
        fk = next(iter(col.foreign_keys))
        assert fk.target_fullname == "workspaces.id"


def test_audit_log_workspace_id_is_nullable_for_system_events() -> None:
    col = AuditLog.__table__.c.workspace_id
    assert col.nullable is True


def test_call_summary_call_id_is_unique() -> None:
    col = CallSummary.__table__.c.call_id
    assert col.unique is True


def test_workspace_member_unique_constraint() -> None:
    constraint_names = {c.name for c in WorkspaceMember.__table__.constraints}
    assert "uq_workspace_members_workspace_user" in constraint_names


def test_all_tenant_tables_and_users_have_timestamps() -> None:
    for model in [User, Workspace, *TENANT_OWNED_MODELS]:
        columns = model.__table__.c
        assert "created_at" in columns
        assert "updated_at" in columns

    # audit_logs is append-only: created_at only, no updated_at
    audit_columns = AuditLog.__table__.c
    assert "created_at" in audit_columns
    assert "updated_at" not in audit_columns
