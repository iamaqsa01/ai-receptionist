from fastapi import APIRouter

router = APIRouter(tags=["root"])


@router.get("/")
async def read_root() -> dict:
    return {
        "message": "AI Receptionist API",
        "docs": "/docs",
        "health": "/api/v1/health",
    }
