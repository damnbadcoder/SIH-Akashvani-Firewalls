#!/usr/bin/env python3
"""
Standalone Verification Suite for Enhancement 3:
Semantic Anchor Re-Linker (User Edit Protection Engine)

Tests:
1. Test Dropped Citation Re-linking (Rephrased claim receives dropped citation)
2. Test Existing Citation Untouched (No duplicate tag injection)
3. Test Unrelated Sentence (No spurious citations for unrelated additions)
4. Sub-15ms Latency Benchmark (Fast deterministic execution)
5. Multi-line Markdown Structure Preservation (Headings & bullets preserved)
6. Zero Citations / Empty Input Handling
"""

import os
import sys

# Auto-switch to project virtual environment if executed with system/global python
venv_python = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".venv", "bin", "python")
if os.path.exists(venv_python) and os.path.realpath(sys.executable) != os.path.realpath(venv_python):
    os.execv(venv_python, [venv_python] + sys.argv)

import time
from pathlib import Path

# Add repo root to sys.path so package imports work seamlessly
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from enhancements.anchor_relinker import relink_citations, SemanticAnchorRelinker
from enhancements.anchor_relinker.types import RelinkMatch, RelinkResult


def test_1_dropped_citation_relink():
    """
    Test 1: Dropped Citation Re-linking
    Original: "CERT-In organized an Automotive Cybersecurity Workshop on December 11, 2025 with over 185 participants [^src-1]."
    Edited: "On December 11, 2025, CERT-In hosted a cybersecurity session with more than 185 attendees." (User deleted [^src-1])
    Assertion: Output must append [^src-1] to the edited sentence.
    """
    print("\n--- Running Test 1: Dropped Citation Re-linking ---")
    original = "CERT-In organized an Automotive Cybersecurity Workshop on December 11, 2025 with over 185 participants [^src-1]."
    edited = "On December 11, 2025, CERT-In hosted a cybersecurity session with more than 185 attendees."

    relinked_text, matches = relink_citations(edited, original)

    print(f"Original: {original}")
    print(f"Edited:   {edited}")
    print(f"Relinked: {relinked_text}")
    print(f"Matches:  {[(m.citation_marker, m.similarity_score) for m in matches]}")

    assert "[^src-1]" in relinked_text, "Expected [^src-1] to be appended to the edited sentence!"
    assert len(matches) == 1, f"Expected 1 relink match, got {len(matches)}"
    assert matches[0].citation_marker == "[^src-1]"
    assert matches[0].similarity_score >= 0.55, f"Similarity score too low: {matches[0].similarity_score}"
    assert matches[0].relinked is True

    print("✅ Test 1 PASSED: Dropped citation [^src-1] successfully re-linked to rewritten sentence.")


def test_2_existing_citation_untouched():
    """
    Test 2: Existing Citation Untouched
    If user already kept [^src-1], it must NOT append a duplicate tag [^src-1] [^src-1].
    """
    print("\n--- Running Test 2: Existing Citation Untouched ---")
    original = "CERT-In organized an Automotive Cybersecurity Workshop on December 11, 2025 with over 185 participants [^src-1]."
    edited_with_tag = "On December 11, 2025, CERT-In hosted a cybersecurity session with more than 185 attendees [^src-1]."

    relinked_text, matches = relink_citations(edited_with_tag, original)

    print(f"Input:    {edited_with_tag}")
    print(f"Output:   {relinked_text}")
    print(f"Matches:  {len(matches)}")

    assert "[^src-1] [^src-1]" not in relinked_text, "Duplicate citation tag [^src-1] [^src-1] detected!"
    assert relinked_text.count("[^src-1]") == 1, f"Expected exactly 1 [^src-1], found {relinked_text.count('[^src-1]')}"
    assert len(matches) == 0, f"Expected 0 relink matches when citation is already present, got {len(matches)}"

    print("✅ Test 2 PASSED: Existing citation preserved without duplicate tagging.")


def test_3_unrelated_sentence():
    """
    Test 3: Unrelated Sentence
    New user-added sentence with zero overlap must NOT receive random citation markers.
    """
    print("\n--- Running Test 3: Unrelated Sentence Protection ---")
    original = "CERT-In organized an Automotive Cybersecurity Workshop on December 11, 2025 with over 185 participants [^src-1]."
    unrelated_edited = "We recommend routine password resets and daily database backups."

    relinked_text, matches = relink_citations(unrelated_edited, original)

    print(f"Input:    {unrelated_edited}")
    print(f"Output:   {relinked_text}")
    print(f"Matches:  {len(matches)}")

    assert "[^src-1]" not in relinked_text, "Spurious citation attached to unrelated sentence!"
    assert len(matches) == 0, f"Expected 0 matches for unrelated sentence, got {len(matches)}"
    assert relinked_text == unrelated_edited, "Unrelated sentence was unexpectedly altered!"

    print("✅ Test 3 PASSED: Unrelated sentences correctly ignored with zero spurious tags.")


def test_4_sub_15ms_latency():
    """
    Test 4: Latency Benchmark (< 15ms execution time)
    """
    print("\n--- Running Test 4: Sub-15ms Latency Benchmark ---")
    original_doc = """
    # Security Briefing
    - The ShadowGate Collective breached internal middleware [^src-1].
    - CERT-In held an Automotive Cybersecurity Workshop on December 11, 2025 with over 185 participants [^src-2].
    - Ingress occurred from bastion gateway 10.14.2.1 [^aud-1].
    """

    edited_doc = """
    # Security Briefing
    - The ShadowGate Collective infiltrated internal middleware.
    - On December 11, 2025, CERT-In hosted a cybersecurity session with more than 185 attendees.
    - Ingress originated through bastion gateway 10.14.2.1.
    """

    # Warmup
    relink_citations(edited_doc, original_doc)

    times_ms = []
    for _ in range(10):
        t0 = time.perf_counter()
        relink_citations(edited_doc, original_doc)
        dt_ms = (time.perf_counter() - t0) * 1000
        times_ms.append(dt_ms)

    avg_ms = sum(times_ms) / len(times_ms)
    max_ms = max(times_ms)
    print(f"Average latency for multi-sentence relinking: {avg_ms:.3f} ms")
    print(f"Maximum latency observed:                     {max_ms:.3f} ms")

    assert max_ms < 15.0, f"Execution time {max_ms:.3f}ms exceeded 15ms ceiling!"
    print(f"✅ Test 4 PASSED: Re-linker executed in {avg_ms:.3f}ms (target < 15ms).")


def test_5_markdown_structure_preservation():
    """
    Test 5: Markdown Structure Preservation
    Preserves headings, bullet points, blank lines, and formatting intact.
    """
    print("\n--- Running Test 5: Markdown Structure Preservation ---")
    original = (
        "## Key Takeaways\n\n"
        "* Over 185 stakeholders joined the automotive security workshop [^src-1].\n"
        "* Initial ingress was observed from gateway 10.14.2.1 [^aud-2].\n"
    )

    edited = (
        "## Key Takeaways\n\n"
        "* More than 185 attendees participated in the automotive security session.\n"
        "* Initial access was traced back to gateway 10.14.2.1.\n"
    )

    relinked, matches = relink_citations(edited, original)
    print(f"Relinked Markdown:\n{relinked}")

    assert relinked.startswith("## Key Takeaways\n\n")
    assert "* More than 185 attendees participated in the automotive security session" in relinked
    assert "[^src-1]" in relinked
    assert "[^aud-2]" in relinked
    assert len(matches) == 2

    print("✅ Test 5 PASSED: Markdown bullets, headings, and indentation 100% preserved.")


def test_6_zero_citations_and_empty_inputs():
    """
    Test 6: Empty inputs and text without citations
    """
    print("\n--- Running Test 6: Zero Citations & Empty Inputs ---")
    assert relink_citations("", "some text") == ("", [])
    assert relink_citations("some text", "") == ("some text", [])

    text_no_cites = "Text without any citation markers."
    relinked, matches = relink_citations(text_no_cites, "Original without citations.")
    assert relinked == text_no_cites
    assert matches == []

    print("✅ Test 6 PASSED: Graceful handling of empty and citation-free inputs.")


if __name__ == "__main__":
    print("=" * 75)
    print("🛡️  TRANSMUTE — ENHANCEMENT 3 ANCHOR RELINKER STANDALONE VERIFICATION")
    print("=" * 75)

    test_1_dropped_citation_relink()
    test_2_existing_citation_untouched()
    test_3_unrelated_sentence()
    test_4_sub_15ms_latency()
    test_5_markdown_structure_preservation()
    test_6_zero_citations_and_empty_inputs()

    print("\n" + "=" * 75)
    print("🎉 ALL 6 STANDALONE TESTS COMPLETED AND PASSED SUCCESSFULLY!")
    print("=" * 75)
