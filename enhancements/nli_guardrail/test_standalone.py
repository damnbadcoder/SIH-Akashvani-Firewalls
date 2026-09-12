#!/usr/bin/env python3
"""
Standalone Verification Suite for Enhancement 2:
NLI Cross-Encoder Provenance Verification Engine

Tests:
1. Grounded Claim Test (Must output ENTAILED, is_verified=True)
2. Hallucinated Claim Test (Must output CONTRADICTION or NEUTRAL, is_verified=False)
3. Sub-50ms Latency Benchmark (< 50ms per draft sentence)
4. Multi-claim Draft Verification (Mixed Grounded & Hallucinated Claims)
5. Content Preservation Invariant (Original draft & citations remain 100% intact)
6. Zero-citation Draft Handling
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

from enhancements.nli_guardrail import verify_citations, NLICrossEncoderGuard
from enhancements.nli_guardrail.types import CitationVerdict, NLIVerificationResult


def test_1_grounded_claim():
    """
    Test 1: Grounded Claim Test
    Premise: "CERT-In organized an Automotive Cybersecurity Workshop on December 11, 2025 with over 185 participants."
    Hypothesis: "Over 185 stakeholders joined the CERT-In automotive session [^src-1]."
    Must output: ENTAILED, is_verified=True.
    """
    print("\n--- Running Test 1: Grounded Claim Entailment ---")
    premise = "CERT-In organized an Automotive Cybersecurity Workshop on December 11, 2025 with over 185 participants."
    hypothesis = "Over 185 stakeholders joined the CERT-In automotive session [^src-1]."

    guard = NLICrossEncoderGuard()
    score, status, is_verified = guard.evaluate_pair(premise, hypothesis)

    print(f"Premise:    {premise}")
    print(f"Hypothesis: {hypothesis}")
    print(f"Result:     score={score:.4f}, status={status}, is_verified={is_verified}")

    assert status == "ENTAILED", f"Expected status 'ENTAILED' but got '{status}'"
    assert is_verified is True, f"Expected is_verified=True but got {is_verified}"
    assert score >= 0.70, f"Expected score >= 0.70 for entailed claim, got {score:.4f}"

    # Also test via verify_citations API
    report = verify_citations(hypothesis, premise)
    assert report["passed"] is True, f"Expected passed=True in report: {report}"
    assert report["total_claims_checked"] == 1
    assert report["verified_count"] == 1
    assert report["hallucinated_count"] == 0
    assert report["verdicts"][0]["status"] == "ENTAILED"
    assert report["verdicts"][0]["is_verified"] is True
    assert report["verdicts"][0]["citation_marker"] == "[^src-1]"

    print("✅ Test 1 PASSED: Grounded claim successfully verified with ENTAILED status.")


def test_2_hallucinated_claim():
    """
    Test 2: Hallucinated Claim Test
    Premise: "CERT-In organized an Automotive Cybersecurity Workshop on December 11, 2025 with over 185 participants."
    Hypothesis: "NetScaler ADC suffers from an unauthenticated RCE exploit [^src-1]."
    Must output: CONTRADICTION or NEUTRAL, is_verified=False.
    """
    print("\n--- Running Test 2: Hallucinated Claim Detection ---")
    premise = "CERT-In organized an Automotive Cybersecurity Workshop on December 11, 2025 with over 185 participants."
    hypothesis = "NetScaler ADC suffers from an unauthenticated RCE exploit [^src-1]."

    guard = NLICrossEncoderGuard()
    score, status, is_verified = guard.evaluate_pair(premise, hypothesis)

    print(f"Premise:    {premise}")
    print(f"Hypothesis: {hypothesis}")
    print(f"Result:     score={score:.4f}, status={status}, is_verified={is_verified}")

    assert status in ("CONTRADICTION", "NEUTRAL"), f"Expected CONTRADICTION or NEUTRAL, got '{status}'"
    assert is_verified is False, f"Expected is_verified=False but got {is_verified}"
    assert score < 0.70, f"Expected score < 0.70 for hallucinated claim, got {score:.4f}"

    # Test via verify_citations API
    report = verify_citations(hypothesis, premise)
    assert report["passed"] is False, f"Expected passed=False for hallucinated draft, got: {report}"
    assert report["total_claims_checked"] == 1
    assert report["verified_count"] == 0
    assert report["hallucinated_count"] == 1
    assert report["verdicts"][0]["status"] in ("CONTRADICTION", "NEUTRAL")
    assert report["verdicts"][0]["is_verified"] is False

    print(f"✅ Test 2 PASSED: Hallucinated claim caught with status '{status}', is_verified=False.")


def test_3_sub_50ms_latency():
    """
    Test 3: Latency Benchmark (< 50ms per draft sentence)
    """
    print("\n--- Running Test 3: Sub-50ms Latency Benchmark ---")
    premise = """
    CERT-In organized an Automotive Cybersecurity Workshop on December 11, 2025 with over 185 participants.
    Technical sessions explored ECU firmware validation, in-vehicle CAN bus intrusion detection systems,
    and telematics telemetry isolation. Speakers highlighted compliance with AIS-189 and ISO/SAE 21434.
    """
    draft_sentence = "Over 185 stakeholders joined the CERT-In automotive session [^src-1]."

    # Warmup
    verify_citations(draft_sentence, premise)

    # Measure latency across 10 iterations
    times_ms = []
    for _ in range(10):
        t0 = time.perf_counter()
        verify_citations(draft_sentence, premise)
        dt_ms = (time.perf_counter() - t0) * 1000
        times_ms.append(dt_ms)

    avg_ms = sum(times_ms) / len(times_ms)
    max_ms = max(times_ms)
    print(f"Average latency per sentence check: {avg_ms:.3f} ms")
    print(f"Maximum latency observed:           {max_ms:.3f} ms")

    assert max_ms < 50.0, f"Latency {max_ms:.3f}ms exceeded 50ms ceiling!"
    print(f"✅ Test 3 PASSED: Offline NLI verification runs in {avg_ms:.3f}ms (target < 50ms).")


def test_4_multi_claim_draft():
    """
    Test 4: Mixed Draft Verification with Grounded & Hallucinated Claims
    """
    print("\n--- Running Test 4: Mixed Multi-Claim Draft Verification ---")
    grounding_doc = """
    The ShadowGate Collective exploited CVE-2026-41822 in BankShield middleware affecting 3,200 controllers.
    CERT-In organized an Automotive Cybersecurity Workshop with over 185 participants on December 11, 2025.
    Initial access occurred via bastion gateway 10.14.2.1 using dumped credentials.
    """

    draft_text = """
    # Executive Briefing
    Over 185 stakeholders joined the CERT-In automotive session [^src-1].
    The ShadowGate Collective exploited CVE-2026-41822 affecting 3,200 controllers [^src-2].
    NetScaler ADC suffers from an unauthenticated RCE exploit [^src-3].
    """

    report = verify_citations(draft_text, grounding_doc)
    print(f"Total claims checked: {report['total_claims_checked']}")
    print(f"Verified count:       {report['verified_count']}")
    print(f"Hallucinated count:   {report['hallucinated_count']}")
    print(f"Overall passed:       {report['passed']}")

    assert report["total_claims_checked"] == 3
    assert report["verified_count"] == 2
    assert report["hallucinated_count"] == 1
    assert report["passed"] is False

    verdicts_map = {v["citation_marker"]: v for v in report["verdicts"]}
    assert verdicts_map["[^src-1]"]["is_verified"] is True
    assert verdicts_map["[^src-2]"]["is_verified"] is True
    assert verdicts_map["[^src-3]"]["is_verified"] is False

    print("✅ Test 4 PASSED: Accurately identified 2 grounded citations and 1 hallucinated citation.")


def test_5_content_preservation():
    """
    Test 5: Content Preservation Invariant
    Verify that verified_text matches original draft verbatim and citation markers are untouched.
    """
    print("\n--- Running Test 5: Content & Citation Preservation Invariant ---")
    original_draft = (
        "Advisory summary: 185 stakeholders joined the workshop [^src-1]. "
        "Audio recorded key remarks [^aud-2]. Telemetry was normal."
    )
    premise = "Over 185 stakeholders joined the workshop on automotive safety."

    report = verify_citations(original_draft, premise)
    assert report["verified_text"] == original_draft, "Draft text was altered!"
    assert "[^src-1]" in report["verified_text"], "Citation [^src-1] was mangled!"
    assert "[^aud-2]" in report["verified_text"], "Citation [^aud-2] was mangled!"

    print("✅ Test 5 PASSED: Draft content and citation markers remained 100% unaltered.")


def test_6_zero_citation_draft():
    """
    Test 6: Handling drafts with zero citation markers
    """
    print("\n--- Running Test 6: Zero Citation Draft Handling ---")
    draft_no_cites = "This is a clean markdown note without citations."
    report = verify_citations(draft_no_cites, "Some context.")

    assert report["total_claims_checked"] == 0
    assert report["verified_count"] == 0
    assert report["hallucinated_count"] == 0
    assert report["passed"] is True
    assert report["verified_text"] == draft_no_cites

    print("✅ Test 6 PASSED: Drafts without citations gracefully handled.")


if __name__ == "__main__":
    print("=" * 75)
    print("🛡️  TRANSMUTE — ENHANCEMENT 2 NLI GUARDRAIL STANDALONE VERIFICATION")
    print("=" * 75)

    test_1_grounded_claim()
    test_2_hallucinated_claim()
    test_3_sub_50ms_latency()
    test_4_multi_claim_draft()
    test_5_content_preservation()
    test_6_zero_citation_draft()

    print("\n" + "=" * 75)
    print("🎉 ALL 6 STANDALONE TESTS COMPLETED AND PASSED SUCCESSFULLY!")
    print("=" * 75)
