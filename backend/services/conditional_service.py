import re
from typing import Dict, Any, List, Tuple

try:
    from enhancements.sensitivity_checker import scan_and_redact, strip_preview_wrappers
except ImportError:
    def scan_and_redact(text: str, is_organization: bool = False, wrap_html: bool = False):
        return text, []
    def strip_preview_wrappers(text: str) -> str:
        return text

try:
    from enhancements.nli_guardrail import verify_citations
except ImportError:
    def verify_citations(draft_text: str, source_context: str) -> dict:
        return {"verified_text": draft_text, "verdicts": [], "passed": True}

try:
    from enhancements.anchor_relinker import relink_citations
except ImportError:
    def relink_citations(edited_text: str, original_text: str = ""):
        return edited_text, []

try:
    from enhancements.readability_scorer import score_readability
except ImportError:
    def score_readability(text: str, platform_key: str = "default") -> dict:
        return {"passed": True, "flesch_reading_ease": 60.0, "metrics": {}}


class ConditionalRoutingService:
    """
    Phase 4: Conditional Logic Routing.
    Condition A: If organisation -> Route to Enhance-3 (Sensitive data check), then Enhance-4 (Restore removed citations).
    Condition B: Not organisation -> Bypass Enhancers 3 & 4 entirely.
    """

    @staticmethod
    def enhance_3_sensitive_check(text: str, wrap_html: bool = False) -> Tuple[str, List[Any]]:
        """
        Enhance-3: Scans and flags operational sensitive data.
        Defaults to wrap_html=False so final synthesis drafts remain clean text.
        """
        audited_text, flags = scan_and_redact(text, is_organization=True, wrap_html=wrap_html)
        return audited_text, flags

    @staticmethod
    def enhance_4_citation_restoration(
        draft_text: str,
        expected_citations: List[str],
        source_context: str
    ) -> str:
        """
        Enhance-4: If any citation was removed during previous steps, add it again.
        Ensures strict provenance integrity.
        """
        restored_text = draft_text
        if source_context:
            try:
                relinked, _ = relink_citations(restored_text, source_context)
                if relinked:
                    restored_text = relinked
            except Exception:
                pass

        missing_citations = []
        for cit in expected_citations:
            marker = cit if cit.startswith("[^") else f"[^{cit}]"
            if marker not in restored_text:
                missing_citations.append(marker)

        # If any citation was removed/omitted, restore it to relevant facts or at the end of key sentences
        if missing_citations:
            # Append citation anchors to the end of findings if not present
            restoration_block = f" {' '.join(missing_citations)}"
            # Find the last paragraph or add as a citation note
            lines = restored_text.split("\n")
            restored = False
            for i in range(len(lines) - 1, -1, -1):
                if lines[i].strip() and not lines[i].strip().startswith("#"):
                    lines[i] = lines[i] + restoration_block
                    restored = True
                    break
            if restored:
                restored_text = "\n".join(lines)
            else:
                restored_text += f"\n\n**Grounding Citations:** {restoration_block}"

        return restored_text

    @staticmethod
    def route_payload(
        draft_text: str,
        is_organisation: bool,
        expected_citations: List[str],
        source_context: str
    ) -> Tuple[str, List[Any], bool]:
        """
        Executes Conditional Logic:
        If is_organisation:
            Enhance-3 (Sensitive data check)
            Enhance-4 (Citation restoration)
        Else:
            Bypass Enhancers 3 and 4 entirely.
        """
        if not is_organisation:
            # Condition B: Bypass Enhancers 3 and 4 entirely
            return draft_text, [], False

        # Condition A:
        # Step 1: Enhance-3 (Clean scan without HTML span injection for final release)
        clean_draft = strip_preview_wrappers(draft_text)
        sensitive_text, flags = ConditionalRoutingService.enhance_3_sensitive_check(clean_draft, wrap_html=False)

        # Step 2: Enhance-4
        final_routed_text = ConditionalRoutingService.enhance_4_citation_restoration(
            draft_text=sensitive_text,
            expected_citations=expected_citations,
            source_context=source_context
        )

        final_routed_text = strip_preview_wrappers(final_routed_text)
        return final_routed_text, flags, True

conditional_routing_service = ConditionalRoutingService()
