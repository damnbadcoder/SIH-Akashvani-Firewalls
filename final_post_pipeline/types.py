from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class ProvenanceItem(BaseModel):
    citation_marker: str
    source_reference: str
    verification_score: Optional[float] = None
    verification_status: Optional[str] = None
    is_verified: Optional[bool] = None

class FinalDeliverableResult(BaseModel):
    platform_key: str
    final_content: str
    provenance: List[ProvenanceItem] = Field(default_factory=list)
    verification: Optional[Dict[str, Any]] = None
    relinked_citations: Optional[List[Any]] = None
    readability: Optional[Dict[str, Any]] = None
    original_english: Optional[str] = None

