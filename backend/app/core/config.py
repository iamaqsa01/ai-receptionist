from functools import lru_cache
from typing import List

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Environments where insecure defaults (the dev-only SECRET_KEY fallback,
# permissive debug behavior) are tolerated. Anything else is treated as
# "production-like" for the checks in Settings.model_post_init below.
_NON_PRODUCTION_ENVS = {"development", "dev", "test", "testing", "local"}

DEV_ONLY_SECRET_KEY = "dev-only-insecure-secret-change-me"


class Settings(BaseSettings):
    app_name: str = "AI Receptionist"
    app_env: str = "development"
    # False by default (secure-by-default): a deployment that forgets to
    # set this explicitly should not accidentally run in a more permissive
    # mode. Local dev sets DEBUG=true via .env.example.
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    host: str = "0.0.0.0"
    port: int = 8000

    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    log_level: str = "INFO"
    # "json" (default — structured, one object per line, machine-parseable)
    # or "text" (human-readable, for local dev tailing).
    log_format: str = "json"

    # Database (PostgreSQL). Prefer DATABASE_URL when set; otherwise it is
    # assembled from the discrete POSTGRES_* fields below. No credentials are
    # hardcoded — everything comes from the environment / .env file.
    database_url: str = ""
    postgres_user: str = "postgres"
    postgres_password: str = ""
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "ai_receptionist"

    db_echo: bool = False
    db_pool_size: int = 5
    db_max_overflow: int = 10

    # Auth. SECRET_KEY has a dev-only fallback so the app boots without
    # configuration in local dev; production deployments MUST override it via
    # the environment — never commit a real secret here. Enforced below
    # (model_post_init): the app refuses to start with this fallback value
    # outside a development/test APP_ENV.
    secret_key: str = DEV_ONLY_SECRET_KEY
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # AI Receptionist / LLM. llm_provider selects which provider to use;
    # if the matching API key is missing, the factory falls back to the
    # mock provider automatically (no credentials required to run/test).
    llm_provider: str = "mock"  # "mock" | "openai" | "anthropic"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-5-haiku-latest"

    # Multilingual defaults. A workspace can override its own supported
    # language list via ai_agents.config; this is the fallback. Codes:
    # en=English, ur=Urdu, pa=Punjabi (Shahmukhi), skr=Saraiki, sd=Sindhi,
    # ps=Pashto (es/fr/de remain registered in the catalog for existing
    # deployments but are no longer in the default set).
    default_supported_languages: str = "en,ur,pa,skr,sd,ps"
    language_detection_min_confidence: float = 0.5

    # Appointment reminder / notification language. Regardless of the
    # language a call was conducted in, appointment reminders and
    # confirmations are only ever generated in English or Urdu. A workspace
    # can override this per-tenant via its clinic_notifications integration
    # config ("notification_language"); this is the fallback. Only "en" and
    # "ur" are honoured.
    notification_default_language: str = "en"

    # Day-of reminder background job (app/jobs/reminders.py). The job wakes
    # hourly and, for each workspace, sends that day's reminders when the
    # local clock reaches `reminder_local_hour`. Disabled automatically
    # under a test APP_ENV.
    reminders_enabled: bool = True
    reminder_local_hour: int = 8

    # Telephony / real-time voice pipeline. Each provider falls back to a
    # mock adapter automatically when its credentials are missing, same
    # pattern as llm_provider above.
    telephony_provider: str = "mock"  # "mock" | "twilio" | "vapi"
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    vapi_api_key: str = ""
    # Inbound custom-tool authentication. This is intentionally distinct
    # from VAPI_API_KEY, which authorizes outbound calls to Vapi's API.
    vapi_tool_webhook_secret: str = ""
    # The caller hears the slots, then gives a name, a phone number and a
    # reason. Five minutes routinely expired mid-conversation, so the
    # booking failed on a token that had been valid when it was issued.
    vapi_availability_token_expire_seconds: int = 1800
    # Country a patient's phone number is read against when they give it
    # without a country code, which on a domestic line is almost always.
    # Two-letter ISO code; blank requires every number to carry its own
    # country code. Only ever a fallback: an explicit +code always wins,
    # and the caller's own number is tried before this.
    default_phone_region: str = "PK"

    stt_provider: str = "mock"  # "mock" | "deepgram"
    deepgram_api_key: str = ""
    deepgram_model: str = "nova-2"

    tts_provider: str = "mock"  # "mock" | "elevenlabs"
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = "21m00Tcm4TlvDq8ikWAM"  # ElevenLabs' public default demo voice

    # Idle-audio watchdog: if no inbound audio arrives for this long, the
    # caller is gently prompted; after call_max_idle_strikes consecutive
    # timeouts, the call is ended.
    call_idle_timeout_seconds: float = 8.0
    call_max_idle_strikes: int = 3

    # Calendar integration. Server-level service-account credentials (one
    # Google Cloud project for the whole deployment); which specific
    # calendar a workspace syncs to is workspace-level config (an
    # `integrations` row, provider="google_calendar", config.calendar_id) —
    # same split as the rest of this project's provider settings.
    calendar_provider: str = "mock"  # "mock" | "google"
    google_service_account_json: str = ""  # raw JSON string, not a file path
    google_calendar_timeout_seconds: float = 10.0
    # Per-workspace Google OAuth (SaaS clinic connections). OAuth tokens are
    # encrypted at rest with a key derived from SECRET_KEY; the redirect URI
    # must exactly match the Google Cloud Console OAuth client configuration.
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = ""

    # WhatsApp / email notifications (Phase 9). Each falls back to a mock
    # adapter automatically when its credentials are missing, same pattern
    # as every other provider in this project.
    whatsapp_provider: str = "mock"  # "mock" | "twilio" | "meta"
    whatsapp_from_number: str = ""  # Twilio WhatsApp-enabled sender, e.g. "+14155238886"
    meta_whatsapp_access_token: str = ""
    meta_whatsapp_phone_number_id: str = ""
    # Pre-approved WhatsApp template names, one per patient-facing event.
    # Blank means send free-form text, which only reaches a patient who
    # messaged the clinic on WhatsApp within the last 24 hours -- almost
    # never true of someone who telephoned. Each template must take three
    # body parameters in this order: patient name, service, when.
    meta_whatsapp_template_confirmation: str = ""
    meta_whatsapp_template_cancellation: str = ""
    meta_whatsapp_template_reschedule: str = ""
    meta_whatsapp_template_language: str = "en"

    email_provider: str = "mock"  # "mock" | "sendgrid"
    sendgrid_api_key: str = ""
    email_from_address: str = "noreply@example.com"

    notification_timeout_seconds: float = 10.0

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def is_production_like(self) -> bool:
        return self.app_env.lower().strip() not in _NON_PRODUCTION_ENVS

    @model_validator(mode="after")
    def _refuse_insecure_defaults_outside_development(self) -> "Settings":
        """Fails loudly at startup rather than silently running an
        exploitable configuration: a JWT secret every reader of this
        (eventually open-source-able) codebase already knows is not a
        secret at all, or debug mode's more detailed error surfaces, left
        on by an operator who forgot to configure the environment."""
        if self.is_production_like and self.secret_key == DEV_ONLY_SECRET_KEY:
            raise ValueError(
                f"SECRET_KEY must be set to a real secret when APP_ENV={self.app_env!r}. "
                "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(48))\""
            )
        return self

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def sqlalchemy_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def default_supported_languages_list(self) -> List[str]:
        return [lang.strip() for lang in self.default_supported_languages.split(",") if lang.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
