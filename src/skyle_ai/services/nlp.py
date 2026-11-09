from __future__ import annotations

import re
import unicodedata
from collections import Counter

POSITIVE = {
    "good",
    "great",
    "excellent",
    "love",
    "loved",
    "like",
    "happy",
    "success",
    "successful",
    "helpful",
    "reliable",
    "beautiful",
    "improve",
    "improved",
    "clear",
    "strong",
    "wonderful",
}
NEGATIVE = {
    "bad",
    "terrible",
    "awful",
    "hate",
    "hated",
    "poor",
    "sad",
    "fail",
    "failed",
    "failure",
    "broken",
    "unsafe",
    "late",
    "angry",
    "disappointing",
    "worse",
    "worst",
    "problem",
}
AMHARIC_POSITIVE = {"ጥሩ", "አስደሳች", "ደስተኛ", "ውብ", "ወደድኩ", "ተስፋ", "ሰላም", "ተሳክቷል"}
AMHARIC_NEGATIVE = {"መጥፎ", "አሳዛኝ", "ችግር", "ውድቀት", "አደገኛ", "አልወደድኩ", "አስጠላ"}
NEGATORS = {"not", "no", "never", "n't", "አይ", "አል"}
TOKEN_RE = re.compile(r"[\w\u1200-\u137F]+", re.UNICODE)
URL_RE = re.compile(r"https?://[^\s<>]+", re.IGNORECASE)
EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
DATE_RE = re.compile(r"\b(?:\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4})\b")


def analyze_text(text: str) -> dict:
    normalized = unicodedata.normalize("NFKC", text).strip()
    if not normalized:
        raise ValueError("Enter some text to analyze.")
    tokens = TOKEN_RE.findall(normalized.lower())
    if not tokens:
        raise ValueError("No analyzable words were found.")
    amharic_count = sum(any("\u1200" <= ch <= "\u137f" for ch in token) for token in tokens)
    latin_count = sum(any("a" <= ch <= "z" for ch in token) for token in tokens)
    language = (
        "Amharic-script"
        if amharic_count > latin_count
        else ("English/Latin-script" if latin_count else "mixed/undetermined")
    )
    positive = 0
    negative = 0
    matches: list[dict[str, str]] = []
    for index, token in enumerate(tokens):
        prev = tokens[max(0, index - 3) : index]
        flipped = any(word in NEGATORS or word.endswith("n't") for word in prev)
        if token in POSITIVE or token in AMHARIC_POSITIVE:
            positive += -1 if flipped else 1
            matches.append({"term": token, "polarity": "negative" if flipped else "positive"})
        elif token in NEGATIVE or token in AMHARIC_NEGATIVE:
            negative += -1 if flipped else 1
            matches.append({"term": token, "polarity": "positive" if flipped else "negative"})
    score = (positive - negative) / max(1, len(matches))
    label = "positive" if score > 0.15 else ("negative" if score < -0.15 else "neutral/unknown")
    proper = re.findall(r"\b[A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,}){0,2}\b", normalized)
    entities = []
    for kind, values in (
        ("url", URL_RE.findall(normalized)),
        ("email", EMAIL_RE.findall(normalized)),
        ("date", DATE_RE.findall(normalized)),
        ("capitalized phrase (pattern)", proper),
    ):
        entities.extend({"type": kind, "text": value.rstrip(".,;:!")} for value in values)
    stop = {
        "the",
        "and",
        "for",
        "with",
        "this",
        "that",
        "from",
        "are",
        "was",
        "were",
        "you",
        "your",
        "but",
        "not",
        "have",
        "has",
        "our",
    }
    keywords = [
        {"term": word, "count": count}
        for word, count in Counter(t for t in tokens if len(t) > 2 and t not in stop).most_common(8)
    ]
    return {
        "language_hint": language,
        "token_count": len(tokens),
        "sentence_count": max(1, len(re.findall(r"[.!?።]+", normalized))),
        "sentiment": {"label": label, "score": round(max(-1.0, min(1.0, score)), 3), "matched_terms": matches},
        "entities": entities,
        "keywords": keywords,
        "method": "Local lexicon and regular-expression heuristics; not a trained or benchmarked model.",
    }
