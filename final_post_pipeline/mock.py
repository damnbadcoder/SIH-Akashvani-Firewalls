from .types import FinalDeliverableResult, ProvenanceItem

def get_mock_final_deliverable(platform_key: str, approved_draft: str) -> FinalDeliverableResult:
    return FinalDeliverableResult(
        platform_key=platform_key,
        final_content=approved_draft,
        provenance=[
            ProvenanceItem(citation_marker="[^src-1]", source_reference="Primary Ingested Source Context")
        ]
    )

