from pydantic import BaseModel, Field
from typing import List, Optional

class CitationVerdict(BaseModel):
    claim_sentence: str
    citation_marker: str
    entailment_score: float = Field(ge=0.0, le=1.0)
    status: str  # "ENTAILED", "NEUTRAL", "CONTRADICTION"
    is_verified: bool

class NLIVerificationResult(BaseModel):
    verified_text: str
    total_claims_checked: int
    verified_count: int
    hallucinated_count: int
    verdicts: List[CitationVerdict]
    passed: bool
