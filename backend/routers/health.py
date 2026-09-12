from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from backend.database import get_db, ACTIVE_DB_URL
from backend.services.router_service import ALL_SUPPORTED_EXTENSIONS

router = APIRouter(tags=["Health"])

@router.get("/health")
@router.get("/api/health")
def health_check(db: Session = Depends(get_db)):
    db_status = "healthy"
    try:
        db.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"unreachable ({e})"

    return {
        "status": "healthy",
        "service": "Transmute Intelligence & Synthesis Platform",
        "database": {
            "status": db_status,
            "engine": ACTIVE_DB_URL.split("://")[0] if "://" in ACTIVE_DB_URL else "unknown"
        },
        "supported_file_formats_count": len(ALL_SUPPORTED_EXTENSIONS),
        "supported_formats": sorted(list(ALL_SUPPORTED_EXTENSIONS)),
        "pipelines": ["text", "audio", "video", "image", "link"],
    }
