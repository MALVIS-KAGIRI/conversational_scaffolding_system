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

SCENARIO_ALIASES = {
    "lunch_group": "joining_group",
    "join a lunch conversation": "joining_group",
    "meet_someone_new": "greeting_practice",
    "meet someone new": "greeting_practice",
    "group_confidence": "social_anxiety_support",
    "speak in a group setting": "social_anxiety_support",
    "awkward_silence": "small_talk_flow",
    "recover from awkward silence": "small_talk_flow",
    "end_conversation": "conversation_exit",
    "end a conversation smoothly": "conversation_exit",
}


def _contains_unsafe_content(text: str) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in UNSAFE_OR_OUT_OF_SCOPE_KEYWORDS)


def normalize_scenario_name(value: str | None) -> str | None:
    if not value:
        return None
    lowered = value.strip().lower()
    return SCENARIO_ALIASES.get(lowered, lowered if lowered in SCENARIO_KEYWORDS else None)


def detect_scenario(user_input: str, intent: str, preferred_scenario: str | None = None) -> str:
    normalized_preference = normalize_scenario_name(preferred_scenario)
    if normalized_preference:
        return normalized_preference

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


def _follow_up_for(scenario: str) -> str:
    follow_ups = {
        "greeting_practice": "What opening line would you like to practice first?",
        "joining_group": "What topic should we pretend the group is already discussing?",
        "social_anxiety_support": "What part of that interaction feels hardest right now?",
        "small_talk_flow": "What detail could you build on with one short follow-up question?",
        "conversation_exit": "What polite closing line would you like to practice?",
    }
    return follow_ups.get(scenario, "What specific interaction would you like to practice next?")


def apply_rules(
    user_input: str,
    intent: str,
    preferred_scenario: str | None = None,
    session_started: bool = False,
) -> RuleResult:
    cleaned = user_input.strip()
    scenario = detect_scenario(cleaned, intent, preferred_scenario=preferred_scenario)
    coaching_step = _coaching_step_for(scenario)
    scenario_follow_up = _follow_up_for(scenario)

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

    if intent == "greeting" and not session_started:
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

    if intent == "greeting" and session_started:
        return RuleResult(
            intent="general_interaction",
            blocked=False,
            response=None,
            guidance=(
                "Stay inside the active scenario, respond naturally, and move the practice "
                "forward instead of restarting scenario selection."
            ),
            follow_up=scenario_follow_up,
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
            follow_up=scenario_follow_up,
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
        follow_up=scenario_follow_up,
        scenario=scenario,
        coaching_step=coaching_step,
    )
