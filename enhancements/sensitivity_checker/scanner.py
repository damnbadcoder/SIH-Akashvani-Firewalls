"""
Deterministic Sensitive Data Proofchecker Scanner.
Transmute System — Enhancement 1

Multi-layered offline scanner:
- Layer 1: High-Speed Multi-Keyword Automaton (Aho-Corasick with pure-Python trie fallback)
- Layer 2: Structured Regex Scanners (RFC 1918 IPv4, internal domains, secret tokens) + Defensive Citation Safeguards
- Layer 3: Shannon Entropy Calculation (H >= 4.2 for unquoted tokens >= 20 chars)
- Wrapping: Wraps flagged spans in <span style="color: red; font-weight: bold;">[SENSITIVE: <matched_value>]</span> in reverse character order.
"""

import re
import math
from collections import Counter, deque
from dataclasses import dataclass, asdict
from typing import Tuple, List, Optional, Dict, Any

try:
    import ahocorasick
    HAS_PYAHOCORASICK = True
except ImportError:
    ahocorasick = None
    HAS_PYAHOCORASICK = False

from .wordlists import KALI_SECLISTS_KEYWORDS


@dataclass
class SensitiveDataFlag:
    entity_type: str = "SENSITIVE_DATA"
    matched_text: str = ""
    char_start: int = 0
    char_end: int = 0
    severity: str = "HIGH"

    def model_dump(self) -> Dict[str, Any]:
        return asdict(self)

    def dict(self) -> Dict[str, Any]:
        return self.model_dump()

    @property
    def match(self) -> str:
        return self.matched_text

    @property
    def type(self) -> str:
        return self.entity_type

    @property
    def location(self) -> str:
        return f"[{self.char_start}:{self.char_end}]"


# =============================================================================
# Pure-Python Aho-Corasick Trie Fallback
# =============================================================================
class _AhoNode:
    __slots__ = ("children", "fail", "outputs")

    def __init__(self):
        self.children = {}
        self.fail = None
        self.outputs = []  # List of (keyword, entity_type)


class PurePythonAhoCorasick:
    """High-speed pure-Python Aho-Corasick automaton."""

    def __init__(self):
        self.root = _AhoNode()
        self._built = False

    def add_keyword(self, keyword: str, entity_type: str = "TACTICAL_KEYWORD"):
        node = self.root
        for ch in keyword.lower():
            if ch not in node.children:
                node.children[ch] = _AhoNode()
            node = node.children[ch]
        node.outputs.append((keyword, entity_type))
        self._built = False

    def build(self):
        queue = deque()
        for ch, child in self.root.children.items():
            child.fail = self.root
            queue.append(child)

        while queue:
            curr = queue.popleft()
            for ch, child in curr.children.items():
                queue.append(child)
                fail_node = curr.fail
                while fail_node is not None and ch not in fail_node.children:
                    fail_node = fail_node.fail
                child.fail = fail_node.children[ch] if fail_node else self.root
                if child.fail.outputs:
                    child.outputs.extend(child.fail.outputs)
        self._built = True

    def search(self, text: str):
        if not self._built:
            self.build()
        curr = self.root
        text_lower = text.lower()
        for idx, ch in enumerate(text_lower):
            while curr is not None and ch not in curr.children:
                curr = curr.fail
            curr = curr.children[ch] if curr else self.root
            if curr.outputs:
                for kw, entity_type in curr.outputs:
                    start = idx - len(kw) + 1
                    end = idx + 1
                    yield (start, end, text[start:end], entity_type)


class AhoCorasickMatcher:
    """Wrapper that chooses C-extension pyahocorasick if available, else pure-Python trie."""

    def __init__(self):
        self.use_c_extension = HAS_PYAHOCORASICK
        if self.use_c_extension:
            self.automaton = ahocorasick.Automaton()
        else:
            self.automaton = PurePythonAhoCorasick()
        self._built = False

    def add_keyword(self, keyword: str, entity_type: str = "TACTICAL_KEYWORD"):
        if self.use_c_extension:
            self.automaton.add_word(keyword.lower(), (keyword, entity_type))
        else:
            self.automaton.add_keyword(keyword, entity_type)
        self._built = False

    def build(self):
        if self.use_c_extension:
            self.automaton.make_automaton()
        else:
            self.automaton.build()
        self._built = True

    def search(self, text: str):
        if not self._built:
            self.build()
        if self.use_c_extension:
            text_lower = text.lower()
            for end_idx, (kw, entity_type) in self.automaton.iter(text_lower):
                start = end_idx - len(kw) + 1
                end = end_idx + 1
                yield (start, end, text[start:end], entity_type)
        else:
            yield from self.automaton.search(text)


# =============================================================================
# Helper Utilities
# =============================================================================
def _is_word_boundary(text: str, start: int, end: int) -> bool:
    """Check if substring match is properly bounded to avoid mid-word false positives."""
    if text[start].isalnum() or text[start] == "_":
        if start > 0 and (text[start - 1].isalnum() or text[start - 1] == "_"):
            return False
    if text[end - 1].isalnum() or text[end - 1] == "_":
        if end < len(text) and (text[end].isalnum() or text[end] == "_"):
            return False
    return True


def _is_valid_ipv4(ip_str: str) -> bool:
    """Verify that all octets are integers between 0 and 255."""
    parts = ip_str.split(".")
    if len(parts) != 4:
        return False
    try:
        return all(0 <= int(part) <= 255 for part in parts)
    except ValueError:
        return False


# Regex to protect citation markers like [^src-1], [^aud-2], [^vid-3], [^doc-4], [^fact-5]
CITATION_REGEX = re.compile(r"\[\^(?:src|aud|vid|doc|fact|[a-zA-Z0-9_\-]+)\]", re.IGNORECASE)

# Regex to identify already-wrapped sensitive spans
EXISTING_WRAPPER_REGEX = re.compile(
    r'<span style="color: red; font-weight: bold;">\[SENSITIVE:[^\]]+\]</span>|\[SENSITIVE:[^\]]+\]',
    re.IGNORECASE,
)

# Standalone citation tokens that should never be flagged
SAFE_CITATION_TOKEN_REGEX = re.compile(r"^(?:src|aud|vid|doc|fact|[a-zA-Z0-9_\-]+)-\d+$", re.IGNORECASE)


# =============================================================================
# Deterministic Sensitivity Scanner
# =============================================================================
class DeterministicSensitivityScanner:
    """
    Multi-stage deterministic sensitive data scanner:
    - Layer 1: High-Speed Multi-Keyword Automaton (Aho-Corasick)
    - Layer 2: Structured Regex Scanners (RFC 1918 Private IPv4, Internal Domains, Secret Tokens)
    - Layer 3: Shannon Entropy Calculation (H >= 4.2 for unquoted tokens >= 20 chars)
    """

    def __init__(self):
        # Layer 1: Aho-Corasick Pattern Matcher
        self.matcher = AhoCorasickMatcher()
        for kw in KALI_SECLISTS_KEYWORDS:
            self.matcher.add_keyword(kw, "TACTICAL_KEYWORD")
        self.matcher.build()

        # Layer 2: Structured Regex Scanners
        self.rfc1918_regex = re.compile(
            r"\b(10\.\d{1,3}\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|127\.\d{1,3}\.\d{1,3}\.\d{1,3})\b"
        )
        self.internal_domain_regex = re.compile(
            r"\b([a-zA-Z0-9_\-\.]+\.(?:internal|local|corp|ntro|lan|intranet))\b",
            re.IGNORECASE,
        )
        self.secret_token_regex = re.compile(
            r"\b([a-zA-Z0-9_\-]{32,64})\b"
        )
        self.header_secret_regex = re.compile(
            r"(?i)\b(?:bearer|token|secret|session|key|auth|api[_-]?key|auth[_-]?token)\s*[:=]\s*[\"']?([a-zA-Z0-9_\-]{32,64})[\"']?"
        )
        self.db_conn_regex = re.compile(
            r"(?:postgresql|mysql|mongodb|redis)://[^:\s]+:[^@\s]+@[^/\s]+"
        )
        self.exploit_regex = re.compile(
            r"(?:\\x[0-9a-fA-F]{2}){4,}|\b(?:curl|wget)\s+[^|\n]+(?:\|\s*(?:bash|sh))\b"
        )
        self.internal_pii_regex = re.compile(
            r"\b(EMP-[0-9]{4,8}|UID-[0-9]{4,8})\b"
        )

        # Layer 3: Standalone alphanumeric tokens for Shannon entropy evaluation
        self.alphanumeric_candidate_regex = re.compile(r"\b([a-zA-Z0-9]{20,})\b")

    @staticmethod
    def calculate_shannon_entropy(token: str) -> float:
        """
        Calculate Shannon entropy of a string:
        H(X) = - sum(p(x) * log2(p(x)))
        """
        if not token:
            return 0.0
        # Strip outer quotes if any
        token = token.strip("'\"")
        if not token:
            return 0.0
        length = len(token)
        counts = Counter(token)
        return -sum((count / length) * math.log2(count / length) for count in counts.values())

    def _get_protected_spans(self, text: str) -> List[Tuple[int, int]]:
        """Identify spans that must never be modified (citations, already wrapped markers)."""
        protected = []
        for m in CITATION_REGEX.finditer(text):
            protected.append((m.start(), m.end()))
        for m in EXISTING_WRAPPER_REGEX.finditer(text):
            protected.append((m.start(), m.end()))
        return protected

    def _overlaps_any(self, start: int, end: int, spans: List[Tuple[int, int]]) -> bool:
        """Check if [start, end) intersects any range in spans."""
        for s, e in spans:
            if max(start, s) < min(end, e):
                return True
        return False

    def scan(self, text: str) -> List[SensitiveDataFlag]:
        """Scan text and return detected sensitive flags without text modification."""
        _, flags = self.scan_and_redact(text)
        return flags

    def scan_and_redact(self, text: str) -> Tuple[str, List[SensitiveDataFlag]]:
        """
        Scan text for sensitive data patterns and wrap matches in red HTML spans:
        <span style="color: red; font-weight: bold;">[SENSITIVE: <matched_value>]</span>

        Guarantees:
        - Citations ([^src-X], [^aud-X]) are 100% untouched.
        - Sub-10ms deterministic execution.
        - Idempotent: already-wrapped items are not double-wrapped.
        - Deduplicated non-overlapping flagged spans.
        """
        if not text:
            return text or "", []

        protected_spans = self._get_protected_spans(text)
        candidates = []  # List of (start, end, entity_type, matched_text, priority)

        # ─────────────────────────────────────────────────────────────────
        # Layer 1: High-Speed Multi-Keyword Automaton (Aho-Corasick)
        # Priority: 1 (Highest keyword priority)
        # ─────────────────────────────────────────────────────────────────
        for start, end, matched_text, entity_type in self.matcher.search(text):
            if self._overlaps_any(start, end, protected_spans):
                continue
            if SAFE_CITATION_TOKEN_REGEX.match(matched_text):
                continue
            if not _is_word_boundary(text, start, end):
                continue
            candidates.append((start, end, entity_type, matched_text, 1))

        # ─────────────────────────────────────────────────────────────────
        # Layer 2: Structured Regex Scanners
        # Priority: 2
        # ─────────────────────────────────────────────────────────────────
        # 2a. RFC 1918 Private IPv4
        for m in self.rfc1918_regex.finditer(text):
            start, end = m.span()
            matched_text = m.group(0)
            if self._overlaps_any(start, end, protected_spans):
                continue
            if not _is_valid_ipv4(matched_text):
                continue
            candidates.append((start, end, "INTERNAL_IP", matched_text, 2))

        # 2b. Internal Domain Zones
        for m in self.internal_domain_regex.finditer(text):
            start, end = m.span()
            matched_text = m.group(0)
            if self._overlaps_any(start, end, protected_spans):
                continue
            candidates.append((start, end, "INTERNAL_DOMAIN", matched_text, 2))

        # 2c. Header Secret Tokens & Hex Hashes
        for m in self.header_secret_regex.finditer(text):
            token = m.group(1)
            start = m.start(1)
            end = m.end(1)
            if self._overlaps_any(start, end, protected_spans):
                continue
            if SAFE_CITATION_TOKEN_REGEX.match(token):
                continue
            candidates.append((start, end, "SECRET_TOKEN", token, 2))

        for m in self.secret_token_regex.finditer(text):
            start, end = m.span()
            token = m.group(0)
            if self._overlaps_any(start, end, protected_spans):
                continue
            if SAFE_CITATION_TOKEN_REGEX.match(token):
                continue
            # Check if token is hex hash or has high entropy (>= 3.8)
            is_hex = bool(re.fullmatch(r"[0-9a-fA-F]{32,64}", token))
            if is_hex or self.calculate_shannon_entropy(token) >= 3.8:
                candidates.append((start, end, "SECRET_TOKEN", token, 2))

        # 2d. Database Connection Strings
        for m in self.db_conn_regex.finditer(text):
            start, end = m.span()
            matched_text = m.group(0)
            if self._overlaps_any(start, end, protected_spans):
                continue
            candidates.append((start, end, "DB_CONNECTION_STRING", matched_text, 2))

        # 2e. Exploit Payloads
        for m in self.exploit_regex.finditer(text):
            start, end = m.span()
            matched_text = m.group(0)
            if self._overlaps_any(start, end, protected_spans):
                continue
            candidates.append((start, end, "EXPLOIT_PAYLOAD", matched_text, 2))

        # 2f. Internal PII
        for m in self.internal_pii_regex.finditer(text):
            start, end = m.span()
            matched_text = m.group(0)
            if self._overlaps_any(start, end, protected_spans):
                continue
            candidates.append((start, end, "INTERNAL_PII", matched_text, 2))

        # ─────────────────────────────────────────────────────────────────
        # Layer 3: Shannon Entropy Calculation
        # Priority: 3
        # Flag unquoted alphanumeric tokens of length >= 20 with H(X) >= 4.2
        # ─────────────────────────────────────────────────────────────────
        for m in self.alphanumeric_candidate_regex.finditer(text):
            token = m.group(0)
            start, end = m.span()
            if self._overlaps_any(start, end, protected_spans):
                continue
            if SAFE_CITATION_TOKEN_REGEX.match(token):
                continue
            clean_token = token.strip("'\"")
            if len(clean_token) < 20:
                continue
            entropy = self.calculate_shannon_entropy(clean_token)
            if entropy >= 4.2:
                candidates.append((start, end, "HIGH_ENTROPY_SECRET", token, 3))

        # ─────────────────────────────────────────────────────────────────
        # Overlap Resolution & Deduplication
        # Longer matches take precedence, followed by priority (Layer 1 > Layer 2 > Layer 3)
        # ─────────────────────────────────────────────────────────────────
        sorted_candidates = sorted(
            candidates, key=lambda c: (-(c[1] - c[0]), c[4], c[0])
        )

        selected_spans = []
        for cand in sorted_candidates:
            start, end, entity_type, matched_text, prio = cand
            overlap = False
            for s_start, s_end, _, _, _ in selected_spans:
                if max(start, s_start) < min(end, s_end):
                    overlap = True
                    break
            if not overlap:
                selected_spans.append(cand)

        selected_spans.sort(key=lambda c: c[0])

        flags: List[SensitiveDataFlag] = [
            SensitiveDataFlag(
                entity_type=etype,
                matched_text=mtext,
                char_start=start,
                char_end=end,
                severity="HIGH",
            )
            for start, end, etype, mtext, _ in selected_spans
        ]

        # ─────────────────────────────────────────────────────────────────
        # In-Place Text Wrapping in reverse order to preserve character offsets
        # ─────────────────────────────────────────────────────────────────
        redacted_text = text
        for start, end, _, matched_text, _ in sorted(
            selected_spans, key=lambda c: c[0], reverse=True
        ):
            wrapper = f'<span style="color: red; font-weight: bold;">[SENSITIVE: {matched_text}]</span>'
            redacted_text = redacted_text[:start] + wrapper + redacted_text[end:]

        return redacted_text, flags


# Global default scanner instance
_default_scanner = DeterministicSensitivityScanner()


def calculate_shannon_entropy(token: str) -> float:
    """Module-level helper to calculate Shannon entropy."""
    return DeterministicSensitivityScanner.calculate_shannon_entropy(token)
