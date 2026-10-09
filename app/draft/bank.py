from __future__ import annotations

import re

from rapidfuzz import fuzz

_PUNCT = re.compile(r"[^a-z0-9\s]+")
_SPACE = re.compile(r"\s+")


def normalize(text: str) -> str:
    cleaned = _PUNCT.sub(" ", text.lower())
    return _SPACE.sub(" ", cleaned).strip()


def match_answer(question: str, answers: list[dict]) -> dict | None:
    target = normalize(question)
    if not target:
        return None
    for entry in answers:
        if normalize(str(entry.get("question", ""))) == target:
            return _hit(str(entry.get("answer", "")), "bank", "high", 100)
    scored: list[tuple[int, dict]] = []
    for entry in answers:
        score = int(fuzz.token_set_ratio(target, normalize(str(entry.get("question", "")))))
        scored.append((score, entry))
    if not scored:
        return None
    scored.sort(key=lambda item: item[0], reverse=True)
    score, entry = scored[0]
    second = scored[1][0] if len(scored) > 1 else 0
    if score < 75 or score - second < 5:
        return None
    confidence = "high" if score >= 90 else "check"
    source = "bank" if score >= 90 else "similar"
    return _hit(str(entry.get("answer", "")), source, confidence, score)


def _hit(answer: str, source: str, confidence: str, score: int) -> dict | None:
    if not answer.strip():
        return None
    notes = "" if confidence == "high" else f"Similar saved answer ({score}). Check it."
    return {
        "value": answer.strip(),
        "source": source,
        "confidence": confidence,
        "notes": notes,
    }


def is_identity(label: str) -> bool:
    text = normalize(label)
    identity_terms = (
        "first name",
        "last name",
        "email",
        "phone",
        "resume",
        "linkedin",
        "github",
        "website",
        "portfolio",
    )
    return any(term in text for term in identity_terms)
