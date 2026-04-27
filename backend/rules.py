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
    scenario: str
    coaching_step: str
    reason: str | None = None


SCENARIO_KEYWORDS = {
    "greeting_practice": {"hello", "hi", "introduce", "first impression", "meet"},
    "joining_group": {"group", "lunch", "table", "join", "conversation circle"},
    "social_anxiety_support": {"nervous", "awkward", "anxious", "scared", "embarrassed"},
    "small_talk_flow": {"small talk", "keep talking", "what do i say", "silence"},
    "conversation_exit": {"leave", "end conversation", "goodbye", "wrap up", "exit"},
}


def _contains_unsafe_content(text: str) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in UNSAFE_OR_OUT_OF_SCOPE_KEYWORDS)


def detect_scenario(user_input: str, intent: str) -> str:
    lowered = user_input.lower()

    for scenario, keywords in SCENARIO_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return scenario

    if intent == "greeting":
        return "greeting_practice"
    if intent == "emotional_expression":
        return "social_anxiety_support"
    return "small_talk_flow"


def _coaching_step_for(scenario: str) -> str:
    steps = {
        "greeting_practice": "Offer one simple opener and invite a brief reply.",
        "joining_group": "Help the user enter with a short comment tied to the current topic.",
        "social_anxiety_support": "Normalize the feeling and reduce the next action to one manageable step.",
        "small_talk_flow": "Keep the exchange moving with one question or bridge phrase.",
        "conversation_exit": "Close politely and leave the connection open for later.",
    }
    return steps.get(scenario, "Give one manageable social step.")


def response_has_question(text: str) -> bool:
    return "?" in text


def response_sentence_count(text: str) -> int:
    fragments = [part.strip() for part in text.replace("?", ".").split(".") if part.strip()]
    return len(fragments)


def response_is_valid(text: str, rule_result: RuleResult) -> bool:
    if not text.strip():
        return False
    if not response_has_question(text):
        return False
    if response_sentence_count(text) > 4:
        return False
    if len(text.split()) > 70:
        return False
    lowered = text.lower()
    if rule_result.follow_up.rstrip("?").lower() not in lowered and lowered.count("?") != 1:
        return False
    return True


def apply_rules(user_input: str, intent: str) -> RuleResult:
    cleaned = user_input.strip()
    scenario = detect_scenario(cleaned, intent)
    coaching_step = _coaching_step_for(scenario)

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
            scenario="scenario_selection",
            coaching_step="Ask for one specific social situation before giving advice.",
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
            scenario="safety_redirect",
            coaching_step="Refuse the unsafe request and redirect to a safe social-support task.",
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
            scenario=scenario,
            coaching_step=coaching_step,
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
            scenario=scenario,
            coaching_step=coaching_step,
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
        scenario=scenario,
        coaching_step=coaching_step,
    )
