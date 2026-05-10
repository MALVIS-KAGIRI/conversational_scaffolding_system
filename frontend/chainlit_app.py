from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List

import chainlit as cl
import requests
from chainlit.input_widget import Select, Slider, Switch


BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")

SCENARIOS: List[Dict[str, str]] = [
    {
        "id": "lunch_group",
        "title": "Join a Lunch Conversation",
        "description": "Practice entering an ongoing group conversation without feeling abrupt.",
        "difficulty": "Beginner",
        "skill": "follow_ups",
        "context": "Work",
    },
    {
        "id": "meet_someone_new",
        "title": "Meet Someone New",
        "description": "Practice greeting someone and keeping the exchange going naturally.",
        "difficulty": "Beginner",
        "skill": "greeting",
        "context": "Social",
    },
    {
        "id": "group_confidence",
        "title": "Speak in a Group Setting",
        "description": "Practice contributing one clear thought in a group discussion.",
        "difficulty": "Intermediate",
        "skill": "confidence",
        "context": "School",
    },
    {
        "id": "awkward_silence",
        "title": "Recover From Awkward Silence",
        "description": "Practice restarting a conversation when the energy drops.",
        "difficulty": "Intermediate",
        "skill": "conversation_flow",
        "context": "Social",
    },
    {
        "id": "end_conversation",
        "title": "End a Conversation Smoothly",
        "description": "Practice leaving politely while keeping the interaction positive.",
        "difficulty": "Advanced",
        "skill": "conversation_endings",
        "context": "Work",
    },
]

SKILL_LABELS = {
    "greeting": "Greeting",
    "follow_ups": "Follow-ups",
    "confidence": "Confidence",
    "conversation_flow": "Flow",
    "conversation_endings": "Endings",
}

SCENARIO_TITLE_TO_ID = {scenario["title"]: scenario["id"] for scenario in SCENARIOS}
SCENARIO_ID_TO_TITLE = {scenario["id"]: scenario["title"] for scenario in SCENARIOS}


def get_scenario_by_id(scenario_id: str) -> Dict[str, str]:
    for scenario in SCENARIOS:
        if scenario["id"] == scenario_id:
            return scenario
    return SCENARIOS[0]


def default_goal_for_skill(skill: str) -> str:
    goals = {
        "greeting": "Open warmly and invite the other person in.",
        "follow_ups": "Ask one natural follow-up question.",
        "confidence": "Share one clear opinion without apologizing for it.",
        "conversation_flow": "Use one bridge phrase to keep the exchange moving.",
        "conversation_endings": "End politely while leaving the door open for later.",
    }
    return goals.get(skill, "Practice one focused social skill.")


def coach_hint_for_skill(skill: str) -> str:
    hints = {
        "greeting": "Start simple: greet, mention the shared context, then invite a response.",
        "follow_ups": "Listen for one detail you can build on with a short question.",
        "confidence": "State one thought clearly before adding extra explanation.",
        "conversation_flow": "Use a bridge phrase like 'That reminds me' or 'How about you?'",
        "conversation_endings": "Close warmly, mention appreciation, and leave the interaction open.",
    }
    return hints.get(skill, "Stay specific, kind, and one step at a time.")


def initial_state() -> Dict[str, Any]:
    scenario = SCENARIOS[0]
    return {
        "selected_scenario_id": scenario["id"],
        "goal_text": default_goal_for_skill(scenario["skill"]),
        "coach_style": "Supportive",
        "difficulty_pref": "Balanced",
        "confidence_before": 3,
        "confidence_after": 3,
        "show_hint_sidebar": True,
        "weekly_goal": 4,
        "messages": [],
        "session_history": [],
        "skill_scores": {key: 0 for key in SKILL_LABELS},
        "recent_wins": [
            "Started the first coaching workspace.",
            "Rule-guided practice mode is ready.",
        ],
        "current_session": {
            "scenario_id": scenario["id"],
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "user_turns": 0,
            "assistant_turns": 0,
            "last_intent": "general_interaction",
            "last_provider": "not_started",
            "last_latency_ms": 0.0,
            "blocked_count": 0,
        },
    }


def get_state() -> Dict[str, Any]:
    state = cl.user_session.get("ui_state")
    if state is None:
        state = initial_state()
        cl.user_session.set("ui_state", state)
    return state


def save_state(state: Dict[str, Any]) -> None:
    cl.user_session.set("ui_state", state)


def current_streak(history: List[Dict[str, Any]]) -> int:
    session_days = sorted(
        {datetime.fromisoformat(item["completed_at"]).date() for item in history},
        reverse=True,
    )
    streak = 0
    day_cursor = datetime.now().date()
    for session_day in session_days:
        if session_day == day_cursor:
            streak += 1
            day_cursor -= timedelta(days=1)
        elif session_day == day_cursor - timedelta(days=1) and streak == 0:
            day_cursor = session_day
            streak += 1
            day_cursor -= timedelta(days=1)
        else:
            break
    return streak


def weekly_sessions_count(history: List[Dict[str, Any]]) -> int:
    cutoff = datetime.now() - timedelta(days=7)
    return sum(
        1 for session in history if datetime.fromisoformat(session["completed_at"]) >= cutoff
    )


def average_confidence(history: List[Dict[str, Any]]) -> float:
    if not history:
        return 0.0
    total = sum(item["confidence_after"] for item in history)
    return round(total / len(history), 1)


def strongest_skill_label(skill_scores: Dict[str, int]) -> str:
    skill = max(skill_scores, key=lambda item: skill_scores[item])
    return SKILL_LABELS[skill]


def weakest_skill_label(skill_scores: Dict[str, int]) -> str:
    skill = min(skill_scores, key=lambda item: skill_scores[item])
    return SKILL_LABELS[skill]


def build_heatmap_text(history: List[Dict[str, Any]]) -> str:
    today = datetime.now().date()
    day_counts: Dict[str, int] = {}
    for session in history:
        day = datetime.fromisoformat(session["completed_at"]).date().isoformat()
        day_counts[day] = day_counts.get(day, 0) + 1

    rows = []
    for week in range(4):
        row = []
        for day_offset in range(7):
            date_value = today - timedelta(days=(27 - (week * 7 + day_offset)))
            count = day_counts.get(date_value.isoformat(), 0)
            shade = ["-", ".", "o", "O", "#"][min(count, 4)]
            row.append(shade)
        rows.append(" ".join(row))
    return "\n".join(rows)


async def post_chat(user_input: str) -> Dict[str, Any]:
    state = get_state()
    scenario = get_scenario_by_id(state["selected_scenario_id"])

    def _send() -> Dict[str, Any]:
        response = requests.post(
            f"{BACKEND_URL}/chat",
            json={
                "user_input": user_input,
                "selected_scenario": scenario["id"],
                "goal_text": state["goal_text"],
                "coach_style": state["coach_style"],
            },
            timeout=90,
        )
        response.raise_for_status()
        return response.json()

    return await asyncio.to_thread(_send)


async def refresh_sidebar() -> None:
    state = get_state()
    scenario = get_scenario_by_id(state["selected_scenario_id"])
    history = state["session_history"]
    skill_scores = state["skill_scores"]
    stats_md = f"""
## Practice Snapshot

**Scenario**
{scenario["title"]}

**Goal**
{state["goal_text"]}

**Coach Style**
{state["coach_style"]}

**Streak**
{current_streak(history)} day(s)

**This Week**
{weekly_sessions_count(history)}

**Confidence Avg**
{average_confidence(history)}

**Best Skill**
{strongest_skill_label(skill_scores)}

**Focus Area**
{weakest_skill_label(skill_scores)}
"""
    skill_map = "\n".join(
        f"- {SKILL_LABELS[skill]}: {score}" for skill, score in skill_scores.items()
    )
    sidebar_elements: List[cl.Text] = [
        cl.Text(name="snapshot", content=stats_md, display="side"),
        cl.Text(
            name="skill_map",
            content=f"## Skill Map\n\n{skill_map}",
            display="side",
        ),
        cl.Text(
            name="recent_wins",
            content="## Recent Wins\n\n" + "\n".join(f"- {win}" for win in state["recent_wins"][:5]),
            display="side",
        ),
        cl.Text(
            name="heatmap",
            content=(
                "## Consistency\n\n```text\n"
                + build_heatmap_text(history)
                + "\n```\n- none  . light  o moderate  O strong  # very active"
            ),
            display="side",
        ),
    ]
    if state["show_hint_sidebar"]:
        sidebar_elements.insert(
            1,
            cl.Text(
                name="hint",
                content=(
                    "## Coach Hint\n\n"
                    + coach_hint_for_skill(scenario["skill"])
                ),
                display="side",
            ),
        )
    await cl.ElementSidebar.set_title("Coaching Dashboard")
    await cl.ElementSidebar.set_elements(sidebar_elements)


def sync_state_from_settings(settings: Dict[str, Any]) -> Dict[str, Any]:
    state = get_state()
    scenario_value = settings.get("Scenario", SCENARIO_ID_TO_TITLE[state["selected_scenario_id"]])
    state["selected_scenario_id"] = SCENARIO_TITLE_TO_ID.get(scenario_value, state["selected_scenario_id"])
    state["coach_style"] = settings.get("CoachStyle", state["coach_style"])
    state["difficulty_pref"] = settings.get("Difficulty", state["difficulty_pref"])
    state["confidence_before"] = int(settings.get("ConfidenceBefore", state["confidence_before"]))
    state["confidence_after"] = int(settings.get("ConfidenceAfter", state["confidence_after"]))
    state["weekly_goal"] = int(settings.get("WeeklyGoal", state["weekly_goal"]))
    state["show_hint_sidebar"] = bool(settings.get("ShowHintSidebar", state["show_hint_sidebar"]))
    scenario = get_scenario_by_id(state["selected_scenario_id"])
    state["goal_text"] = default_goal_for_skill(scenario["skill"])
    save_state(state)
    return state


def build_session_summary(state: Dict[str, Any]) -> str:
    scenario = get_scenario_by_id(state["selected_scenario_id"])
    if state["current_session"]["blocked_count"] == 0:
        improvement = "You stayed focused on the scenario and kept the structure steady."
    else:
        improvement = "You practiced recovering when the interaction drifted out of scope."
    return (
        f"In {scenario['title'].lower()}, you practiced {SKILL_LABELS[scenario['skill']].lower()}. "
        f"{improvement}"
    )


async def complete_session() -> None:
    state = get_state()
    if not state["messages"]:
        await cl.Message(content="Start a practice exchange before ending the session.").send()
        return

    scenario = get_scenario_by_id(state["selected_scenario_id"])
    started_at = datetime.fromisoformat(state["current_session"]["started_at"])
    duration_minutes = max(1, int((datetime.now() - started_at).total_seconds() / 60) or 1)
    skill = scenario["skill"]
    improvement = max(1, state["confidence_after"] - state["confidence_before"] + 1)
    state["skill_scores"][skill] += improvement

    if state["current_session"]["blocked_count"] == 0:
        state["recent_wins"].insert(
            0,
            f"Completed {scenario['title'].lower()} without leaving the practice scope.",
        )
    else:
        state["recent_wins"].insert(
            0,
            f"Recovered from {state['current_session']['blocked_count']} blocked moment(s) in {scenario['title'].lower()}.",
        )
    state["recent_wins"] = state["recent_wins"][:6]

    summary = {
        "scenario_title": scenario["title"],
        "skill": SKILL_LABELS[skill],
        "difficulty": scenario["difficulty"],
        "completed_at": datetime.now().isoformat(timespec="seconds"),
        "duration_minutes": duration_minutes,
        "confidence_before": state["confidence_before"],
        "confidence_after": state["confidence_after"],
        "intent": state["current_session"]["last_intent"],
        "provider": state["current_session"]["last_provider"],
        "latency_ms": state["current_session"]["last_latency_ms"],
        "summary": build_session_summary(state),
    }
    state["session_history"].insert(0, summary)
    state["messages"] = []
    state["current_session"] = {
        "scenario_id": scenario["id"],
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "user_turns": 0,
        "assistant_turns": 0,
        "last_intent": "general_interaction",
        "last_provider": "not_started",
        "last_latency_ms": 0.0,
        "blocked_count": 0,
    }
    save_state(state)
    await refresh_sidebar()
    await cl.Message(
        content=(
            f"Session saved for **{scenario['title']}**.\n\n"
            f"**What went well**\n- {summary['summary']}\n\n"
            f"**Confidence**\n- Before: {summary['confidence_before']}\n- After: {summary['confidence_after']}\n\n"
            f"**Next focus**\n- {default_goal_for_skill(scenario['skill'])}"
        )
    ).send()


@cl.on_chat_start
async def on_chat_start() -> None:
    state = initial_state()
    save_state(state)
    settings = await cl.ChatSettings(
        [
            Select(
                id="Scenario",
                label="Practice Scenario",
                values=[scenario["title"] for scenario in SCENARIOS],
                initial_index=0,
                description="Choose the social situation you want to practice.",
            ),
            Select(
                id="CoachStyle",
                label="Coach Style",
                values=["Supportive", "Calm", "Direct"],
                initial_index=0,
            ),
            Select(
                id="Difficulty",
                label="Difficulty Preference",
                values=["Balanced", "Comfort zone", "Stretch mode"],
                initial_index=0,
            ),
            Slider(
                id="ConfidenceBefore",
                label="Confidence Before Practice",
                initial=3,
                min=1,
                max=5,
                step=1,
            ),
            Slider(
                id="ConfidenceAfter",
                label="Confidence After Practice",
                initial=3,
                min=1,
                max=5,
                step=1,
            ),
            Slider(
                id="WeeklyGoal",
                label="Weekly Session Goal",
                initial=4,
                min=1,
                max=10,
                step=1,
            ),
            Switch(
                id="ShowHintSidebar",
                label="Show coach hint in sidebar",
                initial=True,
            ),
        ]
    ).send()
    sync_state_from_settings(settings)
    await refresh_sidebar()
    scenario = get_scenario_by_id(get_state()["selected_scenario_id"])
    await cl.Message(
        content=(
            "# Rule-Guided Conversational System\n"
            "A coaching workspace for structured social interaction practice.\n\n"
            f"**Today’s focus:** {scenario['title']}\n"
            f"**Goal:** {get_state()['goal_text']}\n\n"
            "Send one short message describing what you want to practice. "
            "If you want to save the current session, type `/save`."
        )
    ).send()


@cl.on_settings_update
async def on_settings_update(settings: Dict[str, Any]) -> None:
    state = sync_state_from_settings(settings)
    await refresh_sidebar()
    scenario = get_scenario_by_id(state["selected_scenario_id"])
    await cl.Message(
        content=(
            f"Updated the workspace. We’re now focused on **{scenario['title']}** "
            f"with a **{state['coach_style']}** coaching style."
        )
    ).send()


@cl.on_message
async def on_message(message: cl.Message) -> None:
    user_input = (message.content or "").strip()
    if not user_input:
        await cl.Message(content="Send one short situation or response you want to practice.").send()
        return

    if user_input.lower() in {"/save", "save session", "end session"}:
        await complete_session()
        return

    state = get_state()
    state["messages"].append({"role": "user", "content": user_input})
    state["current_session"]["user_turns"] += 1
    save_state(state)

    thinking = cl.Message(content="")
    await thinking.send()

    try:
        payload = await post_chat(user_input)
        assistant_text = payload["response"]
        intent = payload.get("intent", "general_interaction")
        provider = payload.get("provider", "unknown")
        latency_ms = float(payload.get("latency_ms", 0.0))
        blocked = bool(payload.get("blocked", False))
    except Exception as exc:
        assistant_text = (
            "I could not reach the backend right now. Please make sure the FastAPI server "
            "is running, then try again."
        )
        intent = "general_interaction"
        provider = "frontend_error"
        latency_ms = 0.0
        blocked = True
        await cl.Message(content=f"Backend error: `{exc}`").send()

    state = get_state()
    state["messages"].append({"role": "assistant", "content": assistant_text})
    state["current_session"]["assistant_turns"] += 1
    state["current_session"]["last_intent"] = intent
    state["current_session"]["last_provider"] = provider
    state["current_session"]["last_latency_ms"] = latency_ms
    if blocked:
        state["current_session"]["blocked_count"] += 1
    save_state(state)

    scenario = get_scenario_by_id(state["selected_scenario_id"])
    thinking.content = assistant_text
    await thinking.update()
    await refresh_sidebar()


@cl.on_chat_end
async def on_chat_end() -> None:
    save_state(get_state())
