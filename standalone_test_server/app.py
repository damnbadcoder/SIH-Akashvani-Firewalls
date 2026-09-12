import os
import sys
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Dict, Any, List, Optional

# We need to add the parent directory to Python path to import our modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from preview_pipeline import generate_previews, scan_and_redact
from final_post_pipeline import generate_final_deliverable

app = FastAPI(title="Standalone Synthesis Test Server")

class ProofcheckRequest(BaseModel):
    text: Optional[str] = None
    previewText: Optional[str] = None
    is_organization: bool = True

@app.post("/api/proofcheck")
def proofcheck_text(payload: ProofcheckRequest):
    target_text = payload.text if payload.text is not None else (payload.previewText or "")
    if payload.is_organization:
        audited_text, flags = scan_and_redact(target_text)
    else:
        audited_text, flags = target_text, []
    return {
        "proofcheckedText": audited_text,
        "sensitiveCount": len(flags),
        "flags": [f.model_dump() for f in flags]
    }


class PreviewRequest(BaseModel):
    content_md: str
    metadata_json: Dict[str, Any]
    selected_outputs: List[str]
    parameters: Dict[str, Any]
    is_organization: bool = False

class FinalizeRequest(BaseModel):
    platform_key: str
    approved_draft: str
    content_md: str
    metadata_json: Dict[str, Any]
    parameters: Dict[str, Any]

@app.post("/api/preview")
def create_preview(payload: PreviewRequest):
    result = generate_previews(
        content_md=payload.content_md,
        metadata_json=payload.metadata_json,
        selected_outputs=payload.selected_outputs,
        parameters=payload.parameters,
        is_organization=payload.is_organization
    )
    return result.model_dump()

@app.post("/api/finalize")
def create_final_post(payload: FinalizeRequest):
    result = generate_final_deliverable(
        platform_key=payload.platform_key,
        approved_draft=payload.approved_draft,
        content_md=payload.content_md,
        metadata_json=payload.metadata_json,
        parameters=payload.parameters
    )
    return result.model_dump()
