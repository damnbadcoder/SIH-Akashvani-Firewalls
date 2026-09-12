from fastapi import APIRouter
from backend.schemas.pipeline import ProofcheckRequest, ProofcheckResponse
from backend.services.conditional_service import conditional_routing_service

router = APIRouter(tags=["Proofcheck"])

@router.post("/api/proofcheck", response_model=ProofcheckResponse)
def proofcheck_content(payload: ProofcheckRequest):
    target_text = payload.text if payload.text is not None else (payload.previewText or "")
    is_org = payload.is_organization if payload.is_organization is not None else (payload.isOrganisation if payload.isOrganisation is not None else True)

    if is_org:
        audited_text, flags = conditional_routing_service.enhance_3_sensitive_check(target_text)
    else:
        audited_text, flags = target_text, []

    return ProofcheckResponse(
        proofcheckedText=audited_text,
        sensitiveCount=len(flags),
        flags=[f.model_dump() if hasattr(f, "model_dump") else f for f in flags],
    )
