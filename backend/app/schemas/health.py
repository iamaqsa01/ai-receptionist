from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    app_name: str
    app_env: str
    version: str


class ReadinessCheck(BaseModel):
    name: str
    status: str  # "ok" | "error"
    detail: str | None = None


class ReadinessResponse(BaseModel):
    status: str  # "ok" | "error" — "ok" only if every check is "ok"
    checks: list[ReadinessCheck]
