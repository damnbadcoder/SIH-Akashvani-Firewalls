"""
Semantic Anchor Re-Linker (User Edit Protection Engine).
Transmute System — Enhancement 3

When an operator edits or paraphrases sentences in the frontend preview,
citation anchors ([^src-X], [^aud-X]) are frequently deleted or misplaced.
This engine compares the modified text against the original approved draft,
detects paraphrased sentences using semantic token overlap and Jaccard similarity,
and re-injects the missing citation anchors to preserve 100% provenance integrity.
"""

import re
import difflib
from typing import List, Tuple, Dict, Set, Optional
from .types import RelinkMatch, RelinkResult

CITATION_REGEX = re.compile(
    r"\[\^(?:src|aud|img|vid|doc|fact|[a-zA-Z0-9_\-]+)-\d+\]", re.IGNORECASE
)

# Semantic domain clusters for robust paraphrase detection
SYNONYM_CLUSTERS: List[Set[str]] = [
    {
        "stakeholder", "stakeholders", "participant", "participants", "attendee",
        "attendees", "member", "members", "delegate", "delegates", "representative",
        "representatives", "user", "users"
    },
    {
        "workshop", "session", "conference", "meeting", "seminar", "summit",
        "gathering", "forum", "event", "roundtable", "symposium"
    },
    {
        "join", "joined", "attend", "attended", "participate", "participated",
        "convene", "convened", "gather", "gathered"
    },
    {
        "organize", "organized", "host", "hosted", "hold", "held", "conduct",
        "conducted", "coordinate", "coordinated", "arrange", "arranged", "facilitate"
    },
    {
        "cybersecurity", "security", "infosec", "cyber", "defensive"
    },
    {
        "automotive", "vehicle", "in-vehicle", "car", "connected-vehicle", "ecu",
        "telemetry", "can-bus"
    },
    {
        "vulnerability", "flaw", "weakness", "bug", "defect", "cve", "exposure"
    },
    {
        "attack", "exploit", "breach", "intrusion", "compromise", "hack", "incident"
    },
    {
        "mitigate", "remediate", "patch", "fix", "resolve", "defend", "protect"
    },
    {
        "exfiltrate", "dump", "steal", "leak", "extract", "harvest"
    },
    {
        "malware", "implant", "payload", "beacon", "trojan", "backdoor", "rootkit"
    },
    {
        "actor", "adversary", "threat-actor", "group", "collective", "syndicate"
    },
    {
        "controller", "node", "endpoint", "host", "server", "device", "asset", "system"
    },
]

# Map each synonym to a canonical cluster representation
_SYNONYM_MAP: Dict[str, str] = {}
for cluster in SYNONYM_CLUSTERS:
    canonical = sorted(cluster)[0]
    for word in cluster:
        _SYNONYM_MAP[word.lower()] = canonical


def _stem_word(word: str) -> str:
    """Lightweight rule-based suffix stemming."""
    w = word.lower()
    for suffix in ("ing", "tion", "sion", "ment", "ness", "able", "ible", "ed", "es", "s", "d"):
        if len(w) > len(suffix) + 3 and w.endswith(suffix):
            return w[:-len(suffix)]
    return w


def _extract_normalized_tokens(text: str) -> List[str]:
    """Strip citation markers and extract normalized, stemmed semantic tokens."""
    clean_text = CITATION_REGEX.sub("", text)
    words = re.findall(r"\b[a-zA-Z0-9]+(?:-[a-zA-Z0-9]+)*\b", clean_text.lower())
    tokens = []
    for w in words:
        mapped = _SYNONYM_MAP.get(w, w)
        stemmed = _stem_word(mapped)
        tokens.append(stemmed)
    return tokens


def _append_citation(sentence: str, marker_str: str) -> str:
    """Append citation marker to the end of a sentence before trailing punctuation."""
    m = re.search(r"([.!?]+)\s*$", sentence)
    if m:
        core = sentence[:m.start()].rstrip()
        punct = m.group(1)
        return f"{core} {marker_str}{punct}"
    return f"{sentence.rstrip()} {marker_str}"


class SemanticAnchorRelinker:
    """
    User Edit Protection Engine.
    Detects rephrased / edited sentences and re-links dropped citation markers.
    """

    def __init__(self):
        pass

    @staticmethod
    def compute_similarity(s1: str, s2: str) -> float:
        """
        Computes semantic similarity between two sentences using token Jaccard similarity
        with synonym clustering, stemming, and SequenceMatcher.
        Returns a score between 0.0 and 1.0.
        """
        t1 = set(_extract_normalized_tokens(s1))
        t2 = set(_extract_normalized_tokens(s2))
        if not t1 or not t2:
            return 0.0

        common = t1.intersection(t2)
        if not common:
            return 0.0

        jaccard = len(common) / len(t1.union(t2))

        # Directional containment: fraction of smaller sentence tokens contained
        directional = len(common) / min(len(t1), len(t2))

        # If significant word overlap, check difflib SequenceMatcher
        if len(common) >= 3:
            s1_clean = CITATION_REGEX.sub("", s1).strip().lower()
            s2_clean = CITATION_REGEX.sub("", s2).strip().lower()
            seq_ratio = difflib.SequenceMatcher(None, s1_clean, s2_clean).ratio()
            score = max(jaccard, seq_ratio, directional * 0.75)
        else:
            score = jaccard

        return round(max(0.0, min(1.0, score)), 4)

    def relink(
        self, edited_text: str, original_text: str, threshold: float = 0.55
    ) -> RelinkResult:
        """
        Re-attaches dropped citation tags onto edited text.
        Preserves original line breaks, headings, and bullet structures.
        """
        if not edited_text or not original_text:
            return RelinkResult(
                relinked_text=edited_text or "",
                relinked_count=0,
                matches=[]
            )

        # ── Step 1: Parse original_text into cited sentences ──
        orig_cited_sentences = self._extract_cited_sentences(original_text)
        if not orig_cited_sentences:
            return RelinkResult(
                relinked_text=edited_text,
                relinked_count=0,
                matches=[]
            )

        # ── Step 2: Check which citations are already present in edited_text ──
        existing_markers_in_edited = set(CITATION_REGEX.findall(edited_text))

        # Filter out cited sentences whose markers are already completely retained
        missing_candidates = []
        for orig_sent, markers in orig_cited_sentences:
            dropped_markers = [m for m in markers if m not in existing_markers_in_edited]
            if dropped_markers:
                missing_candidates.append({
                    "original_sentence": orig_sent,
                    "clean_sentence": CITATION_REGEX.sub("", orig_sent).strip(),
                    "markers": dropped_markers,
                })

        if not missing_candidates:
            # All citations already present in edited text
            return RelinkResult(
                relinked_text=edited_text,
                relinked_count=0,
                matches=[]
            )

        # ── Step 3 & 4: Process edited_text while preserving markdown structure ──
        relinked_matches: List[RelinkMatch] = []
        allocated_markers: Set[str] = set()
        relinked_lines: List[str] = []

        lines = edited_text.splitlines(keepends=True)

        for line in lines:
            # Check if line has content
            line_stripped = line.strip()
            if not line_stripped or line_stripped.startswith("#"):
                # Blank lines or headings: keep as-is
                relinked_lines.append(line)
                continue

            # Check for bullet or list prefix (e.g., "- ", "* ", "1. ", or indentation)
            prefix_match = re.match(r"^(\s*[-*+]\s+|\s*\d+\.\s+)", line)
            if prefix_match:
                prefix = prefix_match.group(1)
                line_content = line[len(prefix):]
            else:
                prefix = ""
                line_content = line

            # Determine line ending (e.g., "\n" or "\r\n")
            ending_match = re.search(r"(\r?\n)$", line_content)
            if ending_match:
                line_ending = ending_match.group(1)
                body = line_content[:-len(line_ending)]
            else:
                line_ending = ""
                body = line_content

            # Split line body into sentences
            raw_sentences = self._split_into_sentences(body)
            processed_sentences: List[str] = []

            for sent in raw_sentences:
                sent_clean = sent.strip()
                if not sent_clean:
                    processed_sentences.append(sent)
                    continue

                # Invariant 5: If sentence already contains a citation tag, leave untouched
                if CITATION_REGEX.search(sent_clean):
                    processed_sentences.append(sent)
                    continue

                # Find best matching missing candidate
                best_cand = None
                best_score = 0.0

                for cand in missing_candidates:
                    # Check if candidate has markers not yet allocated
                    available_markers = [
                        m for m in cand["markers"]
                        if m not in allocated_markers and m not in existing_markers_in_edited
                    ]
                    if not available_markers:
                        continue

                    score = self.compute_similarity(cand["clean_sentence"], sent_clean)
                    if score > best_score:
                        best_score = score
                        best_cand = cand

                if best_cand is not None and best_score >= threshold:
                    available_markers = [
                        m for m in best_cand["markers"]
                        if m not in allocated_markers and m not in existing_markers_in_edited
                    ]
                    if available_markers:
                        markers_str = " ".join(available_markers)
                        relinked_sent = _append_citation(sent, markers_str)
                        processed_sentences.append(relinked_sent)

                        for m in available_markers:
                            allocated_markers.add(m)

                        relinked_matches.append(
                            RelinkMatch(
                                original_sentence=best_cand["original_sentence"],
                                edited_sentence=sent_clean,
                                citation_marker=markers_str,
                                similarity_score=best_score,
                                relinked=True,
                            )
                        )
                        continue

                # No match >= threshold or no available markers
                processed_sentences.append(sent)

            # Reconstruct line
            relinked_body = " ".join(s for s in processed_sentences if s)
            relinked_lines.append(f"{prefix}{relinked_body}{line_ending}")

        relinked_text = "".join(relinked_lines)

        return RelinkResult(
            relinked_text=relinked_text,
            relinked_count=len(relinked_matches),
            matches=relinked_matches,
        )

    def _extract_cited_sentences(self, text: str) -> List[Tuple[str, List[str]]]:
        """Extract all sentences from text that contain citation markers."""
        cited_sentences: List[Tuple[str, List[str]]] = []
        lines = text.splitlines()

        for line in lines:
            line_clean = line.strip()
            if not line_clean or not CITATION_REGEX.search(line_clean):
                continue

            # Strip list/bullet prefixes
            body = re.sub(r"^(\s*[-*+]\s+|\s*\d+\.\s+)", "", line_clean)
            sentences = self._split_into_sentences(body)

            for sent in sentences:
                markers = CITATION_REGEX.findall(sent)
                if markers:
                    cited_sentences.append((sent.strip(), markers))

        return cited_sentences

    @staticmethod
    def _split_into_sentences(text: str) -> List[str]:
        """Splits a single paragraph or line into constituent sentences."""
        if not text:
            return []
        # Split on [.!?] followed by whitespace and uppercase/bracket/digit, or end of string
        sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[])", text)
        return [s.strip() for s in sentences if s.strip()]


_default_relinker = SemanticAnchorRelinker()
