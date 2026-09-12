"""
Enhancement 1: Deterministic Sensitive Data Proofchecker.
Transmute System (SIH 2026 PS 26154)
"""

from typing import Tuple, List
from .scanner import (
    DeterministicSensitivityScanner,
    SensitiveDataFlag,
    calculate_shannon_entropy,
    strip_preview_wrappers,
    _default_scanner,
)
from .wordlists import SENSITIVE_KEYWORDS, KALI_SECLISTS_KEYWORDS


def scan_and_redact(
    text: str, is_organization: bool = False, wrap_html: bool = True
) -> Tuple[str, List[SensitiveDataFlag]]:
    """
    Deterministic Sensitive Data Proofchecker ("Organisation" Mode).

    When is_organization is True, scans text for:
    - Layer 1: High-speed Kali/SecLists tactical keyword matches
    - Layer 2: RFC 1918 private IPv4 subnets, internal domains, secret tokens
    - Layer 3: High Shannon entropy secrets (H >= 4.2 for len >= 20)
    and if wrap_html is True, wraps flagged spans in:
    <span style="color: red; font-weight: bold;">[SENSITIVE: <matched_value>]</span>
    Markdown citations like [^src-1] are guaranteed 100% intact.

    When wrap_html is False, text is left completely untouched (clean markdown)
    while returning the structured flags with character offsets.

    When is_organization is False, returns text untouched and an empty list.
    """
    if not is_organization or not text:
        return text or "", []
    return _default_scanner.scan_and_redact(text, wrap_html=wrap_html)


def scan(text: str) -> List[SensitiveDataFlag]:
    """Scan text and return detected sensitive flags without text modification."""
    return _default_scanner.scan(text)


__all__ = [
    "scan_and_redact",
    "scan",
    "strip_preview_wrappers",
    "DeterministicSensitivityScanner",
    "SensitiveDataFlag",
    "calculate_shannon_entropy",
    "SENSITIVE_KEYWORDS",
    "KALI_SECLISTS_KEYWORDS",
    "_default_scanner",
]
