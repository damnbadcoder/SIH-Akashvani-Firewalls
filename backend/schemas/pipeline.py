from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class GenerationParams(BaseModel):
    audienceCategory: str = "technical"
    targetAudience: Optional[str] = ""
    tone: str = "Authoritative"
    detail: str = "Comprehensive Analysis"
    objective: str = "Threat Alert & Immediate Containment"
    language: str = "English"

class OutputItem(BaseModel):
    id: str
    params: Optional[GenerationParams] = None

class BoundingBox(BaseModel):
    x: float = Field(..., description="Left coordinate percentage 0.0-100.0")
    y: float = Field(..., description="Top coordinate percentage 0.0-100.0")
    width: float = Field(..., description="Width percentage 0.0-100.0")
    height: float = Field(..., description="Height percentage 0.0-100.0")
    text: Optional[str] = None

class Citation(BaseModel):
    id: str
    label: str
    kind: str = "file"  # file, link, text, ocr
    bbox: Optional[Dict[str, Any]] = None
    page_number: Optional[int] = None
    media_url: Optional[str] = None
    all_boxes: Optional[List[Dict[str, Any]]] = None

class PlatformPreview(BaseModel):
    platform_key: str
    output_type_id: Optional[str] = None
    draft_title: str
    draft_content: str
    citations_used: List[str] = Field(default_factory=list)
    sensitive_items_flagged: int = 0
    sensitive_flags: List[Any] = Field(default_factory=list)
    readability: Optional[Dict[str, Any]] = None

class GeneratePlanResponse(BaseModel):
    plan: str
    previewsByType: Dict[str, str]
    previews: Dict[str, PlatformPreview]
    citations: List[Citation]
    grounding_md: Optional[str] = None
    grounding_json: Optional[Any] = None
    extracted_facts: List[str] = Field(default_factory=list)
    session_id: Optional[str] = None

class ProofcheckRequest(BaseModel):
    text: Optional[str] = None
    previewText: Optional[str] = None
    is_organization: bool = True
    isOrganisation: Optional[bool] = None
    wrap_html: Optional[bool] = None
    mdContent: Optional[str] = None
    jsonMetadata: Optional[Any] = None

class ProofcheckResponse(BaseModel):
    proofcheckedText: str
    cleanText: Optional[str] = None
    sensitiveCount: int
    flags: List[Any] = Field(default_factory=list)

class GenerateDeliverableRequest(BaseModel):
    outputType: Optional[str] = None
    platform_key: Optional[str] = None
    previewDraft: Optional[str] = None
    approved_draft: Optional[str] = None
    sourceText: Optional[str] = None
    content_md: Optional[str] = None
    groundingMd: Optional[str] = None
    groundingJson: Optional[Any] = None
    metadata_json: Optional[Any] = None
    params: Optional[Dict[str, Any]] = None
    parameters: Optional[Dict[str, Any]] = None
    isOrganisation: Optional[bool] = False
    is_organization: Optional[bool] = False
    session_id: Optional[str] = None

class DeliverableResponse(BaseModel):
    content: str
    final_content: str
    provenance: List[Dict[str, Any]] = Field(default_factory=list)
    verification: Optional[Dict[str, Any]] = None
    relinked_citations: Optional[List[Any]] = None
    readability: Optional[Dict[str, Any]] = None
    deliverable_id: Optional[str] = None
    session_id: Optional[str] = None
