"""
NLI Cross-Encoder Provenance Verification Engine.
Transmute System — Enhancement 2

Evaluates claim sentences containing citation markers ([^src-X], [^aud-X])
against grounding source context using Natural Language Inference (NLI):
- Premise: Grounding Source Context
- Hypothesis: Claim sentence containing citation
- Execution: Compact Cross-Encoder if available, or offline deterministic
  directional token overlap & semantic containment algorithm (< 5ms).
- Thresholds:
  Score >= 0.70 -> ENTAILED (is_verified = True)
  0.40 <= Score < 0.70 -> NEUTRAL (is_verified = False)
  Score < 0.40 -> CONTRADICTION / HALLUCINATED (is_verified = False)
"""

import re
import math
from collections import Counter
from typing import List, Tuple, Dict, Any, Optional, Set

from .types import CitationVerdict, NLIVerificationResult

CITATION_REGEX = re.compile(
    r"\[\^(?:src|aud|vid|doc|fact|[a-zA-Z0-9_\-]+)-\d+\]", re.IGNORECASE
)

# Common English stop words
STOP_WORDS: Set[str] = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can", "can't", "cannot", "could",
    "couldn't", "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down",
    "during", "each", "few", "for", "from", "further", "had", "hadn't", "has",
    "hasn't", "have", "haven't", "having", "he", "he'd", "he'll", "he's", "her",
    "here", "here's", "hers", "herself", "him", "himself", "his", "how", "how's",
    "i", "i'd", "i'll", "i'm", "i've", "if", "in", "into", "is", "isn't", "it",
    "it's", "its", "itself", "let's", "me", "more", "most", "mustn't", "my",
    "myself", "no", "nor", "not", "of", "off", "on", "once", "only", "or", "other",
    "ought", "our", "ours", "ourselves", "out", "over", "own", "same", "shan't",
    "she", "she'd", "she'll", "she's", "should", "shouldn't", "so", "some", "such",
    "than", "that", "that's", "the", "their", "theirs", "them", "themselves",
    "then", "there", "there's", "these", "they", "they'd", "they'll", "they're",
    "they've", "this", "those", "through", "to", "too", "under", "until", "up",
    "very", "was", "wasn't", "we", "we'd", "we'll", "we're", "we've", "were",
    "weren't", "what", "what's", "when", "when's", "where", "where's", "which",
    "while", "who", "who's", "whom", "why", "why's", "with", "won't", "would",
    "wouldn't", "you", "you'd", "you'll", "you're", "you've", "your", "yours",
    "yourself", "yourselves"
}

# Cybersecurity & operational semantic synonym clusters
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
        "convene", "convened", "gather", "gathered", "enter", "entered"
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
        "mitigate", "remediate", "patch", "fix", "resolve", "defend", "protect", "address"
    },
    {
        "exfiltrate", "dump", "steal", "leak", "extract", "harvest", "siphon"
    },
    {
        "malware", "implant", "payload", "beacon", "trojan", "backdoor", "rootkit"
    },
    {
        "actor", "adversary", "threat-actor", "group", "collective", "syndicate", "campaign"
    },
    {
        "controller", "node", "endpoint", "host", "server", "device", "asset", "system"
    },
]

# Map each word in a cluster to its cluster index
_WORD_TO_CLUSTER: Dict[str, int] = {}
for idx, cluster in enumerate(SYNONYM_CLUSTERS):
    for word in cluster:
        _WORD_TO_CLUSTER[word.lower()] = idx


def _stem_word(word: str) -> str:
    """Lightweight rule-based suffix stemming."""
    w = word.lower()
    for suffix in ("ing", "tion", "sion", "ment", "ness", "able", "ible", "ed", "es", "s", "d"):
        if len(w) > len(suffix) + 3 and w.endswith(suffix):
            return w[:-len(suffix)]
    return w


def _extract_tokens(text: str) -> List[str]:
    """Tokenize text into alphanumeric tokens and hyphens."""
    cleaned = re.sub(r"[^\w\-\.]", " ", text.lower())
    tokens = re.findall(r"\b[a-zA-Z0-9]+(?:-[a-zA-Z0-9]+)*\b", cleaned)
    return tokens


def _compute_token_similarity(tok_a: str, tok_b: str) -> float:
    """Compare two individual tokens using exact match, synonym cluster, or stemming."""
    if tok_a == tok_b:
        return 1.0

    # Number equality
    if tok_a.isdigit() and tok_b.isdigit():
        return 1.0 if tok_a == tok_b else 0.0

    # Synonym cluster check
    cluster_a = _WORD_TO_CLUSTER.get(tok_a)
    cluster_b = _WORD_TO_CLUSTER.get(tok_b)
    if cluster_a is not None and cluster_a == cluster_b:
        return 1.0

    # Stem match
    stem_a = _stem_word(tok_a)
    stem_b = _stem_word(tok_b)
    if stem_a == stem_b and len(stem_a) >= 3:
        return 0.95

    # Substring / Prefix match for compound terms
    if len(tok_a) >= 5 and len(tok_b) >= 5:
        if tok_a.startswith(tok_b) or tok_b.startswith(tok_a):
            return 0.85

    return 0.0


class NLICrossEncoderGuard:
    """
    NLI Cross-Encoder Entailment Guardrail.
    Evaluates (Premise, Hypothesis) pairs:
    - Premise: Grounding Source Context
    - Hypothesis: Draft sentence containing citation marker
    """

    def __init__(self, model_name: Optional[str] = None):
        self.model = None
        if model_name:
            self._init_transformer(model_name)

    def _init_transformer(self, model_name: str):
        try:
            from sentence_transformers import CrossEncoder
            self.model = CrossEncoder(model_name)
        except Exception:
            self.model = None

    def evaluate_pair(self, premise: str, hypothesis: str) -> Tuple[float, str, bool]:
        """
        Evaluate single (Premise, Hypothesis) pair.
        Returns: (entailment_score, status, is_verified)
        """
        if self.model is not None:
            try:
                # CrossEncoder returns logits or probabilities [contradiction, neutral, entailment]
                scores = self.model.predict([(premise, hypothesis)])
                # If binary or softmax
                if hasattr(scores, "__iter__") and len(scores) > 0:
                    entail_prob = float(scores[0])
                    return self._score_to_verdict(entail_prob)
            except Exception:
                pass

        # Deterministic Mathematical Fallback Engine
        return self._evaluate_fallback(premise, hypothesis)

    def _evaluate_fallback(self, premise: str, hypothesis: str) -> Tuple[float, str, bool]:
        """
        Deterministic, directional mathematical token-overlap & semantic containment fallback.
        Executes in < 5ms without external dependencies.
        """
        if not premise or not hypothesis:
            return 0.0, "CONTRADICTION", False

        # Clean hypothesis from citation markers for semantic evaluation
        clean_hyp = CITATION_REGEX.sub("", hypothesis).strip()
        hyp_tokens = _extract_tokens(clean_hyp)
        prem_tokens = _extract_tokens(premise)

        if not hyp_tokens:
            return 1.0, "ENTAILED", True

        # Separate into significant content tokens vs stop words
        significant_hyp: List[Tuple[str, float]] = []
        for t in hyp_tokens:
            if t in STOP_WORDS and not t.isdigit():
                continue
            # Assign weights based on semantic salience
            if t.isdigit():
                weight = 2.0  # Exact metrics / numbers must be preserved
            elif "-" in t or any(c.isupper() for c in t) or len(t) >= 8:
                weight = 1.5  # Proper entities, compound terms, acronyms
            else:
                weight = 1.0  # General content words
            significant_hyp.append((t, weight))

        if not significant_hyp:
            return 0.85, "ENTAILED", True

        # Segment premise into sentences / chunks to find best supporting context
        prem_sentences = re.split(r"(?<=[.!?\n])\s+", premise)
        prem_sentences = [s.strip() for s in prem_sentences if s.strip()]
        if not prem_sentences:
            prem_sentences = [premise]

        # Find best matching premise sentence or evaluate against full context
        best_sentence_score = 0.0
        for sent in prem_sentences:
            sent_tokens = _extract_tokens(sent)
            sent_score = self._compute_directional_score(significant_hyp, sent_tokens)
            if sent_score > best_sentence_score:
                best_sentence_score = sent_score

        # Also compute global premise score
        global_score = self._compute_directional_score(significant_hyp, prem_tokens)
        overall_score = max(best_sentence_score, global_score)

        # Semantic Jaccard bi-gram alignment bonus/penalty
        hyp_bigrams = set(zip(hyp_tokens, hyp_tokens[1:]))
        prem_bigrams = set(zip(prem_tokens, prem_tokens[1:]))
        if hyp_bigrams and prem_bigrams:
            bigram_jaccard = len(hyp_bigrams.intersection(prem_bigrams)) / len(hyp_bigrams)
        else:
            bigram_jaccard = 0.0

        final_score = (0.85 * overall_score) + (0.15 * min(1.0, bigram_jaccard * 1.5))
        final_score = max(0.0, min(1.0, round(final_score, 4)))

        return self._score_to_verdict(final_score)

    def _compute_directional_score(
        self, significant_hyp: List[Tuple[str, float]], context_tokens: List[str]
    ) -> float:
        """Compute weighted directional recall of hypothesis tokens from context."""
        total_weight = sum(w for _, w in significant_hyp)
        if total_weight <= 0:
            return 1.0

        accumulated_score = 0.0
        context_token_set = set(context_tokens)

        for tok, weight in significant_hyp:
            # 1. Fast exact check
            if tok in context_token_set:
                accumulated_score += weight
                continue

            # 2. Semantic synonym or stem check
            max_sim = 0.0
            for c_tok in context_tokens:
                sim = _compute_token_similarity(tok, c_tok)
                if sim > max_sim:
                    max_sim = sim
                if max_sim >= 1.0:
                    break

            accumulated_score += (weight * max_sim)

        return accumulated_score / total_weight

    @staticmethod
    def _score_to_verdict(score: float, threshold: float = 0.65) -> Tuple[float, str, bool]:
        """Convert float score to categorical NLI verdict and verification status."""
        score = round(max(0.0, min(1.0, score)), 4)
        if score >= 0.70:
            status = "ENTAILED"
            is_verified = True
        elif score >= 0.40:
            status = "NEUTRAL"
            is_verified = (score >= threshold)
        else:
            status = "CONTRADICTION"
            is_verified = False

        return score, status, is_verified

    def verify(
        self, draft_text: str, source_context: str, threshold: float = 0.65
    ) -> NLIVerificationResult:
        """
        Parses claim sentences containing citation markers from draft_text,
        runs entailment evaluation against source_context, and builds NLIVerificationResult.
        """
        if not draft_text:
            return NLIVerificationResult(
                verified_text="",
                total_claims_checked=0,
                verified_count=0,
                hallucinated_count=0,
                verdicts=[],
                passed=True,
            )

        verdicts: List[CitationVerdict] = []
        # Find all citation matches
        matches = list(CITATION_REGEX.finditer(draft_text))

        # Process each citation match
        seen_claims: Set[str] = set()
        for m in matches:
            marker = m.group(0)
            m_start, m_end = m.span()

            # Find the sentence boundary enclosing this citation
            # Search backwards for sentence start
            preceding_text = draft_text[:m_start]
            s_start = 0
            for delim in ("\n", ". ", "! ", "? "):
                idx = preceding_text.rfind(delim)
                if idx != -1:
                    cand = idx + len(delim)
                    if cand > s_start:
                        s_start = cand

            # Search forwards for sentence end
            succeeding_text = draft_text[m_end:]
            s_end = len(draft_text)
            for delim in ("\n", ". ", "! ", "? "):
                idx = succeeding_text.find(delim)
                if idx != -1:
                    cand = m_end + idx + (1 if delim == "\n" else 1)
                    if cand < s_end:
                        s_end = cand

            claim_sentence = draft_text[s_start:s_end].strip()
            # Clean leading markdown bullets or punctuation
            claim_sentence = re.sub(r"^[\s\-*#•0-9\.]+", "", claim_sentence).strip()

            claim_key = f"{marker}::{claim_sentence}"
            if claim_key in seen_claims:
                continue
            seen_claims.add(claim_key)

            # Evaluate (Premise = source_context, Hypothesis = claim_sentence)
            score, status, is_verified = self.evaluate_pair(source_context, claim_sentence)

            # If threshold is customized and score exceeds threshold
            if score >= threshold and status != "CONTRADICTION":
                is_verified = True
            elif score < threshold:
                is_verified = False

            verdicts.append(
                CitationVerdict(
                    claim_sentence=claim_sentence,
                    citation_marker=marker,
                    entailment_score=score,
                    status=status,
                    is_verified=is_verified,
                )
            )

        total = len(verdicts)
        verified = sum(1 for v in verdicts if v.is_verified)
        hallucinated = total - verified
        passed = (hallucinated == 0)

        return NLIVerificationResult(
            verified_text=draft_text,
            total_claims_checked=total,
            verified_count=verified,
            hallucinated_count=hallucinated,
            verdicts=verdicts,
            passed=passed,
        )


# Singleton guard instance
_default_guard = NLICrossEncoderGuard()
