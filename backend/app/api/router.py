from fastapi import APIRouter

from app.api import (
    ai,
    analytics,
    appointments,
    auth,
    calls,
    health,
    human_handoffs,
    leads,
    notifications,
    patients,
    providers,
    services,
    telephony,
    vapi_tools,
    workspaces,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(workspaces.router)
api_router.include_router(patients.router)
api_router.include_router(leads.router)
api_router.include_router(services.router)
api_router.include_router(providers.router)
api_router.include_router(appointments.router)
api_router.include_router(calls.router)
api_router.include_router(ai.router)
api_router.include_router(telephony.router)
api_router.include_router(vapi_tools.router)
api_router.include_router(notifications.router)
api_router.include_router(human_handoffs.router)
api_router.include_router(analytics.router)
