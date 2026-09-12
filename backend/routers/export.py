"""
Router for exporting single deliverables or batch deliverable archives (.zip)
in various formats: .md, .txt, .pdf, .docx.
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from backend.services.export_service import (
    export_deliverable,
    export_all_deliverables_zip,
)

router = APIRouter(prefix="/api/export", tags=["export"])


class ExportSingleRequest(BaseModel):
    content: str = Field(..., description="Markdown deliverable content to export")
    output_type: str = Field("deliverable", description="Deliverable type slug (e.g. advisory, linkedin_post)")
    format: str = Field("md", description="Target format: 'md', 'txt', 'pdf', 'docx'")


class ExportZipRequest(BaseModel):
    deliverables: List[Dict[str, Any]] = Field(..., description="List of deliverables with output_type and content")
    format: str = Field("md", description="Target format for all items in archive: 'md', 'txt', 'pdf', 'docx'")
    session_id: Optional[str] = Field(None, description="Optional session id for naming archive")


@router.post("/single")
async def export_single(payload: ExportSingleRequest):
    """
    Exports a single deliverable in the chosen format (.md, .txt, .pdf, .docx)
    with all internal citation anchors stripped.
    """
    fmt = payload.format.lower().lstrip(".")
    if fmt not in ("md", "txt", "pdf", "docx"):
        raise HTTPException(status_code=400, detail=f"Unsupported format '{payload.format}'. Use 'md', 'txt', 'pdf', or 'docx'.")

    try:
        data_bytes, filename, media_type = export_deliverable(
            content=payload.content,
            output_type=payload.output_type,
            file_format=fmt,
        )

        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Access-Control-Expose-Headers": "Content-Disposition",
        }
        return Response(content=data_bytes, media_type=media_type, headers=headers)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Export failed: {str(exc)}")


@router.post("/zip")
async def export_zip(payload: ExportZipRequest):
    """
    Exports all deliverables in the chosen format (.md, .txt, .pdf, .docx)
    bundled inside a single .zip file with citations stripped.
    """
    fmt = payload.format.lower().lstrip(".")
    if fmt not in ("md", "txt", "pdf", "docx"):
        raise HTTPException(status_code=400, detail=f"Unsupported format '{payload.format}'. Use 'md', 'txt', 'pdf', or 'docx'.")

    if not payload.deliverables:
        raise HTTPException(status_code=400, detail="Deliverables list cannot be empty.")

    try:
        prefix = f"deliverables_{payload.session_id[:8]}" if payload.session_id else "cyber_deliverables"
        zip_bytes, zip_filename, media_type = export_all_deliverables_zip(
            deliverables=payload.deliverables,
            file_format=fmt,
            prefix=prefix,
        )

        headers = {
            "Content-Disposition": f'attachment; filename="{zip_filename}"',
            "Access-Control-Expose-Headers": "Content-Disposition",
        }
        return Response(content=zip_bytes, media_type=media_type, headers=headers)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Zip export failed: {str(exc)}")
