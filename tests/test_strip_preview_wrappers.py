#!/usr/bin/env python3
"""
Verification tests for strip_preview_wrappers and leak prevention.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from final_post_pipeline.generator import strip_preview_wrappers
from enhancements.sensitivity_checker import scan_and_redact


def test_double_wrapping_cleanup():
    # Case 1: Plain double-wrapped redaction
    sample = "Under Situation: [SENSITIVE: [REDACTED: INTERNAL_IP]] was detected."
    cleaned = strip_preview_wrappers(sample)
    assert cleaned == "Under Situation: [REDACTED: INTERNAL_IP] was detected.", f"Failed: {cleaned}"

    # Case 2: HTML span double-wrapped redaction
    sample_html = 'Under Situation: <span style="color: red; font-weight: bold;">[SENSITIVE: [REDACTED: INTERNAL_IP]]</span> was detected.'
    cleaned_html = strip_preview_wrappers(sample_html)
    assert cleaned_html == "Under Situation: [REDACTED: INTERNAL_IP] was detected.", f"Failed: {cleaned_html}"

    # Case 3: [RESTRICTED] double wrapped
    sample_restricted = "Payload: [SENSITIVE: [RESTRICTED]]"
    cleaned_restricted = strip_preview_wrappers(sample_restricted)
    assert cleaned_restricted == "Payload: [RESTRICTED]", f"Failed: {cleaned_restricted}"
    print("✅ test_double_wrapping_cleanup PASSED")


def test_classification_header_cleanup_and_protection():
    # 1. Classification header with [SENSITIVE: ...] gets restored
    sample = "**CLASSIFICATION:** [SENSITIVE: STRICTLY CONFIDENTIAL // BOARD MATERIAL]"
    cleaned = strip_preview_wrappers(sample)
    assert cleaned == "**CLASSIFICATION:** STRICTLY CONFIDENTIAL // BOARD MATERIAL", f"Failed: {cleaned}"

    # 2. Scanner does NOT flag classification header lines
    doc = """# EXECUTIVE REPORT
**CLASSIFICATION:** STRICTLY CONFIDENTIAL // BOARD MATERIAL
TLP: TLP:AMBER+STRICT
Attacker pivot: 10.4.12.8 [^src-1]
"""
    clean_text, flags = scan_and_redact(doc, is_organization=True, wrap_html=False)
    assert len(flags) == 1, f"Expected 1 flag for IP, got {len(flags)}: {[f.matched_text for f in flags]}"
    assert flags[0].matched_text == "10.4.12.8"
    assert "STRICTLY CONFIDENTIAL" not in [f.matched_text for f in flags]
    print("✅ test_classification_header_cleanup_and_protection PASSED")


def test_redacted_token_protection():
    # Verify that [REDACTED: INTERNAL_IP] is protected from re-flagging
    doc = "Host at [REDACTED: INTERNAL_IP] was quarantined."
    clean_text, flags = scan_and_redact(doc, is_organization=True, wrap_html=False)
    assert len(flags) == 0, f"Expected 0 flags for already redacted doc, got {len(flags)}: {flags}"
    print("✅ test_redacted_token_protection PASSED")


def test_html_soc_badge_stripping():
    # Complex SOC-style review badge should be stripped back to plain text
    sample = (
        'Threat actor accessed <span class="sensitive-flag-badge critical soc-review-badge" '
        'data-flag-id="flag-1"><span class="badge-icon">🛡️</span> '
        '<span class="flag-matched-value">10.4.12.8</span> <span class="flag-review-pill">Review</span></span>.'
    )
    cleaned = strip_preview_wrappers(sample)
    assert cleaned == "Threat actor accessed 10.4.12.8.", f"Failed: {cleaned}"
    print("✅ test_html_soc_badge_stripping PASSED")


if __name__ == "__main__":
    test_double_wrapping_cleanup()
    test_classification_header_cleanup_and_protection()
    test_redacted_token_protection()
    test_html_soc_badge_stripping()
    print("🎉 ALL strip_preview_wrappers and protection tests PASSED!")
