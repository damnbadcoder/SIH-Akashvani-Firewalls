"""
Scorer implementation for Enhancement 4: Readability & Tone Regression Scoring Engine.
Transmute System (SIH 2026 PS 26154)

Provides:
- Syllable counter (pure Python, offline, sub-5ms)
- Flesch Reading Ease
- Flesch-Kincaid Grade Level
- Gunning Fog Index
- Channel & audience tone compliance validation
"""

import re
from typing import Dict, Any, List, Tuple
from .types import ReadabilityMetrics, ReadabilityResult


# Common abbreviations that end in a period but do NOT indicate sentence boundaries
ABBREVIATIONS = (
    r"\b(e\.g\.|i\.e\.|etc\.|vs\.|al\.|approx\.|dept\.|fig\.|inc\.|ltd\.|corp\.|"
    r"dr\.|mr\.|mrs\.|ms\.|prof\.|gov\.|sec\.|vol\.|no\.|jan\.|feb\.|mar\.|apr\.|"
    r"jun\.|jul\.|aug\.|sep\.|sept\.|oct\.|nov\.|dec\.)"
)

# Suffixes where silent 'e' appears internally before a suffix
INTERNAL_SILENT_E_SUFFIXES = ("ment", "ful", "less", "ly", "ness", "some")

# Platform Calibration Thresholds
PLATFORM_THRESHOLDS: Dict[str, Dict[str, Any]] = {
    "linkedin_post": {
        "min_grade": 7.0,
        "max_grade": 10.0,
        "min_ease": 55.0,
        "max_ease": 100.0,
        "name": "LinkedIn Post",
    },
    "twitter_thread": {
        "min_grade": 7.0,
        "max_grade": 10.0,
        "min_ease": 55.0,
        "max_ease": 100.0,
        "name": "Twitter Thread",
    },
    "social_thread": {
        "min_grade": 7.0,
        "max_grade": 10.0,
        "min_ease": 55.0,
        "max_ease": 100.0,
        "name": "Social Thread",
    },
    "executive_brief": {
        "min_grade": 10.0,
        "max_grade": 14.0,
        "min_ease": 35.0,
        "max_ease": 55.0,
        "name": "Executive Brief",
    },
    "exec_summary": {
        "min_grade": 10.0,
        "max_grade": 14.0,
        "min_ease": 35.0,
        "max_ease": 55.0,
        "name": "Executive Summary",
    },
    "technical_advisory": {
        "min_grade": 10.0,
        "max_grade": 14.0,
        "min_ease": 35.0,
        "max_ease": 55.0,
        "name": "Technical Advisory",
    },
    "advisory": {
        "min_grade": 10.0,
        "max_grade": 14.0,
        "min_ease": 35.0,
        "max_ease": 55.0,
        "name": "Security Advisory",
    },
    "incident_report": {
        "min_grade": 10.0,
        "max_grade": 14.0,
        "min_ease": 35.0,
        "max_ease": 55.0,
        "name": "Incident Report",
    },
    "video_script": {
        "min_grade": 6.0,
        "max_grade": 9.0,
        "min_ease": 65.0,
        "max_ease": 100.0,
        "name": "Video Script",
    },
    "playbook": {
        "min_grade": 8.0,
        "max_grade": 12.0,
        "min_ease": 40.0,
        "max_ease": 65.0,
        "name": "Incident Playbook",
    },
    "slide_deck": {
        "min_grade": 8.0,
        "max_grade": 12.0,
        "min_ease": 45.0,
        "max_ease": 75.0,
        "name": "Slide Deck",
    },
    "press_release": {
        "min_grade": 8.0,
        "max_grade": 12.0,
        "min_ease": 45.0,
        "max_ease": 70.0,
        "name": "Press Release",
    },
    "default": {
        "min_grade": 7.0,
        "max_grade": 12.0,
        "min_ease": 45.0,
        "max_ease": 85.0,
        "name": "Default Deliverable",
    },
}


def count_syllables(word: str) -> int:
    """
    Computes syllable count for an English word using fast heuristic analysis.
    Pure Python, sub-microsecond per word.
    """
    w = re.sub(r"[^a-z]", "", word.lower())
    if not w:
        return 0
    if len(w) <= 3:
        return 1

    # Adjust for internal silent 'e' before standard suffixes (e.g. management, safely)
    for suffix in INTERNAL_SILENT_E_SUFFIXES:
        if w.endswith(suffix):
            base = w[:-len(suffix)]
            if base.endswith("e") and not base.endswith("ee") and not base.endswith("le"):
                w = base[:-1] + suffix
                break

    # Adjust for trailing silent 'e'
    if w.endswith("e") and not w.endswith("ee") and not w.endswith("le"):
        w = w[:-1]
    # Adjust for regular past tense -ed (unless preceded by t or d, e.g. waited/needed)
    elif w.endswith("ed") and not (w.endswith("ted") or w.endswith("ded")):
        w = w[:-2]
    # Adjust for plural -es (unless preceded by s, z, ch, sh, x)
    elif w.endswith("es") and not (
        w.endswith("ses")
        or w.endswith("zes")
        or w.endswith("ches")
        or w.endswith("shes")
        or w.endswith("xes")
    ):
        w = w[:-2]

    matches = re.findall(r"[aeiouy]+", w)
    return max(1, len(matches))


def is_complex_word(word: str) -> bool:
    """
    Identifies complex words for Gunning Fog: words with >= 3 syllables,
    excluding common grammatical suffixes (-ing, -ed, -es).
    """
    w = re.sub(r"[^a-z]", "", word.lower())
    sylls = count_syllables(w)
    if sylls < 3:
        return False

    # Exclude words where the 3rd syllable is introduced solely by common suffixes
    for suffix in ("ing", "ed", "es"):
        if w.endswith(suffix):
            stem = w[:-len(suffix)]
            if count_syllables(stem) < 3:
                return False

    return True


def clean_and_tokenize(text: str) -> Tuple[List[str], List[str]]:
    """
    Strips markdown formatting, code blocks, and citations, then extracts
    sentences and word tokens.
    """
    if not text or not text.strip():
        return [], []

    # 1. Remove markdown citation markers (e.g. [^src-1], [^aud-2])
    cleaned = re.sub(r"\[\^[^\]]+\]", "", text)

    # 2. Remove markdown links [text](url) -> keep text
    cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)

    # 3. Remove image tags ![alt](url)
    cleaned = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", cleaned)

    # 4. Remove code blocks and inline code
    cleaned = re.sub(r"```[\s\S]*?```", "", cleaned)
    cleaned = re.sub(r"`[^`]+`", "", cleaned)

    # 5. Remove headers, blockquotes, bullets
    cleaned = re.sub(r"^#+\s+", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"^>\s+", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"^[-*•]\s+", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"[*_~]", " ", cleaned)

    # 6. Protect dots in decimals, IP addresses, and versions (e.g. 10.4.12.8, 3.14, v1.2)
    cleaned = re.sub(r"(\d+)\.(\d+)", r"\1<DOT>\2", cleaned)

    # 7. Protect common abbreviations with periods
    cleaned = re.sub(
        ABBREVIATIONS,
        lambda m: m.group(0).replace(".", "<DOT>"),
        cleaned,
        flags=re.IGNORECASE,
    )

    # 8. Sentence tokenization on terminal punctuation or double linebreaks
    raw_sentences = re.split(r"(?:[.!?]+(?:\s+|\n|$))|\n{2,}", cleaned)
    sentences = [
        s.replace("<DOT>", ".").strip()
        for s in raw_sentences
        if s.strip() and re.search(r"[a-zA-Z0-9]", s)
    ]

    # 9. Word tokenization
    words = re.findall(r"\b[a-zA-Z]+(?:'[a-zA-Z]+)?\b", cleaned.replace("<DOT>", "."))

    return sentences, words


class ReadabilityScorer:
    """
    Linguistic indices and audience readability analyzer.
    Deterministic, pure Python, sub-5ms runtime.
    """

    def calculate_metrics(self, text: str) -> ReadabilityMetrics:
        """
        Computes Flesch Reading Ease, Flesch-Kincaid Grade Level, and Gunning Fog.
        """
        sentences, words = clean_and_tokenize(text)
        word_count = len(words)
        sentence_count = max(1, len(sentences))

        if word_count == 0:
            return ReadabilityMetrics(
                flesch_reading_ease=0.0,
                flesch_kincaid_grade=0.0,
                gunning_fog=0.0,
                word_count=0,
                sentence_count=0,
                syllable_count=0,
                avg_words_per_sentence=0.0,
            )

        syllable_counts = [count_syllables(w) for w in words]
        total_syllables = sum(syllable_counts)
        complex_count = sum(1 for w in words if is_complex_word(w))

        asl = word_count / sentence_count
        asw = total_syllables / word_count

        # Standard Flesch Reading Ease formula:
        # 206.835 - 1.015 * (words / sentences) - 84.6 * (syllables / words)
        fre = 206.835 - (1.015 * asl) - (84.6 * asw)

        # Standard Flesch-Kincaid Grade Level formula:
        # 0.39 * (words / sentences) + 11.8 * (syllables / words) - 15.59
        fkgl = (0.39 * asl) + (11.8 * asw) - 15.59

        # Standard Gunning Fog Index:
        # 0.4 * ((words / sentences) + 100 * (complex_words / words))
        gunning_fog = 0.4 * (asl + 100.0 * (complex_count / word_count))

        return ReadabilityMetrics(
            flesch_reading_ease=round(fre, 2),
            flesch_kincaid_grade=round(max(0.0, fkgl), 2),
            gunning_fog=round(max(0.0, gunning_fog), 2),
            word_count=word_count,
            sentence_count=len(sentences),
            syllable_count=total_syllables,
            avg_words_per_sentence=round(asl, 2),
        )

    def score(self, text: str, platform_key: str = "default") -> ReadabilityResult:
        """
        Calculates readability metrics and evaluates audience tone alignment
        against calibrated platform benchmarks.
        """
        metrics = self.calculate_metrics(text)
        normalized_key = (platform_key or "default").lower().strip().replace("-", "_")
        profile = PLATFORM_THRESHOLDS.get(normalized_key, PLATFORM_THRESHOLDS["default"])

        if metrics.word_count == 0:
            return ReadabilityResult(
                passed=False,
                target_platform=platform_key,
                metrics=metrics,
                verdict="TOO_SIMPLE",
                details="No readable words detected in deliverable text.",
            )

        grade = metrics.flesch_kincaid_grade
        ease = metrics.flesch_reading_ease
        min_grade = profile["min_grade"]
        max_grade = profile["max_grade"]
        min_ease = profile["min_ease"]
        max_ease = profile.get("max_ease", 100.0)
        p_name = profile["name"]

        # Classification logic:
        # TOO_DENSE: Grade level is too high OR reading ease is too low (excessive jargon/long sentences)
        if grade > max_grade or ease < min_ease:
            verdict = "TOO_DENSE"
            passed = False
            details = (
                f"Deliverable tone is too dense for {p_name}. "
                f"Grade Level is {grade:.1f} (target: {min_grade:.1f}–{max_grade:.1f}) "
                f"and Reading Ease is {ease:.1f} (target: >= {min_ease:.1f})."
            )
        # TOO_SIMPLE: Grade level is below minimum OR ease exceeds the upper ceiling for technical briefs
        elif grade < min_grade or ease > max_ease:
            verdict = "TOO_SIMPLE"
            passed = False
            details = (
                f"Deliverable tone is too elementary for {p_name}. "
                f"Grade Level is {grade:.1f} (target: {min_grade:.1f}–{max_grade:.1f}) "
                f"and Reading Ease is {ease:.1f} (target: <= {max_ease:.1f})."
            )
        else:
            verdict = "OPTIMAL"
            passed = True
            details = (
                f"Deliverable tone is optimal for {p_name}. "
                f"Grade Level: {grade:.1f} (target: {min_grade:.1f}–{max_grade:.1f}), "
                f"Reading Ease: {ease:.1f} (target: {min_ease:.1f}–{max_ease:.1f}), "
                f"Gunning Fog: {metrics.gunning_fog:.1f}."
            )

        return ReadabilityResult(
            passed=passed,
            target_platform=platform_key,
            metrics=metrics,
            verdict=verdict,
            details=details,
        )

    def score_dict(self, text: str, platform_key: str = "default") -> dict:
        """
        Convenience method returning a pure Python dictionary representation
        of ReadabilityResult.
        """
        return self.score(text, platform_key).model_dump()


_default_scorer = ReadabilityScorer()


def score_readability(text: str, platform_key: str = "default") -> dict:
    """
    Top-level API: Computes linguistic indices and checks platform compliance.
    Returns ReadabilityResult dict.
    """
    return _default_scorer.score_dict(text, platform_key)
