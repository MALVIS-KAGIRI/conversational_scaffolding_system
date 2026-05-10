from __future__ import annotations

import re


GREETING_KEYWORDS = {
    "hello",
    "hi",
    "hey",
    "good morning",
    "good afternoon",
    "good evening",
}

EMOTIONAL_KEYWORDS = {
    "nervous",
    "anxious",
    "worried",
    "sad",
    "upset",
    "lonely",
    "awkward",
    "scared",
    "frustrated",
    "embarrassed",
}


def _is_greeting_only(text: str) -> bool:
    normalized = re.sub(r"[^\w\s]", " ", text.lower()).strip()
    if not normalized:
        return False

    compact = re.sub(r"\s+", " ", normalized)
    if compact in GREETING_KEYWORDS:
        return True

    words = compact.split()
    if len(words) > 4:
        return False

    return all(word in {"hello", "hi", "hey", "good", "morning", "afternoon", "evening", "there"} for word in words)


def classify_intent(user_input: str) -> str:
    text = user_input.strip().lower()

    if _is_greeting_only(text):
        return "greeting"

    if any(keyword in text for keyword in EMOTIONAL_KEYWORDS):
        return "emotional_expression"

    return "general_interaction"
