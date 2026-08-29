import uuid
from datetime import datetime

from pydantic import BaseModel


class AnalyticsSummaryOut(BaseModel):
    workspace_id: uuid.UUID
    since: datetime | None
    until: datetime | None

    total_calls: int
    answered_calls: int
    average_duration_seconds: float | None
    qualified_leads: int
    total_leads: int
    appointments: int
    conversion_rate: float | None
    ai_resolution_rate: float | None
    receptionist_transfers: int
    integration_failures: int
    integration_attempts: int

    model_config = {"from_attributes": True}
