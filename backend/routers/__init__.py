from backend.routers.health import router as health_router
from backend.routers.auth import router as auth_router
from backend.routers.pipeline import router as pipeline_router
from backend.routers.proofcheck import router as proofcheck_router
from backend.routers.chat import router as chat_router

__all__ = [
    "health_router",
    "auth_router",
    "pipeline_router",
    "proofcheck_router",
    "chat_router",
]
