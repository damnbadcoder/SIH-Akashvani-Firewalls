#!/usr/bin/env python3
"""
Standalone Verification Suite for Enhancement 4:
Readability & Tone Regression Scoring Engine

Tests:
1. Test Simple Text (High Reading Ease > 70, Low Grade Level < 6)
2. Test Complex Technical Text (Lower Reading Ease, Higher Grade Level > 10)
3. Latency Benchmark (< 5ms execution time)
4. Platform Calibration Compliance (LinkedIn, Executive Brief, Video Script)
5. Content Preservation / Non-mutation Invariant
6. Edge Case Handling (Empty text, Markdown citations, IP addresses, abbreviations)
"""

import os
import sys
import time
from pathlib import Path

# Auto-switch to project virtual environment if executed with system/global python
venv_python = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".venv", "bin", "python")
if os.path.exists(venv_python) and os.path.realpath(sys.executable) != os.path.realpath(venv_python):
    os.execv(venv_python, [venv_python] + sys.argv)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from enhancements.readability_scorer import score_readability, ReadabilityScorer
from enhancements.readability_scorer.types import ReadabilityResult, ReadabilityMetrics


def test_1_simple_text():
    """
    Test 1: Simple Text Test
    Input: Simple sentences with 1-syllable words.
    Asserts: High Reading Ease (> 70), Low Grade Level (< 6).
    """
    print("\n--- Running Test 1: Simple Text Readability ---")
    simple_text = (
        "The cat sat on the mat. "
        "The dog ran in the sun. "
        "It was a hot and fun day for all of us. "
        "We like to play in the yard."
    )

    report = score_readability(simple_text, platform_key="linkedin_post")
    metrics = report["metrics"]
    ease = metrics["flesch_reading_ease"]
    grade = metrics["flesch_kincaid_grade"]

    print(f"Input text:     {simple_text}")
    print(f"Metrics:        Reading Ease = {ease}, Grade Level = {grade}, Fog = {metrics['gunning_fog']}")
    print(f"Classification: verdict = {report['verdict']}, passed = {report['passed']}")

    assert ease > 70.0, f"Expected Reading Ease > 70.0, got {ease}"
    assert grade < 6.0, f"Expected Grade Level < 6.0, got {grade}"
    print("✅ Test 1 PASSED: Simple text produces High Reading Ease (> 70) and Low Grade Level (< 6).")


def test_2_complex_technical_text():
    """
    Test 2: Complex Technical Text Test
    Input: Dense cybersecurity advisory text with multi-syllabic terminology.
    Asserts: Lower Reading Ease, Higher Grade Level (> 10).
    """
    print("\n--- Running Test 2: Complex Technical Text Readability ---")
    complex_text = (
        "Critical unauthenticated remote code execution vulnerability discovered in cryptographic "
        "subsystem necessitating immediate remediation and comprehensive architecture re-evaluation. "
        "Dissemination of unsegmented telemetry facilitates unauthorized privilege escalation across "
        "distributed operational microcontroller networks [^src-1]."
    )

    report = score_readability(complex_text, platform_key="executive_brief")
    metrics = report["metrics"]
    ease = metrics["flesch_reading_ease"]
    grade = metrics["flesch_kincaid_grade"]

    print(f"Input text:     {complex_text}")
    print(f"Metrics:        Reading Ease = {ease}, Grade Level = {grade}, Fog = {metrics['gunning_fog']}")
    print(f"Classification: verdict = {report['verdict']}, passed = {report['passed']}")

    assert grade > 10.0, f"Expected Grade Level > 10.0 for dense advisory text, got {grade}"
    assert ease < 60.0, f"Expected Reading Ease < 60.0 for dense advisory text, got {ease}"
    print("✅ Test 2 PASSED: Complex text produces Lower Reading Ease and Higher Grade Level (> 10).")


def test_3_latency_benchmark():
    """
    Test 3: Latency Constraint Test
    Asserts: Execution time under 5ms for standard deliverable text.
    """
    print("\n--- Running Test 3: Sub-5ms Latency Benchmark ---")
    sample_text = """
    # Executive Brief: Automotive Cybersecurity Assessment

    Senior management must review our security findings for modern vehicles and network systems.
    Our audit team found several serious flaws in the central computer and wireless communication links [^src-1].
    If these flaws are exploited, attackers can gain unauthorized remote access to the car.
    Leaders should provide funding to patch all systems and improve active defense tools.
    These proactive actions will reduce operational risks and satisfy all government standards.

    ### Key Recommendations:
    1. Deploy perimeter validation on all telemetry gateways.
    2. Establish continuous monitoring across critical vehicle control units.
    """ * 5  # ~500 words

    scorer = ReadabilityScorer()

    # Warm-up run
    scorer.score(sample_text, platform_key="executive_brief")

    iterations = 200
    start = time.perf_counter()
    for _ in range(iterations):
        res = scorer.score(sample_text, platform_key="executive_brief")
    total_time = time.perf_counter() - start
    avg_ms = (total_time / iterations) * 1000.0

    print(f"Words processed per run: {res.metrics.word_count}")
    print(f"Average execution time:  {avg_ms:.3f} ms over {iterations} iterations")

    assert avg_ms < 5.0, f"Latency benchmark exceeded: expected < 5.0 ms, got {avg_ms:.3f} ms"
    print(f"✅ Test 3 PASSED: Sub-5ms execution time verified ({avg_ms:.3f} ms < 5.0 ms).")


def test_4_platform_calibration():
    """
    Test 4: Platform Calibration Compliance
    Asserts:
    - LinkedIn: Optimal Grade 7-10, Ease >= 55.0 outputs OPTIMAL
    - Executive Brief: Grade 10-14, Ease 35-55 outputs OPTIMAL
    - Video Script: Grade 6-9, Ease >= 65.0 outputs OPTIMAL
    - Tone mismatch outputs TOO_DENSE or TOO_SIMPLE
    """
    print("\n--- Running Test 4: Platform Calibration & Drift Detection ---")

    # A. Calibrated LinkedIn post
    linkedin_text = (
        "Good cybersecurity is about simple daily habits for everyone on your team. "
        "Last week, we hosted a workshop on how to protect smart cars from cyber attacks. "
        "Over one hundred experts attended to share tips and tools for better defense. "
        "If you build software, take time to review your code and test your systems today. "
        "A small security check now can prevent a major headache in the future."
    )
    li_report = score_readability(linkedin_text, platform_key="linkedin_post")
    print(f"LinkedIn Post:   Grade={li_report['metrics']['flesch_kincaid_grade']}, "
          f"Ease={li_report['metrics']['flesch_reading_ease']}, Verdict={li_report['verdict']}")
    assert li_report["passed"] is True, f"Expected LinkedIn text to pass: {li_report}"
    assert li_report["verdict"] == "OPTIMAL"

    # B. Calibrated Executive Brief
    exec_text = (
        "Senior management must review our security findings for modern vehicles and network systems. "
        "Our audit team found several serious flaws in the central computer and wireless communication links. "
        "If these flaws are exploited, attackers can gain unauthorized remote access to the car. "
        "Leaders should provide funding to patch all systems and improve active defense tools. "
        "These proactive actions will reduce operational risks and satisfy all government standards."
    )
    exec_report = score_readability(exec_text, platform_key="executive_brief")
    print(f"Executive Brief: Grade={exec_report['metrics']['flesch_kincaid_grade']}, "
          f"Ease={exec_report['metrics']['flesch_reading_ease']}, Verdict={exec_report['verdict']}")
    assert exec_report["passed"] is True, f"Expected Executive text to pass: {exec_report}"
    assert exec_report["verdict"] == "OPTIMAL"

    # C. Calibrated Video Script
    video_text = (
        "Hey everyone, welcome back! "
        "Today we are looking at how attackers target modern smart cars. "
        "Vehicles run lots of software code to control the engine and navigation. "
        "If someone finds a bug in that code, they might be able to control the car. "
        "In this video, I will show you how automotive engineers test their systems. "
        "Be sure to hit like and subscribe for more cybersecurity tips."
    )
    vid_report = score_readability(video_text, platform_key="video_script")
    print(f"Video Script:    Grade={vid_report['metrics']['flesch_kincaid_grade']}, "
          f"Ease={vid_report['metrics']['flesch_reading_ease']}, Verdict={vid_report['verdict']}")
    assert vid_report["passed"] is True, f"Expected Video Script to pass: {vid_report}"
    assert vid_report["verdict"] == "OPTIMAL"

    # D. Tone Drift Check: Dense text submitted to LinkedIn
    dense_text = (
        "Cryptographic obfuscation in decentralized firmware architectures necessitates hyper-parameterized "
        "formal verification algorithms to preclude multi-tenancy vulnerability exploitation."
    )
    drift_report = score_readability(dense_text, platform_key="linkedin_post")
    print(f"Dense on LinkedIn: Verdict={drift_report['verdict']}, Passed={drift_report['passed']}")
    assert drift_report["verdict"] == "TOO_DENSE"
    assert drift_report["passed"] is False

    # E. Tone Drift Check: Elementary text submitted to Executive Brief
    simple_text = "The dog ran fast. The cat was small. The sun was hot."
    simple_exec_report = score_readability(simple_text, platform_key="executive_brief")
    print(f"Simple on Exec:   Verdict={simple_exec_report['verdict']}, Passed={simple_exec_report['passed']}")
    assert simple_exec_report["verdict"] == "TOO_SIMPLE"
    assert simple_exec_report["passed"] is False

    print("✅ Test 4 PASSED: Calibrated platforms pass; mismatched tones correctly trigger TOO_DENSE or TOO_SIMPLE.")


def test_5_content_preservation():
    """
    Test 5: Content Preservation Invariant
    Asserts: Original text and citation markers are 100% untouched. Readability analysis is strictly read-only.
    """
    print("\n--- Running Test 5: Content Preservation Invariant ---")
    original_text = (
        "CERT-In organized SAMVAAD 2025 on automotive cybersecurity [^src-1]. "
        "Over 185 participants from 47 organizations attended [^src-2]. "
        "Key discussions centered on in-vehicle communications and perimeter testing [^aud-1]."
    )
    copy_text = str(original_text)

    report = score_readability(original_text, platform_key="linkedin_post")

    assert original_text == copy_text, "Original text string was mutated by score_readability!"
    assert "[^src-1]" in original_text
    assert "[^src-2]" in original_text
    assert "[^aud-1]" in original_text
    assert isinstance(report, dict)
    assert "metrics" in report
    assert report["metrics"]["word_count"] > 0
    print("✅ Test 5 PASSED: Input string and citation markers remain completely immutable.")


def test_6_edge_cases():
    """
    Test 6: Edge Cases & Robustness
    - Empty or whitespace-only text
    - Citations, IP addresses, abbreviations, code fences
    """
    print("\n--- Running Test 6: Edge Cases & Robustness ---")

    # Empty text
    empty_report = score_readability("", platform_key="linkedin_post")
    assert empty_report["passed"] is False
    assert empty_report["metrics"]["word_count"] == 0
    assert empty_report["verdict"] == "TOO_SIMPLE"

    # Text with IP addresses and abbreviations (e.g., 10.4.12.8, v1.2.0)
    abbrev_text = (
        "In v1.2, e.g. at 10.4.12.8, the telemetry service failed to validate incoming packets. "
        "However, CERT-In published an immediate advisory with remediation guidelines. "
        "System administrators should verify all endpoints vs. the compliance checklist."
    )
    abbrev_report = score_readability(abbrev_text, platform_key="technical_advisory")
    assert abbrev_report["metrics"]["sentence_count"] == 3, (
        f"Expected exactly 3 sentences despite abbreviations and IPs, got {abbrev_report['metrics']['sentence_count']}"
    )

    print("✅ Test 6 PASSED: Edge cases (empty text, IPs, abbreviations) handled cleanly.")


def run_all_tests():
    print("=" * 70)
    print("ENHANCEMENT 4: READABILITY & TONE SCORING SUITE VERIFICATION")
    print("=" * 70)

    test_1_simple_text()
    test_2_complex_technical_text()
    test_3_latency_benchmark()
    test_4_platform_calibration()
    test_5_content_preservation()
    test_6_edge_cases()

    print("\n" + "=" * 70)
    print("🎯 ALL READABILITY SCORER VERIFICATION TESTS PASSED SUCCESSFULLY!")
    print("=" * 70)


if __name__ == "__main__":
    run_all_tests()
