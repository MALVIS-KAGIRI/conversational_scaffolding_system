from __future__ import annotations

from dataclasses import dataclass


UNSAFE_OR_OUT_OF_SCOPE_KEYWORDS = {
    "diagnose",
    "diagnosis",
    "prescribe",
    "prescription",
    "medical advice",
    "legal advice",
    "suicide",
    "self-harm",
    "harm someone",
    "kill",
    "overdose",
}


@dataclass
class RuleResult:
    intent: str
    blocked: bool
    response: str | None
    guidance: str
    follow_up: str
    reason: str | None = None


def _contains_unsafe_content(text: str) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in UNSAFE_OR_OUT_OF_SCOPE_KEYWORDS)


def apply_rules(user_input: str, intent: str) -> RuleResult:
    cleaned = user_input.strip()

    if not cleaned:
        return RuleResult(
            intent=intent,
            blocked=True,
            response=(
                "I hear that you want to engage. Please share one short social situation "
                "you want to practice, and I will guide you step by step. "
                "What interaction would you like to rehearse?"
            ),
            guidance="Ask the user for a specific social situation.",
            follow_up="What interaction would you like to rehearse?",
            reason="empty_input",
        )

    if _contains_unsafe_content(cleaned):
        return RuleResult(
            intent=intent,
            blocked=True,
            response=(
                "I can support practice for everyday social interaction, but I cannot provide "
                "medical, legal, or crisis guidance. Please contact a qualified professional "
                "or local emergency support if the situation is urgent. "
                "Would you like to practice how to ask a trusted person for help?"
            ),
            guidance="Reject unsafe or out-of-scope requests.",
            follow_up="Would you like to practice how to ask a trusted person for help?",
            reason="out_of_scope",
        )

    if intent == "greeting":
        return RuleResult(
            intent=intent,
            blocked=True,
            response=(
                "Thanks for starting the conversation. Let us focus on one social situation "
                "you want to practice, such as greeting someone, joining a group, or keeping "
                "a conversation going. Which situation should we work on first?"
            ),
            guidance="Convert greetings into a structured practice prompt.",
            follow_up="Which situation should we work on first?",
        )

    if intent == "emotional_expression":
        return RuleResult(
            intent=intent,
            blocked=False,
            response=None,
            guidance=(
                "Acknowledge the feeling, give one simple social coaching step, and ask for "
                "a concrete practice scenario."
            ),
            follow_up="What social moment feels hardest right now?",
        )

    return RuleResult(
        intent=intent,
        blocked=False,
        response=None,
        guidance=(
            "Keep the user focused on practicing a specific social interaction with one step "
            "at a time."
        ),
        follow_up="What specific interaction would you like to practice next?",
    )
