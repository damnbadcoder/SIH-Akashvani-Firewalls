import os
import sys
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Ensure root workspace is on python path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from backend.config import settings
from backend.database import init_db
from backend.routers import (
    health_router,
    auth_router,
    pipeline_router,
    proofcheck_router,
    chat_router,
    signing_router,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("transmute.backend")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing Transmute Backend System...")
    init_db()
    logger.info(f"Storage directories active at: {settings.STORAGE_DIR}")
    yield
    logger.info("Shutting down Transmute Backend System...")

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="End-to-end multimodal intelligence ingestion, preview review, and deliverable synthesis platform.",
    lifespan=lifespan,
)

# CORS middleware for seamless communication with frontend Vite server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(pipeline_router)
app.include_router(proofcheck_router)
app.include_router(chat_router)
app.include_router(signing_router)

def start_server(host: str = None, port: int = None):
    import uvicorn
    h = host or settings.HOST
    p = port or settings.PORT
    logger.info(f"Starting Uvicorn server on http://{h}:{p}")
    uvicorn.run("backend.main:app", host=h, port=p, reload=False)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", settings.PORT))
    start_server(settings.HOST, port)
