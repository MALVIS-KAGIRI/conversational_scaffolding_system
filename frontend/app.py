from __future__ import annotations

import os
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List

import requests
import streamlit as st


BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")

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

NAV_ITEMS = ["Home", "Practice", "Scenarios", "Insights", "History", "Profile"]


st.set_page_config(
    page_title="Social Interaction Support Guide",
    layout="wide",
    initial_sidebar_state="expanded",
)


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        .stApp {
            background:
                radial-gradient(circle at top left, rgba(111, 180, 160, 0.18), transparent 30%),
                radial-gradient(circle at top right, rgba(237, 151, 116, 0.12), transparent 25%),
                linear-gradient(180deg, #f6f2ea 0%, #fbf8f2 100%);
        }
        .block-container {
            padding-top: 1.5rem;
            padding-bottom: 2rem;
        }
        .card {
            background: rgba(255, 255, 255, 0.82);
            border: 1px solid rgba(37, 62, 62, 0.08);
            border-radius: 18px;
            padding: 1rem 1.1rem;
            box-shadow: 0 8px 30px rgba(37, 62, 62, 0.06);
        }
        .hero {
            background: linear-gradient(135deg, #e9f4ef 0%, #fff7ef 100%);
            border: 1px solid rgba(37, 62, 62, 0.08);
            border-radius: 22px;
            padding: 1.2rem 1.3rem;
            box-shadow: 0 10px 35px rgba(37, 62, 62, 0.08);
        }
        .mini {
            font-size: 0.88rem;
            color: #55605f;
        }
        .section-title {
            font-size: 1.15rem;
            font-weight: 700;
            color: #203637;
            margin-bottom: 0.4rem;
        }
        .soft-label {
            font-size: 0.82rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: #617172;
        }
        .scenario-tag {
            display: inline-block;
            padding: 0.2rem 0.5rem;
            margin-right: 0.35rem;
            margin-top: 0.35rem;
            border-radius: 999px;
            background: #edf3ef;
            color: #365150;
            font-size: 0.78rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def init_state() -> None:
    if "page" not in st.session_state:
        st.session_state.page = "Home"
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "selected_scenario_id" not in st.session_state:
        st.session_state.selected_scenario_id = SCENARIOS[0]["id"]
    if "skill_scores" not in st.session_state:
        st.session_state.skill_scores = {key: 0 for key in SKILL_LABELS}
    if "session_history" not in st.session_state:
        st.session_state.session_history = []
    if "recent_wins" not in st.session_state:
        st.session_state.recent_wins = [
            "Started the first coaching workspace.",
            "Rule-guided practice mode is ready.",
        ]
    if "goal_text" not in st.session_state:
        st.session_state.goal_text = "Ask one natural follow-up question."
    if "weekly_goal" not in st.session_state:
        st.session_state.weekly_goal = 4
    if "coach_style" not in st.session_state:
        st.session_state.coach_style = "Supportive"
    if "difficulty_pref" not in st.session_state:
        st.session_state.difficulty_pref = "Balanced"
    if "theme_pref" not in st.session_state:
        st.session_state.theme_pref = "Calm"
    if "confidence_before" not in st.session_state:
        st.session_state.confidence_before = 3
    if "confidence_after" not in st.session_state:
        st.session_state.confidence_after = 3
    if "current_session" not in st.session_state:
        st.session_state.current_session = {
            "scenario_id": st.session_state.selected_scenario_id,
            "started_at": time.time(),
            "user_turns": 0,
            "assistant_turns": 0,
            "last_intent": "general_interaction",
            "last_provider": "not_started",
            "last_latency_ms": 0.0,
            "blocked_count": 0,
        }


def get_selected_scenario() -> Dict[str, str]:
    scenario_id = st.session_state.selected_scenario_id
    for scenario in SCENARIOS:
        if scenario["id"] == scenario_id:
            return scenario
    return SCENARIOS[0]


def go_to(page: str) -> None:
    st.session_state.page = page
    st.rerun()


def start_scenario(scenario_id: str) -> None:
    st.session_state.selected_scenario_id = scenario_id
    st.session_state.messages = []
    st.session_state.current_session = {
        "scenario_id": scenario_id,
        "started_at": time.time(),
        "user_turns": 0,
        "assistant_turns": 0,
        "last_intent": "general_interaction",
        "last_provider": "not_started",
        "last_latency_ms": 0.0,
        "blocked_count": 0,
    }
    scenario = get_selected_scenario()
    st.session_state.goal_text = default_goal_for_skill(scenario["skill"])
    st.session_state.page = "Practice"
    st.rerun()


def default_goal_for_skill(skill: str) -> str:
    goals = {
        "greeting": "Open warmly and invite the other person in.",
        "follow_ups": "Ask one natural follow-up question.",
        "confidence": "Share one clear opinion without apologizing for it.",
        "conversation_flow": "Use one bridge phrase to keep the exchange moving.",
        "conversation_endings": "End politely while leaving the door open for later.",
    }
    return goals.get(skill, "Practice one focused social skill.")


def recommended_scenario() -> Dict[str, str]:
    weakest_skill = min(
        st.session_state.skill_scores,
        key=lambda skill: st.session_state.skill_scores[skill],
    )
    for scenario in SCENARIOS:
        if scenario["skill"] == weakest_skill:
            return scenario
    return SCENARIOS[0]


def weekly_sessions_count() -> int:
    cutoff = datetime.now() - timedelta(days=7)
    return sum(
        1
        for session in st.session_state.session_history
        if datetime.fromisoformat(session["completed_at"]) >= cutoff
    )


def current_streak() -> int:
    session_days = sorted(
        {datetime.fromisoformat(item["completed_at"]).date() for item in st.session_state.session_history},
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


def average_confidence() -> float:
    if not st.session_state.session_history:
        return 0.0
    total = sum(item["confidence_after"] for item in st.session_state.session_history)
    return round(total / len(st.session_state.session_history), 1)


def call_backend(user_input: str) -> Dict[str, Any]:
    response = requests.post(
        f"{BACKEND_URL}/chat",
        json={"user_input": user_input},
        timeout=90,
    )
    response.raise_for_status()
    return response.json()


def handle_user_turn(user_input: str) -> None:
    st.session_state.messages.append({"role": "user", "content": user_input})
    st.session_state.current_session["user_turns"] += 1

    try:
        payload = call_backend(user_input)
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
        st.error(str(exc))

    st.session_state.messages.append({"role": "assistant", "content": assistant_text})
    st.session_state.current_session["assistant_turns"] += 1
    st.session_state.current_session["last_intent"] = intent
    st.session_state.current_session["last_provider"] = provider
    st.session_state.current_session["last_latency_ms"] = latency_ms
    if blocked:
        st.session_state.current_session["blocked_count"] += 1


def complete_session() -> None:
    if not st.session_state.messages:
        st.info("Start a practice exchange before ending the session.")
        return

    scenario = get_selected_scenario()
    duration_minutes = max(1, int((time.time() - st.session_state.current_session["started_at"]) / 60) or 1)
    skill = scenario["skill"]
    improvement = max(1, st.session_state.confidence_after - st.session_state.confidence_before + 1)
    st.session_state.skill_scores[skill] += improvement

    if st.session_state.current_session["blocked_count"] == 0:
        st.session_state.recent_wins.insert(
            0,
            f"Completed {scenario['title'].lower()} without leaving the practice scope.",
        )
    else:
        st.session_state.recent_wins.insert(
            0,
            f"Recovered from {st.session_state.current_session['blocked_count']} blocked moment(s) in {scenario['title'].lower()}.",
        )
    st.session_state.recent_wins = st.session_state.recent_wins[:6]

    summary = {
        "scenario_title": scenario["title"],
        "skill": SKILL_LABELS[skill],
        "difficulty": scenario["difficulty"],
        "completed_at": datetime.now().isoformat(timespec="seconds"),
        "duration_minutes": duration_minutes,
        "confidence_before": st.session_state.confidence_before,
        "confidence_after": st.session_state.confidence_after,
        "intent": st.session_state.current_session["last_intent"],
        "provider": st.session_state.current_session["last_provider"],
        "latency_ms": st.session_state.current_session["last_latency_ms"],
        "summary": build_session_summary(),
    }
    st.session_state.session_history.insert(0, summary)
    st.session_state.messages = []
    st.session_state.current_session = {
        "scenario_id": scenario["id"],
        "started_at": time.time(),
        "user_turns": 0,
        "assistant_turns": 0,
        "last_intent": "general_interaction",
        "last_provider": "not_started",
        "last_latency_ms": 0.0,
        "blocked_count": 0,
    }
    st.success("Session saved to your progress history.")


def build_session_summary() -> str:
    scenario = get_selected_scenario()
    if st.session_state.current_session["blocked_count"] == 0:
        improvement = "You stayed focused on the scenario and kept the structure steady."
    else:
        improvement = "You practiced recovering when the interaction drifted out of scope."
    return (
        f"In {scenario['title'].lower()}, you practiced {SKILL_LABELS[scenario['skill']].lower()}. "
        f"{improvement}"
    )


def render_top_bar() -> None:
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Streak", f"{current_streak()} day(s)")
    col2.metric("This Week", weekly_sessions_count())
    col3.metric("Confidence Avg", average_confidence())
    col4.metric("Weekly Goal", f"{weekly_sessions_count()}/{st.session_state.weekly_goal}")


def render_sidebar() -> None:
    with st.sidebar:
        st.markdown("## Social Practice Guide")
        st.caption("A structured coaching workspace, not a free-form chatbot.")
        for item in NAV_ITEMS:
            button_type = "primary" if st.session_state.page == item else "secondary"
            if st.button(item, use_container_width=True, type=button_type):
                go_to(item)

        st.markdown("---")
        st.markdown("### Coach Snapshot")
        st.write(f"Style: `{st.session_state.coach_style}`")
        st.write(f"Current goal: `{st.session_state.goal_text}`")
        scenario = get_selected_scenario()
        st.write(f"Scenario: `{scenario['title']}`")


def render_home() -> None:
    scenario = recommended_scenario()
    st.markdown(
        f"""
        <div class="hero">
            <div class="soft-label">Today&apos;s Practice</div>
            <h2 style="margin:0.25rem 0 0.4rem 0; color:#203637;">{scenario["title"]}</h2>
            <div class="mini">{scenario["description"]}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("Start Recommended Session", type="primary", use_container_width=False):
        start_scenario(scenario["id"])

    metric_cols = st.columns(4)
    metric_cols[0].metric("Sessions", len(st.session_state.session_history))
    metric_cols[1].metric("Best Skill", strongest_skill_label())
    metric_cols[2].metric("Focus Area", weakest_skill_label())
    metric_cols[3].metric("Coach Mode", st.session_state.coach_style)

    left, right = st.columns([1.6, 1.0])
    with left:
        st.markdown('<div class="section-title">Skill Map</div>', unsafe_allow_html=True)
        for skill, score in st.session_state.skill_scores.items():
            display_score = min(100, score * 10)
            st.write(SKILL_LABELS[skill])
            st.progress(display_score / 100)

        st.markdown('<div class="section-title">Consistency</div>', unsafe_allow_html=True)
        render_heatmap()

    with right:
        st.markdown('<div class="section-title">Recent Wins</div>', unsafe_allow_html=True)
        for win in st.session_state.recent_wins[:5]:
            st.markdown(f"- {win}")

        st.markdown('<div class="section-title">Next Best Actions</div>', unsafe_allow_html=True)
        st.markdown(f"- Practice `{scenario['title']}` next.")
        st.markdown(f"- Keep today&apos;s goal focused on `{default_goal_for_skill(scenario['skill'])}`.")
        st.markdown("- End your next session with a confidence check-in.")


def render_practice() -> None:
    scenario = get_selected_scenario()
    header_cols = st.columns([2.2, 1.2, 1.2, 1.0])
    header_cols[0].markdown(f"## {scenario['title']}")
    header_cols[1].metric("Difficulty", scenario["difficulty"])
    header_cols[2].metric("Target Skill", SKILL_LABELS[scenario["skill"]])
    current_step = min(4, st.session_state.current_session["user_turns"] + 1)
    header_cols[3].metric("Step", f"{current_step}/4")

    st.markdown(
        f"""
        <div class="card">
            <div class="soft-label">Session Goal</div>
            <div style="font-size:1.05rem; color:#203637; margin-top:0.35rem;">{st.session_state.goal_text}</div>
            <div class="mini" style="margin-top:0.55rem;">Keep the interaction short, specific, and focused on one social skill.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    left, right = st.columns([2.5, 1.0])
    with left:
        st.markdown("### Guided Practice")
        if not st.session_state.messages:
            st.info("Start with one short message describing what you want to practice in this scenario.")

        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.write(message["content"])

        user_input = st.chat_input("Describe your next move or social response")
        if user_input:
            handle_user_turn(user_input)
            st.rerun()

    with right:
        st.markdown("### Coach Panel")
        st.markdown(
            f"""
            <div class="card">
                <div class="soft-label">Hint</div>
                <div style="margin-top:0.35rem;">{coach_hint_for_skill(scenario["skill"])}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown("")
        st.session_state.confidence_before = st.slider(
            "Confidence before practice",
            min_value=1,
            max_value=5,
            value=st.session_state.confidence_before,
        )
        st.session_state.confidence_after = st.slider(
            "Confidence after practice",
            min_value=1,
            max_value=5,
            value=st.session_state.confidence_after,
        )

        if st.button("Need a Different Scenario", use_container_width=True):
            go_to("Scenarios")
        if st.button("End Session and Save", type="primary", use_container_width=True):
            complete_session()
            go_to("History")


def render_scenarios() -> None:
    st.markdown("## Scenario Library")
    contexts = ["All"] + sorted({scenario["context"] for scenario in SCENARIOS})
    difficulties = ["All"] + sorted({scenario["difficulty"] for scenario in SCENARIOS})
    skills = ["All"] + sorted({SKILL_LABELS[scenario["skill"]] for scenario in SCENARIOS})

    filter_cols = st.columns(4)
    selected_context = filter_cols[0].selectbox("Context", contexts)
    selected_difficulty = filter_cols[1].selectbox("Difficulty", difficulties)
    selected_skill = filter_cols[2].selectbox("Skill", skills)
    search = filter_cols[3].text_input("Search", placeholder="Search scenarios")

    filtered = []
    for scenario in SCENARIOS:
        if selected_context != "All" and scenario["context"] != selected_context:
            continue
        if selected_difficulty != "All" and scenario["difficulty"] != selected_difficulty:
            continue
        if selected_skill != "All" and SKILL_LABELS[scenario["skill"]] != selected_skill:
            continue
        haystack = f"{scenario['title']} {scenario['description']}".lower()
        if search and search.lower() not in haystack:
            continue
        filtered.append(scenario)

    recommended = recommended_scenario()
    st.info(f"Recommended next scenario: {recommended['title']}")

    cols = st.columns(2)
    for index, scenario in enumerate(filtered):
        with cols[index % 2]:
            st.markdown(
                f"""
                <div class="card">
                    <div class="soft-label">{scenario["context"]}</div>
                    <div style="font-size:1.1rem; font-weight:700; color:#203637; margin-top:0.25rem;">{scenario["title"]}</div>
                    <div class="mini" style="margin-top:0.4rem;">{scenario["description"]}</div>
                    <div>
                        <span class="scenario-tag">{scenario["difficulty"]}</span>
                        <span class="scenario-tag">{SKILL_LABELS[scenario["skill"]]}</span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button(f"Start {scenario['title']}", key=f"start_{scenario['id']}", use_container_width=True):
                start_scenario(scenario["id"])


def render_insights() -> None:
    st.markdown("## Insights")
    st.caption("A supportive view of how your practice habits and skills are evolving.")

    chart_data = {
        "Confidence": [item["confidence_after"] for item in reversed(st.session_state.session_history[-10:])]
    }
    if chart_data["Confidence"]:
        st.line_chart(chart_data)
    else:
        st.info("Complete a few sessions to unlock confidence trends.")

    skill_cols = st.columns(2)
    with skill_cols[0]:
        st.markdown("### Skill Progress")
        for skill, score in st.session_state.skill_scores.items():
            st.write(f"{SKILL_LABELS[skill]}: {score}")
            st.progress(min(1.0, score / 10))

    with skill_cols[1]:
        st.markdown("### Pattern Detection")
        st.markdown(f"- Strongest area: `{strongest_skill_label()}`")
        st.markdown(f"- Most useful next focus: `{weakest_skill_label()}`")
        st.markdown(
            f"- Average confidence after practice: `{average_confidence()}`"
        )
        st.markdown(
            f"- Sessions completed this week: `{weekly_sessions_count()}`"
        )

    st.markdown("### Practice Heatmap")
    render_heatmap()


def render_history() -> None:
    st.markdown("## Session History")
    if not st.session_state.session_history:
        st.info("No saved sessions yet. Complete one practice session to populate your history.")
        return

    for index, session in enumerate(st.session_state.session_history):
        with st.expander(f"{session['completed_at']} | {session['scenario_title']}"):
            st.write(f"Skill: {session['skill']}")
            st.write(f"Difficulty: {session['difficulty']}")
            st.write(f"Confidence: {session['confidence_before']} -> {session['confidence_after']}")
            st.write(f"Provider: {session['provider']}")
            st.write(f"Latency: {round(session['latency_ms'], 2)} ms")
            st.write(session["summary"])
            if st.button("Practice This Again", key=f"revisit_{index}"):
                scenario = next(
                    (item for item in SCENARIOS if item["title"] == session["scenario_title"]),
                    SCENARIOS[0],
                )
                start_scenario(scenario["id"])


def render_profile() -> None:
    st.markdown("## Profile and Preferences")
    st.session_state.coach_style = st.selectbox(
        "Coach style",
        ["Supportive", "Calm", "Direct"],
        index=["Supportive", "Calm", "Direct"].index(st.session_state.coach_style),
    )
    st.session_state.difficulty_pref = st.selectbox(
        "Difficulty preference",
        ["Balanced", "Comfort zone", "Stretch mode"],
        index=["Balanced", "Comfort zone", "Stretch mode"].index(st.session_state.difficulty_pref),
    )
    st.session_state.theme_pref = st.selectbox(
        "Theme",
        ["Calm", "Warm", "Focus"],
        index=["Calm", "Warm", "Focus"].index(st.session_state.theme_pref),
    )
    st.session_state.weekly_goal = st.slider(
        "Weekly session goal",
        min_value=1,
        max_value=10,
        value=st.session_state.weekly_goal,
    )

    st.markdown("### Trace and Privacy")
    st.checkbox("Enable LangSmith tracing in backend", value=True, disabled=True)
    st.checkbox("Keep practice summaries in local session history", value=True, disabled=True)

    if st.button("Reset Local Progress"):
        for key in ["messages", "session_history", "recent_wins", "skill_scores"]:
            del st.session_state[key]
        init_state()
        st.success("Local dashboard progress reset.")
        st.rerun()


def strongest_skill_label() -> str:
    if not st.session_state.skill_scores:
        return "Not enough data"
    skill = max(st.session_state.skill_scores, key=lambda item: st.session_state.skill_scores[item])
    return SKILL_LABELS[skill]


def weakest_skill_label() -> str:
    if not st.session_state.skill_scores:
        return "Not enough data"
    skill = min(st.session_state.skill_scores, key=lambda item: st.session_state.skill_scores[item])
    return SKILL_LABELS[skill]


def coach_hint_for_skill(skill: str) -> str:
    hints = {
        "greeting": "Start simple: greet, mention the shared context, then invite a response.",
        "follow_ups": "Listen for one detail you can build on with a short question.",
        "confidence": "State one thought clearly before adding extra explanation.",
        "conversation_flow": "Use a bridge phrase like 'That reminds me' or 'How about you?'",
        "conversation_endings": "Close warmly, mention appreciation, and leave the interaction open.",
    }
    return hints.get(skill, "Stay specific, kind, and one step at a time.")


def render_heatmap() -> None:
    today = datetime.now().date()
    day_counts: Dict[str, int] = {}
    for session in st.session_state.session_history:
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
    st.code("\n".join(rows))
    st.caption("- none  . light  o moderate  O strong  # very active")


def main() -> None:
    inject_styles()
    init_state()
    render_sidebar()

    st.title("Rule-Guided Conversational System")
    st.caption("A coaching workspace for structured social interaction practice.")
    render_top_bar()

    page = st.session_state.page
    if page == "Home":
        render_home()
    elif page == "Practice":
        render_practice()
    elif page == "Scenarios":
        render_scenarios()
    elif page == "Insights":
        render_insights()
    elif page == "History":
        render_history()
    elif page == "Profile":
        render_profile()


if __name__ == "__main__":
    main()
