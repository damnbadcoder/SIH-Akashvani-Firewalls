from fastapi import APIRouter
from backend.schemas.pipeline import ProofcheckRequest, ProofcheckResponse
from backend.services.conditional_service import conditional_routing_service

router = APIRouter(tags=["Proofcheck"])

@router.post("/api/proofcheck", response_model=ProofcheckResponse)
def proofcheck_content(payload: ProofcheckRequest):
    target_text = payload.text if payload.text is not None else (payload.previewText or "")
    is_org = payload.is_organization if payload.is_organization is not None else (payload.isOrganisation if payload.isOrganisation is not None else True)

    # By default, wrap_html is True for backward compatibility with legacy endpoints/tests unless explicitly set to False
    should_wrap = True if payload.wrap_html is None else bool(payload.wrap_html)

    if is_org:
        audited_text, flags = conditional_routing_service.enhance_3_sensitive_check(target_text, wrap_html=should_wrap)
    else:
        audited_text, flags = target_text, []

    return ProofcheckResponse(
        proofcheckedText=audited_text,
        cleanText=target_text,
        sensitiveCount=len(flags),
        flags=[f.model_dump() if hasattr(f, "model_dump") else f for f in flags],
    )
