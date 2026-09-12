"""
Enhancement 1: Deterministic Sensitive Data Proofchecker.
Transmute System (SIH 2026 PS 26154)
"""

from typing import Tuple, List
from .scanner import (
    DeterministicSensitivityScanner,
    SensitiveDataFlag,
    calculate_shannon_entropy,
    _default_scanner,
)
from .wordlists import SENSITIVE_KEYWORDS, KALI_SECLISTS_KEYWORDS


def scan_and_redact(text: str, is_organization: bool = False) -> Tuple[str, List[SensitiveDataFlag]]:
    """
    Deterministic Sensitive Data Proofchecker ("Organisation" Mode).

    When is_organization is True, scans text for:
    - Layer 1: High-speed Kali/SecLists tactical keyword matches
    - Layer 2: RFC 1918 private IPv4 subnets, internal domains, secret tokens
    - Layer 3: High Shannon entropy secrets (H >= 4.2 for len >= 20)
    and wraps flagged spans in:
    <span style="color: red; font-weight: bold;">[SENSITIVE: <matched_value>]</span>
    Markdown citations like [^src-1] are guaranteed 100% intact.

    When is_organization is False, returns text untouched and an empty list.
    """
    if not is_organization or not text:
        return text or "", []
    return _default_scanner.scan_and_redact(text)


__all__ = [
    "scan_and_redact",
    "DeterministicSensitivityScanner",
    "SensitiveDataFlag",
    "calculate_shannon_entropy",
    "SENSITIVE_KEYWORDS",
    "KALI_SECLISTS_KEYWORDS",
]
