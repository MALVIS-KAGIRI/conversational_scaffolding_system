from __future__ import annotations


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


def classify_intent(user_input: str) -> str:
    text = user_input.strip().lower()

    if any(keyword in text for keyword in GREETING_KEYWORDS):
        return "greeting"

    if any(keyword in text for keyword in EMOTIONAL_KEYWORDS):
        return "emotional_expression"

    return "general_interaction"
