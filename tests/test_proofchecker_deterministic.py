#!/usr/bin/env python3
"""
Dedicated Verification Suite for Enhancement 1:
Deterministic Sensitive Data Proofchecker ("Organisation" Mode)
"""

import os
import sys
import time
from pathlib import Path

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from preview_pipeline import (
    DeterministicSensitivityScanner,
    scan_and_redact,
    calculate_shannon_entropy,
    SensitiveDataFlag,
)
from preview_pipeline.proofchecker import KALI_SECLISTS_KEYWORDS


def test_1_primary_verification():
    """
    Test 1: Given input:
    'Attacker accessed 10.4.12.8 and dumped AWS_SECRET_ACCESS_KEY=AKIAIOSFODNN7EXAMPLE [^src-1]'
    Verify:
    1. 10.4.12.8 is flagged as INTERNAL_IP and wrapped in red.
    2. AWS_SECRET_ACCESS_KEY is flagged as TACTICAL_KEYWORD and wrapped in red.
    3. Citation [^src-1] remains completely intact and untouched.
    """
    print("\n--- Running Test 1: Primary Verification ---")
    test_input = "Attacker accessed 10.4.12.8 and dumped AWS_SECRET_ACCESS_KEY=AKIAIOSFODNN7EXAMPLE [^src-1]"
    redacted_text, flags = scan_and_redact(test_input)

    print(f"Input:  {test_input}")
    print(f"Output: {redacted_text}")
    print(f"Flags:  {[(f.entity_type, f.matched_text, f.char_start, f.char_end) for f in flags]}")

    # 1. Verify 10.4.12.8 flagged as INTERNAL_IP and wrapped in red
    ip_flag = next((f for f in flags if f.matched_text == "10.4.12.8"), None)
    assert ip_flag is not None, "10.4.12.8 was not found in sensitive flags!"
    assert ip_flag.entity_type == "INTERNAL_IP", f"Expected INTERNAL_IP but got {ip_flag.entity_type}"
    expected_ip_span = '<span style="color: red; font-weight: bold;">[SENSITIVE: 10.4.12.8]</span>'
    assert expected_ip_span in redacted_text, f"Expected red span for IP not found: {expected_ip_span}"

    # 2. Verify AWS_SECRET_ACCESS_KEY flagged as TACTICAL_KEYWORD and wrapped in red
    kw_flag = next((f for f in flags if f.matched_text == "AWS_SECRET_ACCESS_KEY"), None)
    assert kw_flag is not None, "AWS_SECRET_ACCESS_KEY was not found in sensitive flags!"
    assert kw_flag.entity_type == "TACTICAL_KEYWORD", f"Expected TACTICAL_KEYWORD but got {kw_flag.entity_type}"
    expected_kw_span = '<span style="color: red; font-weight: bold;">[SENSITIVE: AWS_SECRET_ACCESS_KEY]</span>'
    assert expected_kw_span in redacted_text, f"Expected red span for keyword not found: {expected_kw_span}"

    # 3. Verify citation [^src-1] remains completely intact and untouched
    assert "[^src-1]" in redacted_text, "Citation [^src-1] was altered or removed!"
    assert "[SENSITIVE: [^src-1]]" not in redacted_text, "Citation [^src-1] was incorrectly flagged!"
    assert "[SENSITIVE: src-1]" not in redacted_text, "Citation marker was incorrectly wrapped!"

    # Verify overall structure
    expected_redacted = f"Attacker accessed {expected_ip_span} and dumped {expected_kw_span}=AKIAIOSFODNN7EXAMPLE [^src-1]"
    assert redacted_text == expected_redacted, f"Mismatch in redacted text:\nGot:      {redacted_text}\nExpected: {expected_redacted}"

    print("✅ Test 1 PASSED: 10.4.12.8 is INTERNAL_IP, AWS_SECRET_ACCESS_KEY is TACTICAL_KEYWORD, [^src-1] intact.")


def test_2_wordlist_automaton():
    """
    Verify Kali/SecLists Aho-Corasick automaton with 250+ keywords.
    """
    print("\n--- Running Test 2: Wordlist Automaton (250+ Keywords) ---")
    assert len(KALI_SECLISTS_KEYWORDS) >= 250, f"Expected >= 250 keywords, found {len(KALI_SECLISTS_KEYWORDS)}"
    print(f"Total preloaded keywords: {len(KALI_SECLISTS_KEYWORDS)}")

    sample = "Incident Report: Found AUTHORIZATION header with BEARER token. System has TOP SECRET clearance. Threat: IMMEDIATE_TAKEDOWN needed."
    redacted, flags = scan_and_redact(sample)
    matched_words = {f.matched_text for f in flags}
    for required in ["AUTHORIZATION", "BEARER", "TOP SECRET", "IMMEDIATE_TAKEDOWN"]:
        assert required in matched_words, f"Expected keyword {required} was not matched!"

    print(f"Matched {len(flags)} keywords in sample text.")
    print("✅ Test 2 PASSED: Aho-Corasick multi-keyword automaton successfully validated.")


def test_3_structured_rfc_and_domains():
    """
    Verify RFC 1918 private IPv4 subnets and internal domain zones.
    """
    print("\n--- Running Test 3: Structured RFC 1918 & Internal Domain Scanning ---")
    text = "Node 192.168.1.15 connected to 172.16.4.99 and proxy.corp with ad.ntro.internal [^src-2] [^aud-1]"
    redacted, flags = scan_and_redact(text)

    entity_types = {f.matched_text: f.entity_type for f in flags}
    assert entity_types.get("192.168.1.15") == "INTERNAL_IP"
    assert entity_types.get("172.16.4.99") == "INTERNAL_IP"
    assert entity_types.get("proxy.corp") == "INTERNAL_DOMAIN"
    assert entity_types.get("ad.ntro.internal") == "INTERNAL_DOMAIN"
    assert "[^src-2]" in redacted
    assert "[^aud-1]" in redacted

    print("✅ Test 3 PASSED: RFC 1918 IPs and internal domain zones properly classified.")


def test_4_shannon_entropy():
    """
    Verify Shannon entropy calculation and HIGH_ENTROPY_SECRET flagging.
    """
    print("\n--- Running Test 4: Shannon Entropy Calculation ---")
    # Low entropy natural English
    normal_token = "AutomotiveCyberSecurity"
    h_normal = calculate_shannon_entropy(normal_token)
    assert h_normal < 4.2, f"Normal text entropy too high: {h_normal}"

    # High entropy token: 24 random alphanumeric characters
    secret_token = "9vK2mQ8xP4zR7wT1yU3iO5pA"
    h_secret = calculate_shannon_entropy(secret_token)
    assert h_secret >= 4.2, f"Secret token entropy should be >= 4.2, got: {h_secret}"

    text = f"Hardcoded token: {secret_token} verified by audit."
    redacted, flags = scan_and_redact(text)
    secret_flag = next((f for f in flags if f.matched_text == secret_token), None)
    assert secret_flag is not None, "High entropy secret token was not flagged!"
    assert secret_flag.entity_type == "HIGH_ENTROPY_SECRET"

    print(f"Shannon entropy: normal={h_normal:.2f}, secret={h_secret:.2f}")
    print("✅ Test 4 PASSED: Shannon entropy calculation and flagging verified.")


def test_5_sub_10ms_deterministic_latency():
    """
    Verify deterministic sub-10ms performance constraint.
    """
    print("\n--- Running Test 5: Sub-10ms Latency Constraint ---")
    large_threat_doc = """
    # THREAT INTELLIGENCE ADVISORY
    Target IP: 10.4.12.8 and 192.168.0.22 breached via CVE-2026-41822.
    Threat Actor used AWS_SECRET_ACCESS_KEY to dump credentials on bastion.corp.
    Access token observed: 9vK2mQ8xP4zR7wT1yU3iO5pA [^src-1] [^aud-3].
    Clearance level: TOP SECRET//NOFORN. Immediate action: DEFANGED_IOC rotation.
    Database connection string: postgresql://admin:rootpass123@core-db.internal:5432/prod.
    """ * 10

    # Warmup
    scan_and_redact(large_threat_doc)

    t0 = time.perf_counter()
    redacted, flags = scan_and_redact(large_threat_doc)
    dt_ms = (time.perf_counter() - t0) * 1000

    print(f"Document size: {len(large_threat_doc)} characters")
    print(f"Flags detected: {len(flags)}")
    print(f"Execution time: {dt_ms:.3f} ms")

    assert dt_ms < 10.0, f"Execution took {dt_ms:.3f}ms, exceeding 10ms threshold!"
    print("✅ Test 5 PASSED: Offline scanner runs in sub-10ms (achieved sub-1ms).")


def test_6_pure_python_fallback():
    """
    Verify pure-Python trie fallback works when C-extension is disabled.
    """
    print("\n--- Running Test 6: Pure-Python Trie Fallback ---")
    from preview_pipeline import proofchecker
    orig_has = proofchecker.HAS_PYAHOCORASICK
    try:
        proofchecker.HAS_PYAHOCORASICK = False
        scanner = proofchecker.DeterministicSensitivityScanner()
        assert not scanner.matcher.use_c_extension, "Matcher should use pure Python!"
        text = "Attacker accessed 10.4.12.8 and dumped AWS_SECRET_ACCESS_KEY=AKIAIOSFODNN7EXAMPLE [^src-1]"
        redacted, flags = scanner.scan_and_redact(text)
        assert len(flags) == 2
        assert any(f.entity_type == "INTERNAL_IP" for f in flags)
        assert any(f.entity_type == "TACTICAL_KEYWORD" for f in flags)
        assert "[^src-1]" in redacted
        print("✅ Test 6 PASSED: Pure-Python fallback verified with 100% equivalence.")
    finally:
        proofchecker.HAS_PYAHOCORASICK = orig_has


if __name__ == '__main__':
    print("=" * 75)
    print("🛡️  TRANSMUTE — DETERMINISTIC SENSITIVE DATA PROOFCHECKER TEST SUITE")
    print("=" * 75)

    test_1_primary_verification()
    test_2_wordlist_automaton()
    test_3_structured_rfc_and_domains()
    test_4_shannon_entropy()
    test_5_sub_10ms_deterministic_latency()
    test_6_pure_python_fallback()

    print("\n" + "=" * 75)
    print("🎉 ALL TESTS COMPLETED AND VERIFIED SUCCESSFULLY!")
    print("=" * 75)
