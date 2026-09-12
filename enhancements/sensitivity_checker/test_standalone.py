#!/usr/bin/env python3
"""
Standalone Verification Script for Enhancement 1:
Deterministic Sensitive Data Proofchecker ("Organisation" Mode)

Tests:
1. Primary verification: 10.4.12.8 (INTERNAL_IP), AWS_SECRET_ACCESS_KEY (TACTICAL_KEYWORD), untouched [^src-1]
2. 300+ sensitive tactical keywords across credentials, operational markings, and threat intel artifacts
3. Structured RFC 1918 private IPv4 subnets and internal domain zones (.internal, .corp, .local, .ntro)
4. Shannon entropy calculation and high-entropy secret detection (H >= 4.2)
5. Pure-Python trie fallback equivalence
6. Organization mode gating (is_organization=False vs is_organization=True)
7. Deterministic sub-10ms latency benchmark
"""

import os
import sys
import time
from pathlib import Path

# Add repo root to sys.path so package imports work seamlessly
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Also ensure local folder is accessible
LOCAL_DIR = Path(__file__).resolve().parent
if str(LOCAL_DIR) not in sys.path:
    sys.path.insert(0, str(LOCAL_DIR))

from enhancements.sensitivity_checker import (
    scan_and_redact,
    DeterministicSensitivityScanner,
    calculate_shannon_entropy,
    SensitiveDataFlag,
)
from enhancements.sensitivity_checker.wordlists import (
    SENSITIVE_KEYWORDS,
    KALI_SECLISTS_KEYWORDS,
)
from enhancements.sensitivity_checker import scanner as scanner_module


def test_1_primary_verification():
    """
    Test 1: Primary Verification
    Input: 'Attacker accessed 10.4.12.8 and dumped AWS_SECRET_ACCESS_KEY=AKIAIOSFODNN7EXAMPLE [^src-1]'
    Verify:
    1. 10.4.12.8 flagged as INTERNAL_IP and wrapped in red HTML span.
    2. AWS_SECRET_ACCESS_KEY flagged as TACTICAL_KEYWORD and wrapped in red HTML span.
    3. Citation [^src-1] remains completely intact and untouched.
    """
    print("\n--- Running Test 1: Primary Verification ---")
    test_input = "Attacker accessed 10.4.12.8 and dumped AWS_SECRET_ACCESS_KEY=AKIAIOSFODNN7EXAMPLE [^src-1]"
    redacted_text, flags = scan_and_redact(test_input, is_organization=True)

    print(f"Input:  {test_input}")
    print(f"Output: {redacted_text}")
    print(f"Flags:  {[(f.entity_type, f.matched_text, f.char_start, f.char_end) for f in flags]}")

    # 1. Verify 10.4.12.8 is INTERNAL_IP
    ip_flag = next((f for f in flags if f.matched_text == "10.4.12.8"), None)
    assert ip_flag is not None, "10.4.12.8 was not found in sensitive flags!"
    assert ip_flag.entity_type == "INTERNAL_IP", f"Expected INTERNAL_IP, got {ip_flag.entity_type}"
    expected_ip_span = '<span style="color: red; font-weight: bold;">[SENSITIVE: 10.4.12.8]</span>'
    assert expected_ip_span in redacted_text, f"Expected red span for IP not found: {expected_ip_span}"

    # 2. Verify AWS_SECRET_ACCESS_KEY is TACTICAL_KEYWORD
    kw_flag = next((f for f in flags if f.matched_text == "AWS_SECRET_ACCESS_KEY"), None)
    assert kw_flag is not None, "AWS_SECRET_ACCESS_KEY was not found in sensitive flags!"
    assert kw_flag.entity_type == "TACTICAL_KEYWORD", f"Expected TACTICAL_KEYWORD, got {kw_flag.entity_type}"
    expected_kw_span = '<span style="color: red; font-weight: bold;">[SENSITIVE: AWS_SECRET_ACCESS_KEY]</span>'
    assert expected_kw_span in redacted_text, f"Expected red span for keyword not found: {expected_kw_span}"

    # 3. Verify citation [^src-1] remains intact and untouched
    assert "[^src-1]" in redacted_text, "Citation [^src-1] was altered or removed!"
    assert "[SENSITIVE: [^src-1]]" not in redacted_text, "Citation [^src-1] was incorrectly wrapped!"
    assert "[SENSITIVE: src-1]" not in redacted_text, "Citation marker was incorrectly flagged!"

    # 4. Verify exact reconstructed string
    expected_redacted = f"Attacker accessed {expected_ip_span} and dumped {expected_kw_span}=AKIAIOSFODNN7EXAMPLE [^src-1]"
    assert redacted_text == expected_redacted, f"Mismatch in redacted text:\nGot:      {redacted_text}\nExpected: {expected_redacted}"

    print("✅ Test 1 PASSED: 10.4.12.8 is INTERNAL_IP, AWS_SECRET_ACCESS_KEY is TACTICAL_KEYWORD, [^src-1] intact.")


def test_2_wordlist_automaton():
    """
    Test 2: Wordlist Verification (300+ Keywords across 4 critical categories)
    """
    print("\n--- Running Test 2: Wordlist Automaton (300+ Keywords) ---")
    assert len(SENSITIVE_KEYWORDS) >= 300, f"Expected >= 300 keywords, found {len(SENSITIVE_KEYWORDS)}"
    print(f"Total verified tactical keywords: {len(SENSITIVE_KEYWORDS)}")

    # Check key operational requirements explicitly specified in task
    required_keywords = [
        "AWS_SECRET_ACCESS_KEY",
        "ROOT_PASSWORD",
        "SSH_PRIVATE_KEY",
        "id_rsa",
        "TOP SECRET",
        "NOFORN",
        "RESTRICTED OPERATION",
        "/etc/shadow",
        "SAM_HIVE",
    ]
    for req in required_keywords:
        assert req in SENSITIVE_KEYWORDS, f"Mandatory keyword '{req}' missing from wordlists!"

    sample_doc = (
        "Incident: AWS_SECRET_ACCESS_KEY exposed. Found ROOT_PASSWORD dump from /etc/shadow and SAM_HIVE. "
        "User id_rsa key exposed with SSH_PRIVATE_KEY. "
        "Marking: TOP SECRET and NOFORN. RESTRICTED OPERATION active."
    )
    redacted, flags = scan_and_redact(sample_doc, is_organization=True)
    matched_texts = {f.matched_text for f in flags}
    for req in required_keywords:
        assert req in matched_texts, f"Keyword '{req}' was not detected in sample doc!"

    print(f"Detected {len(flags)} sensitive keywords in multi-category sample.")
    print("✅ Test 2 PASSED: 300+ keyword list verified with required credentials, markings, and artifacts.")


def test_3_rfc1918_and_internal_domains():
    """
    Test 3: RFC 1918 Private IPv4 and Internal Domain Zones (.internal, .corp, .local, .ntro)
    """
    print("\n--- Running Test 3: RFC 1918 Private IPv4 & Internal Domains ---")
    test_text = (
        "Ingress from 10.24.1.8 and 192.168.1.55 via 172.16.8.99 to internal node 127.0.0.1. "
        "Targets: gw.ntro, bastion.corp, identity.internal, proxy.local. "
        "Public IP: 8.8.8.8 and public domain: google.com. "
        "Grounding citations: [^src-12] [^aud-3] [^doc-99]."
    )
    redacted, flags = scan_and_redact(test_text, is_organization=True)
    entity_map = {f.matched_text: f.entity_type for f in flags}

    # Verify RFC 1918 private IPs
    assert entity_map.get("10.24.1.8") == "INTERNAL_IP"
    assert entity_map.get("192.168.1.55") == "INTERNAL_IP"
    assert entity_map.get("172.16.8.99") == "INTERNAL_IP"
    assert entity_map.get("127.0.0.1") == "INTERNAL_IP"
    assert "8.8.8.8" not in entity_map, "Public IP 8.8.8.8 should not be flagged as internal!"

    # Verify internal domain zones
    assert entity_map.get("gw.ntro") == "INTERNAL_DOMAIN"
    assert entity_map.get("bastion.corp") == "INTERNAL_DOMAIN"
    assert entity_map.get("identity.internal") == "INTERNAL_DOMAIN"
    assert entity_map.get("proxy.local") == "INTERNAL_DOMAIN"
    assert "google.com" not in entity_map, "Public domain google.com should not be flagged!"

    # Verify citations intact
    assert "[^src-12]" in redacted
    assert "[^aud-3]" in redacted
    assert "[^doc-99]" in redacted

    print("✅ Test 3 PASSED: RFC 1918 IPs and internal domain zones accurately flagged while citations remain intact.")


def test_4_shannon_entropy():
    """
    Test 4: Shannon Entropy Calculation (H >= 4.2 for unquoted tokens >= 20 chars)
    """
    print("\n--- Running Test 4: Shannon Entropy Calculation ---")
    normal_token = "AutomotiveCyberSecurity"
    h_normal = calculate_shannon_entropy(normal_token)
    assert h_normal < 4.2, f"Expected entropy < 4.2 for English token, got: {h_normal:.2f}"

    secret_token = "9vK2mQ8xP4zR7wT1yU3iO5pA"  # 24 chars, high randomness
    h_secret = calculate_shannon_entropy(secret_token)
    assert h_secret >= 4.2, f"Expected entropy >= 4.2 for secret token, got: {h_secret:.2f}"

    text = f"Audit verified high-entropy API key: '{secret_token}' in source [^src-1]."
    redacted, flags = scan_and_redact(text, is_organization=True)

    secret_flag = next((f for f in flags if f.matched_text == secret_token), None)
    assert secret_flag is not None, "High entropy secret was not detected!"
    assert secret_flag.entity_type == "HIGH_ENTROPY_SECRET"
    assert f'<span style="color: red; font-weight: bold;">[SENSITIVE: {secret_token}]</span>' in redacted
    assert "[^src-1]" in redacted

    print(f"Entropy results: normal token '{normal_token}' = {h_normal:.2f}, secret token = {h_secret:.2f}")
    print("✅ Test 4 PASSED: Shannon entropy calculation and token flagging verified.")


def test_5_pure_python_trie_fallback():
    """
    Test 5: Pure-Python Trie Fallback when pyahocorasick is disabled
    """
    print("\n--- Running Test 5: Pure-Python Trie Fallback ---")
    orig_has = scanner_module.HAS_PYAHOCORASICK
    try:
        scanner_module.HAS_PYAHOCORASICK = False
        fallback_scanner = DeterministicSensitivityScanner()
        assert not fallback_scanner.matcher.use_c_extension, "Scanner did not switch to pure Python trie!"

        sample = "Target 10.4.12.8 exposed AWS_SECRET_ACCESS_KEY=AKIA123 [^src-5]"
        redacted, flags = fallback_scanner.scan_and_redact(sample)
        assert len(flags) == 2
        assert any(f.entity_type == "INTERNAL_IP" and f.matched_text == "10.4.12.8" for f in flags)
        assert any(f.entity_type == "TACTICAL_KEYWORD" and f.matched_text == "AWS_SECRET_ACCESS_KEY" for f in flags)
        assert "[^src-5]" in redacted
        print("✅ Test 5 PASSED: Pure-Python trie fallback functions identically to C-extension.")
    finally:
        scanner_module.HAS_PYAHOCORASICK = orig_has


def test_6_organization_mode_gating():
    """
    Test 6: Organization Mode Gating (is_organization=False vs is_organization=True)
    """
    print("\n--- Running Test 6: Organization Mode Gating ---")
    sample = "Internal IP 10.1.2.3 and ROOT_PASSWORD [^src-1]"

    # When is_organization=False: zero modifications, empty flags
    untouched, flags_off = scan_and_redact(sample, is_organization=False)
    assert untouched == sample, "Text should remain completely untouched when is_organization=False!"
    assert len(flags_off) == 0, f"Expected 0 flags when is_organization=False, got {len(flags_off)}"

    # When is_organization=True: scanned and redacted
    redacted, flags_on = scan_and_redact(sample, is_organization=True)
    assert redacted != sample, "Text should be redacted when is_organization=True!"
    assert len(flags_on) == 2, f"Expected 2 flags when is_organization=True, got {len(flags_on)}"
    assert "[SENSITIVE: 10.1.2.3]" in redacted
    assert "[SENSITIVE: ROOT_PASSWORD]" in redacted
    assert "[^src-1]" in redacted

    print("✅ Test 6 PASSED: Organization gating strictly enforces scan_and_redact activation.")


def test_7_sub_10ms_latency():
    """
    Test 7: Sub-10ms Deterministic Offline Performance
    """
    print("\n--- Running Test 7: Sub-10ms Latency Constraint ---")
    doc_template = """
    # THREAT ADVISORY: OPERATION SHADOWGATE
    Host: 10.100.4.15 and 192.168.10.12 accessed via CVE-2026-41822.
    Threat Actor obtained AWS_SECRET_ACCESS_KEY and ROOT_PASSWORD.
    Exfiltration to proxy.internal and C2 at bastion.ntro.
    Unquoted token: 9vK2mQ8xP4zR7wT1yU3iO5pA.
    Classification: TOP SECRET//NOFORN. RESTRICTED OPERATION underway.
    Artifacts found: /etc/shadow and SAM_HIVE dumped.
    References: [^src-1] [^src-2] [^aud-1] [^vid-2].
    """
    large_doc = doc_template * 15  # ~6.5 KB document

    # Warm-up run
    scan_and_redact(large_doc, is_organization=True)

    # Timed run
    start_time = time.perf_counter()
    redacted, flags = scan_and_redact(large_doc, is_organization=True)
    elapsed_ms = (time.perf_counter() - start_time) * 1000

    print(f"Document size: {len(large_doc)} characters")
    print(f"Sensitive flags detected: {len(flags)}")
    print(f"Execution time: {elapsed_ms:.3f} ms")

    assert elapsed_ms < 10.0, f"Performance exceeded 10ms threshold: {elapsed_ms:.3f} ms"
    assert "[^src-1]" in redacted
    assert "[^aud-1]" in redacted
    print(f"✅ Test 7 PASSED: Deterministic proofchecker ran in {elapsed_ms:.3f}ms (< 10ms target).")


if __name__ == "__main__":
    print("=" * 75)
    print("🛡️  TRANSMUTE — ENHANCEMENT 1 STANDALONE PROOFCHECKER VERIFICATION")
    print("=" * 75)

    test_1_primary_verification()
    test_2_wordlist_automaton()
    test_3_rfc1918_and_internal_domains()
    test_4_shannon_entropy()
    test_5_pure_python_trie_fallback()
    test_6_organization_mode_gating()
    test_7_sub_10ms_latency()

    print("\n" + "=" * 75)
    print("🎉 ALL 7 STANDALONE TESTS COMPLETED AND PASSED SUCCESSFULLY!")
    print("=" * 75)
