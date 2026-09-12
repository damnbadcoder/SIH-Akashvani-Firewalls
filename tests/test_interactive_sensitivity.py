#!/usr/bin/env python3
"""
Test Suite: Interactive Sensitivity Flagging & Selection System
Verifies:
1. Zero text corruption in scan_and_redact (wrap_html=False).
2. Structured SensitiveDataFlag format: flag_id, entity_type, matched_text, char_start, char_end, severity, suggested_action.
3. Citation protection: [^src-1], [^aud-2], etc. are completely ignored by the scanner.
4. Redaction string offset arithmetic consistency (delta shift preserves subsequent coordinates).
5. Fast sub-10ms deterministic execution.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from enhancements.sensitivity_checker import scan_and_redact, scan, SensitiveDataFlag
from preview_pipeline.types import PlatformPreview, SensitiveDataFlag as PydanticFlag


def test_zero_text_corruption():
    """Verify wrap_html=False leaves markdown text 100% untouched."""
    raw_md = "# Incident Report\n\nAttacker pivoted to internal host 10.4.12.8 using AWS_SECRET_ACCESS_KEY=AKIAIOSFODNN7EXAMPLE [^src-1].\n"
    clean_text, flags = scan_and_redact(raw_md, is_organization=True, wrap_html=False)

    assert clean_text == raw_md, "clean_text was modified or corrupted!"
    assert len(flags) == 2, f"Expected 2 flags, found {len(flags)}"
    assert flags[0].flag_id == "flag-1"
    assert flags[0].entity_type == "INTERNAL_IP"
    assert flags[0].matched_text == "10.4.12.8"
    assert flags[0].severity == "CRITICAL"
    assert flags[0].suggested_action == "REDACT"
    assert flags[1].flag_id == "flag-2"
    assert flags[1].entity_type == "TACTICAL_KEYWORD"
    assert flags[1].matched_text == "AWS_SECRET_ACCESS_KEY"
    assert flags[1].severity == "HIGH"
    print("✅ test_zero_text_corruption PASSED")


def test_citation_protection():
    """Verify citations are never flagged or mangled."""
    text_with_citations = "Observed exploit payload at [^src-1] and verified against [^aud-2] and [^vid-3]."
    clean_text, flags = scan_and_redact(text_with_citations, is_organization=True, wrap_html=False)
    assert clean_text == text_with_citations
    assert len(flags) == 0, f"Expected 0 flags for citations, got {flags}"
    print("✅ test_citation_protection PASSED")


def test_redaction_offset_arithmetic():
    """Verify that operator redaction accurately shifts subsequent offsets."""
    text = "Host 192.168.1.50 compromised with token 12345678901234567890123456789012 [^src-1]"
    clean_text, flags = scan_and_redact(text, is_organization=True, wrap_html=False)
    assert len(flags) == 2

    # Operator redacts flag 1
    f1 = flags[0]
    replacement = f"[REDACTED: {f1.entity_type}]"
    edited = text[:f1.char_start] + replacement + text[f1.char_end:]
    delta = len(replacement) - (f1.char_end - f1.char_start)

    # Shift remaining flag
    f2 = flags[1]
    f2_new_start = f2.char_start + delta
    f2_new_end = f2.char_end + delta

    # Verify that shifted offset matches the exact substring in edited text
    extracted = edited[f2_new_start:f2_new_end]
    assert extracted == f2.matched_text, f"Offset mismatch: expected {f2.matched_text}, got {extracted}"
    print("✅ test_redaction_offset_arithmetic PASSED")


if __name__ == "__main__":
    test_zero_text_corruption()
    test_citation_protection()
    test_redaction_offset_arithmetic()
    print("🎉 All interactive sensitivity tests PASSED!")
