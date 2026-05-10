# frontend.py
"""
Social Interaction Support Guide
All features: debrief, warmup starters, streak freeze, confidence celebration,
session replay, skill unlock, coach style previews, weekly recap, focus shortcut,
typing indicator, session timer, contextual sidebar tips, empty-state illustrations.
"""

from __future__ import annotations

import html
import os
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import uuid4

import requests
import streamlit as st

# ---------------------------------------------------------------------------
# Configuration & Constants
# ---------------------------------------------------------------------------

BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")
NAV_ITEMS = ["Home", "Practice", "Scenarios", "Insights", "History", "Profile"]

SCENARIOS: List[Dict[str, Any]] = [
    {
        "id": "lunch_group",
        "title": "Join a Lunch Conversation",
        "description": "Practice entering an ongoing group conversation without feeling abrupt.",
        "difficulty": "Beginner",
        "skill": "follow_ups",
        "context": "Work",
        "icon": "🍽️",
        "unlock_after": 0,
    },
    {
        "id": "meet_someone_new",
        "title": "Meet Someone New",
        "description": "Practice greeting someone and keeping the exchange going naturally.",
        "difficulty": "Beginner",
        "skill": "greeting",
        "context": "Social",
        "icon": "👋",
        "unlock_after": 0,
    },
    {
        "id": "group_confidence",
        "title": "Speak in a Group Setting",
        "description": "Practice contributing one clear thought in a group discussion.",
        "difficulty": "Intermediate",
        "skill": "confidence",
        "context": "School",
        "icon": "🎤",
        "unlock_after": 0,
    },
    {
        "id": "awkward_silence",
        "title": "Recover From Awkward Silence",
        "description": "Practice restarting a conversation when the energy drops.",
        "difficulty": "Intermediate",
        "skill": "conversation_flow",
        "context": "Social",
        "icon": "🌊",
        "unlock_after": 0,
    },
    {
        "id": "end_conversation",
        "title": "End a Conversation Smoothly",
        "description": "Practice leaving politely while keeping the interaction positive.",
        "difficulty": "Advanced",
        "skill": "conversation_endings",
        "context": "Work",
        "icon": "🤝",
        "unlock_after": 2,   # requires 2 completed intermediate sessions
    },
]

SKILL_LABELS = {
    "greeting": "Greeting",
    "follow_ups": "Follow-ups",
    "confidence": "Confidence",
    "conversation_flow": "Flow",
    "conversation_endings": "Endings",
}

SKILL_ICONS = {
    "greeting": "👋",
    "follow_ups": "💬",
    "confidence": "💪",
    "conversation_flow": "🌊",
    "conversation_endings": "🤝",
}

COACH_STYLE_PREVIEWS: Dict[str, str] = {
    "Supportive": "\"That was a great attempt — you showed real warmth there. What felt most natural to you?\"",
    "Calm": "\"You handled that moment steadily. Let's look at one small thing to refine next.\"",
    "Direct": "\"Good effort. Here's exactly what to change: lead with the topic, then invite a response.\"",
}

# One rotating contextual tip per scenario skill
SCENARIO_TIPS: Dict[str, List[str]] = {
    "greeting": [
        "A shared observation ('busy in here today') is the easiest conversation opener.",
        "Smile first, then speak — it sets the other person at ease before you say a word.",
        "Use their name once early. It creates instant connection.",
    ],
    "follow_ups": [
        "Listen for one concrete word in their reply and ask about that specific thing.",
        "A follow-up question starting with 'What was that like?' almost always works.",
        "Silence after their answer isn't awkward — it signals you're thinking, not ignoring.",
    ],
    "confidence": [
        "Shorter sentences sound more confident than long hedged ones.",
        "Start with 'I think…' not 'I'm not sure but maybe…' to own your view.",
        "Volume matters more than words — speak to the person furthest away.",
    ],
    "conversation_flow": [
        "'That reminds me of…' is the most versatile bridge phrase in social conversation.",
        "If the topic dies, ask about their week — it almost always reopens a thread.",
        "Light laughter at the silence itself ('well, we covered that topic!') resets the energy.",
    ],
    "conversation_endings": [
        "Signal your exit early: 'I should let you go, but…' gives both people a graceful out.",
        "Ending with a forward reference ('let's pick this up next time') leaves things open.",
        "A specific compliment as you leave ('this was genuinely fun') makes the goodbye memorable.",
    ],
}


# ---------------------------------------------------------------------------
# Styling
# ---------------------------------------------------------------------------

def inject_styles() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;0,9..40,600;1,9..40,300&display=swap');

        html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }

        /* ── Sidebar ── */
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #1a3a3c 0%, #0f2426 100%) !important;
            border-right: 1px solid rgba(255,255,255,0.06);
        }
        [data-testid="stSidebar"] * { color: #d4e9e2 !important; }
        [data-testid="stSidebar"] hr { border-color: rgba(255,255,255,0.1) !important; }

        /* ── Hero banner ── */
        .hero-banner {
            background: linear-gradient(135deg, #1a3a3c 0%, #2d6a4f 50%, #1a3a3c 100%);
            border-radius: 20px;
            padding: 2rem 2.2rem;
            margin-bottom: 1.5rem;
            position: relative;
            overflow: hidden;
            box-shadow: 0 8px 32px rgba(26,58,60,0.25);
        }
        .hero-banner::before {
            content: '';
            position: absolute;
            top: -40%; right: -10%;
            width: 300px; height: 300px;
            background: radial-gradient(circle, rgba(82,183,136,0.18) 0%, transparent 70%);
            border-radius: 50%;
        }
        .hero-banner .label {
            font-size: 0.72rem; font-weight: 600; letter-spacing: 0.12em;
            text-transform: uppercase; color: #95d5b2; margin-bottom: 0.5rem;
        }
        .hero-banner h2 {
            font-family: 'DM Serif Display', serif;
            font-size: 1.9rem; color: #ffffff; margin: 0 0 0.5rem 0; line-height: 1.2;
        }
        .hero-banner .desc { color: rgba(255,255,255,0.72); font-size: 0.95rem; max-width: 480px; }

        /* ── Weekly recap ── */
        .recap-banner {
            background: linear-gradient(135deg, #2d6a4f 0%, #52b788 100%);
            border-radius: 16px; padding: 1.2rem 1.6rem; margin-bottom: 1.2rem;
            display: flex; align-items: center; gap: 1rem;
            box-shadow: 0 4px 20px rgba(45,106,79,0.25);
        }
        .recap-banner .rb-icon { font-size: 2rem; }
        .recap-banner .rb-title {
            font-family: 'DM Serif Display', serif;
            font-size: 1.1rem; color: white; margin-bottom: 0.15rem;
        }
        .recap-banner .rb-sub { font-size: 0.84rem; color: rgba(255,255,255,0.78); }

        /* ── Confidence celebration ── */
        .celebrate-banner {
            background: linear-gradient(135deg, #d8f3dc 0%, #b7e4c7 100%);
            border: 1.5px solid #52b788;
            border-radius: 14px; padding: 0.9rem 1.2rem;
            display: flex; align-items: center; gap: 0.8rem;
            margin-bottom: 1rem;
            animation: popIn 0.4s cubic-bezier(0.34,1.56,0.64,1);
        }
        @keyframes popIn {
            from { transform: scale(0.9); opacity: 0; }
            to   { transform: scale(1);   opacity: 1; }
        }
        .celebrate-banner .cb-text {
            font-weight: 600; color: #1b4332; font-size: 0.95rem;
        }

        /* ── Stat cards ── */
        .stat-row {
            display: grid; grid-template-columns: repeat(4,1fr); gap: 0.9rem; margin-bottom: 1.5rem;
        }
        .stat-card {
            background: #ffffff; border: 1px solid #e8eeec; border-radius: 14px;
            padding: 1rem 1.2rem; box-shadow: 0 2px 12px rgba(32,54,55,0.06);
            transition: transform 0.18s, box-shadow 0.18s;
        }
        .stat-card:hover { transform: translateY(-2px); box-shadow: 0 6px 20px rgba(32,54,55,0.1); }
        .stat-card .icon { font-size: 1.4rem; margin-bottom: 0.3rem; }
        .stat-card .val { font-family: 'DM Serif Display', serif; font-size: 1.6rem; color: #1a3a3c; line-height:1; }
        .stat-card .lbl { font-size: 0.75rem; font-weight: 500; color: #6b8f8e; text-transform: uppercase; letter-spacing:0.08em; margin-top:0.2rem; }

        /* ── Skill bars ── */
        .skill-row { display:flex; align-items:center; gap:0.75rem; margin-bottom:0.75rem; }
        .skill-icon { font-size:1.1rem; width:24px; text-align:center; }
        .skill-name { font-size:0.82rem; font-weight:600; color:#2d4a4b; width:85px; flex-shrink:0; }
        .skill-track { flex:1; height:7px; background:#e8eeec; border-radius:999px; overflow:hidden; }
        .skill-fill { height:100%; border-radius:999px; background:linear-gradient(90deg,#52b788,#2d6a4f); }
        .skill-score { font-size:0.78rem; font-weight:700; color:#2d6a4f; width:28px; text-align:right; }

        /* ── Scenario cards ── */
        .scenario-card {
            background:#ffffff; border:1px solid #e0eae7; border-radius:16px;
            padding:1.2rem 1.4rem; margin-bottom:0.8rem;
            box-shadow:0 2px 10px rgba(32,54,55,0.05);
            transition:transform 0.18s, box-shadow 0.18s, border-color 0.18s;
            position:relative;
        }
        .scenario-card:hover { transform:translateY(-2px); box-shadow:0 8px 24px rgba(32,54,55,0.1); border-color:#52b788; }
        .scenario-card.locked { opacity:0.55; pointer-events:none; filter:grayscale(0.4); }
        .scenario-card .s-icon { font-size:1.6rem; margin-bottom:0.4rem; }
        .scenario-card .s-title { font-family:'DM Serif Display',serif; font-size:1.05rem; color:#1a3a3c; margin-bottom:0.3rem; }
        .scenario-card .s-desc { font-size:0.86rem; color:#4c6b6a; margin-bottom:0.7rem; line-height:1.5; }
        .lock-badge {
            position:absolute; top:12px; right:12px;
            background:#f0f0f0; color:#888; font-size:0.72rem; font-weight:600;
            padding:0.2rem 0.6rem; border-radius:999px;
        }
        .tag { display:inline-block; padding:0.2rem 0.65rem; border-radius:999px; font-size:0.74rem; font-weight:600; margin-right:0.35rem; }
        .tag-diff-beginner   { background:#d8f3dc; color:#1b5e35; }
        .tag-diff-intermediate { background:#fff0dc; color:#7a4600; }
        .tag-diff-advanced   { background:#ffe0e2; color:#8b1f26; }
        .tag-skill { background:#e8f4f3; color:#1a3a3c; }
        .tag-ctx   { background:#f0eeff; color:#3d2b8e; }
        .recommended-badge {
            position:absolute; top:-10px; right:14px;
            background:linear-gradient(90deg,#52b788,#2d6a4f); color:white;
            font-size:0.7rem; font-weight:700; letter-spacing:0.08em;
            padding:0.2rem 0.7rem; border-radius:999px; text-transform:uppercase;
        }

        /* ── Warmup starters ── */
        .starter-grid { display:flex; flex-direction:column; gap:0.5rem; margin-bottom:1rem; }
        .starter-btn {
            background:#f0f8f4; border:1.5px solid #b7e4c7; border-radius:12px;
            padding:0.65rem 1rem; cursor:pointer;
            font-size:0.88rem; color:#1b4332; text-align:left;
            transition:background 0.15s, border-color 0.15s;
        }
        .starter-btn:hover { background:#d8f3dc; border-color:#52b788; }

        /* ── Typing indicator ── */
        .typing-indicator {
            display:inline-flex; align-items:center; gap:5px; padding:0.5rem 0.8rem;
            background:#f0f8f4; border-radius:12px; margin:0.4rem 0;
        }
        .typing-dot {
            width:7px; height:7px; background:#52b788; border-radius:50%;
            animation:typingBounce 1.2s infinite ease-in-out;
        }
        .typing-dot:nth-child(2) { animation-delay:0.2s; }
        .typing-dot:nth-child(3) { animation-delay:0.4s; }
        @keyframes typingBounce {
            0%,60%,100% { transform:translateY(0); }
            30%          { transform:translateY(-6px); }
        }

        /* ── Practice UI ── */
        .practice-header {
            background:linear-gradient(135deg,#e8f4f3 0%,#f7f1e8 100%);
            border:1px solid rgba(32,54,55,0.08); border-radius:16px;
            padding:1.1rem 1.4rem; margin-bottom:1.2rem;
        }
        .practice-header .ph-label {
            font-size:0.72rem; font-weight:600; letter-spacing:0.1em;
            text-transform:uppercase; color:#4c6b6a;
        }
        .practice-header h3 { font-family:'DM Serif Display',serif; color:#1a3a3c; margin:0.25rem 0 0.3rem; }
        .practice-header .ph-sub { font-size:0.88rem; color:#4c6b6a; }

        .coach-panel {
            background:#f7faf9; border:1px solid #dceae7; border-radius:16px; padding:1.2rem;
        }
        .coach-panel h4 { font-family:'DM Serif Display',serif; font-size:1.1rem; color:#1a3a3c; margin:0 0 0.8rem; }
        .coach-hint {
            background:linear-gradient(135deg,#d8f3dc,#b7e4c7); border-radius:12px;
            padding:0.9rem 1rem; font-size:0.9rem; color:#1b4332; line-height:1.5; margin-bottom:1rem;
        }
        .coach-tip {
            background:#fff9ee; border:1px solid #f4d58d; border-radius:10px;
            padding:0.65rem 0.9rem; font-size:0.82rem; color:#7a4600; margin-bottom:0.8rem;
        }
        .coach-meta-row { display:flex; flex-direction:column; gap:0.5rem; margin-bottom:1rem; }
        .coach-meta-item .cm-label { font-size:0.7rem; font-weight:600; text-transform:uppercase; letter-spacing:0.09em; color:#6b8f8e; }
        .coach-meta-item .cm-value { font-size:0.9rem; font-weight:600; color:#1a3a3c; }

        .session-timer {
            background:rgba(26,58,60,0.06); border-radius:8px;
            padding:0.4rem 0.8rem; font-size:0.8rem; font-weight:600;
            color:#1a3a3c; text-align:center; margin-bottom:0.8rem;
            letter-spacing:0.06em;
        }

        /* ── Step indicator ── */
        .step-indicator { display:flex; gap:0.4rem; margin-bottom:1rem; }
        .step-dot { height:6px; border-radius:999px; transition:all 0.3s; }
        .step-dot.done   { background:#52b788; flex:1; }
        .step-dot.active { background:#2d6a4f; flex:2; }
        .step-dot.todo   { background:#d0e4df; flex:1; }

        /* ── Debrief card ── */
        .debrief-card {
            background:#ffffff; border:1.5px solid #b7e4c7; border-radius:18px;
            padding:1.6rem; margin-top:1rem;
            box-shadow:0 4px 20px rgba(45,106,79,0.1);
            animation:popIn 0.5s cubic-bezier(0.34,1.56,0.64,1);
        }
        .debrief-card .dc-title {
            font-family:'DM Serif Display',serif; font-size:1.3rem;
            color:#1a3a3c; margin-bottom:1.2rem;
        }
        .debrief-section { margin-bottom:1rem; }
        .debrief-section .ds-label {
            font-size:0.72rem; font-weight:700; text-transform:uppercase;
            letter-spacing:0.1em; margin-bottom:0.3rem;
        }
        .debrief-section .ds-text {
            font-size:0.92rem; color:#2d4a4b; line-height:1.55;
        }
        .ds-went-well .ds-label { color:#2d6a4f; }
        .ds-improve   .ds-label { color:#7a4600; }
        .ds-tip       .ds-label { color:#3d2b8e; }
        .ds-encourage {
            background:linear-gradient(135deg,#1a3a3c,#2d6a4f);
            border-radius:12px; padding:0.9rem 1.1rem; margin-top:0.8rem;
            font-size:0.92rem; color:rgba(255,255,255,0.9); line-height:1.5;
            font-style:italic;
        }

        /* ── Insights ── */
        .insights-kpi-grid {
            display:grid; grid-template-columns:repeat(4,1fr); gap:0.9rem; margin-bottom:1.8rem;
        }
        .kpi-card {
            background:#ffffff; border:1px solid #e0eae7; border-radius:16px;
            padding:1.2rem 1.4rem; box-shadow:0 2px 12px rgba(32,54,55,0.06);
            transition:transform 0.18s;
        }
        .kpi-card:hover { transform:translateY(-2px); }
        .kpi-card .kpi-icon { font-size:1.6rem; margin-bottom:0.4rem; }
        .kpi-card .kpi-val { font-family:'DM Serif Display',serif; font-size:2rem; color:#1a3a3c; line-height:1; margin-bottom:0.15rem; }
        .kpi-card .kpi-label { font-size:0.75rem; font-weight:600; color:#6b8f8e; text-transform:uppercase; letter-spacing:0.08em; }
        .kpi-card .kpi-delta { font-size:0.8rem; margin-top:0.35rem; font-weight:600; }
        .kpi-delta.up { color:#2d6a4f; }
        .kpi-delta.neutral { color:#6b8f8e; }

        .section-header { display:flex; align-items:baseline; gap:0.6rem; margin:1.6rem 0 0.8rem; }
        .section-header h3 { font-family:'DM Serif Display',serif; font-size:1.25rem; color:#1a3a3c; margin:0; }
        .section-header .sh-sub { font-size:0.82rem; color:#6b8f8e; }

        .insight-callout {
            background:linear-gradient(135deg,#1a3a3c 0%,#2d6a4f 100%);
            border-radius:16px; padding:1.4rem 1.6rem; color:white; margin-bottom:1rem;
        }
        .insight-callout .ic-label {
            font-size:0.72rem; font-weight:600; letter-spacing:0.1em;
            text-transform:uppercase; color:#95d5b2; margin-bottom:0.4rem;
        }
        .insight-callout .ic-text { font-family:'DM Serif Display',serif; font-size:1.1rem; line-height:1.4; }

        /* ── Heatmap ── */
        .heatmap-week { display:flex; gap:4px; }
        .heatmap-cell { width:18px; height:18px; border-radius:4px; flex-shrink:0; }
        .hm-0 { background:#e8eeec; } .hm-1 { background:#95d5b2; }
        .hm-2 { background:#52b788; } .hm-3 { background:#2d6a4f; } .hm-4 { background:#1b4332; }
        .hm-day-label { width:18px; font-size:0.6rem; color:#6b8f8e; text-align:center; }

        /* ── History ── */
        .history-card {
            background:#ffffff; border:1px solid #e0eae7; border-radius:14px;
            padding:1.1rem 1.4rem; margin-bottom:0.75rem;
            box-shadow:0 2px 10px rgba(32,54,55,0.04);
        }
        .history-card .hc-top { display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:0.5rem; }
        .history-card .hc-title { font-family:'DM Serif Display',serif; font-size:1rem; color:#1a3a3c; }
        .history-card .hc-date { font-size:0.75rem; color:#6b8f8e; }
        .conf-arrow { display:inline-flex; align-items:center; gap:4px; font-size:0.85rem; font-weight:600; color:#2d6a4f; }

        /* ── Transcript replay ── */
        .transcript-msg {
            padding:0.55rem 0.9rem; border-radius:12px; margin-bottom:0.4rem;
            font-size:0.86rem; line-height:1.5; max-width:88%;
        }
        .transcript-user { background:#e8f4f3; color:#1a3a3c; margin-left:auto; text-align:right; }
        .transcript-coach { background:#f7f7f7; color:#2d4a4b; }

        /* ── Profile ── */
        .profile-section {
            background:#ffffff; border:1px solid #e0eae7; border-radius:16px;
            padding:1.4rem 1.6rem; margin-bottom:1rem;
            box-shadow:0 2px 12px rgba(32,54,55,0.05);
        }
        .profile-section h4 { font-family:'DM Serif Display',serif; font-size:1.1rem; color:#1a3a3c; margin:0 0 1rem; }
        .style-preview {
            background:#f7faf9; border-left:3px solid #52b788; border-radius:0 10px 10px 0;
            padding:0.6rem 1rem; font-size:0.84rem; color:#2d4a4b;
            font-style:italic; margin-top:0.5rem;
        }
        .streak-freeze-badge {
            display:inline-flex; align-items:center; gap:0.4rem;
            background:#fff9ee; border:1px solid #f4d58d;
            border-radius:999px; padding:0.3rem 0.8rem;
            font-size:0.8rem; font-weight:600; color:#7a4600;
        }

        /* ── Sidebar snapshot ── */
        .snapshot-row {
            display:flex; justify-content:space-between; align-items:center;
            padding:0.4rem 0; border-bottom:1px solid rgba(255,255,255,0.07); font-size:0.85rem;
        }
        .snapshot-row:last-child { border-bottom:none; }
        .snapshot-key { color:rgba(255,255,255,0.5); }
        .snapshot-val { color:#95d5b2; font-weight:600; }

        /* ── Wins ── */
        .win-item { display:flex; align-items:flex-start; gap:0.6rem; padding:0.65rem 0; border-bottom:1px solid #f0f4f3; font-size:0.88rem; color:#2d4a4b; }
        .win-item:last-child { border-bottom:none; }
        .win-bullet { width:7px; height:7px; border-radius:50%; background:#52b788; margin-top:6px; flex-shrink:0; }

        /* ── Empty states ── */
        .empty-state { text-align:center; padding:3rem 2rem; }
        .empty-state svg { margin-bottom:1.2rem; }
        .empty-state .es-title { font-family:'DM Serif Display',serif; font-size:1.3rem; color:#1a3a3c; margin-bottom:0.4rem; }
        .empty-state .es-sub { font-size:0.9rem; color:#6b8f8e; max-width:280px; margin:0 auto; }

        /* ── Page typography ── */
        .page-title { font-family:'DM Serif Display',serif; font-size:2rem; color:#1a3a3c; margin-bottom:0.2rem; }
        .page-caption { font-size:0.9rem; color:#6b8f8e; margin-bottom:1.4rem; }

        /* ── Streamlit overrides ── */
        .stButton > button[kind="primary"] {
            background:linear-gradient(135deg,#2d6a4f,#1a3a3c) !important;
            border:none !important; border-radius:10px !important;
            font-weight:600 !important; letter-spacing:0.02em !important;
            padding:0.55rem 1.2rem !important; transition:opacity 0.2s !important;
        }
        .stButton > button[kind="primary"]:hover { opacity:0.88 !important; }
        .stButton > button:not([kind="primary"]) {
            border-radius:10px !important; border:1.5px solid #d0e4df !important; font-weight:500 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------

def init_state() -> None:
    defaults: Dict[str, Any] = {
        "frontend_user_id": f"user-{uuid4().hex}",
        "backend_session_id": f"session-{uuid4().hex}",
        "messages": [],
        "active_page": "Home",
        "selected_scenario_id": SCENARIOS[0]["id"],
        "skill_scores": {key: 0 for key in SKILL_LABELS},
        "session_history": [],
        "recent_wins": [
            "Started the first coaching workspace.",
            "Rule-guided practice mode is ready.",
        ],
        "goal_text": "Ask one natural follow-up question.",
        "weekly_goal": 4,
        "coach_style": "Supportive",
        "difficulty_pref": "Balanced",
        "theme_pref": "Calm",
        "confidence_before": 3,
        "confidence_after": 3,
        "streak_freeze_used": False,
        "streak_freeze_enabled": True,
        "warmup_starters": [],
        "warmup_loading": False,
        "last_debrief": None,          # stores DebriefResponse dict after session ends
        "show_debrief": False,
        "tip_index": {},               # {scenario_id: tip_index}
        "current_session": {
            "scenario_id": SCENARIOS[0]["id"],
            "started_at": time.time(),
            "user_turns": 0,
            "assistant_turns": 0,
            "last_intent": "general_interaction",
            "last_provider": "not_started",
            "last_latency_ms": 0.0,
            "blocked_count": 0,
        },
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def get_selected_scenario() -> Dict[str, Any]:
    sid = st.session_state.selected_scenario_id
    return next((s for s in SCENARIOS if s["id"] == sid), SCENARIOS[0])


def default_goal_for_skill(skill: str) -> str:
    return {
        "greeting": "Open warmly and invite the other person in.",
        "follow_ups": "Ask one natural follow-up question.",
        "confidence": "Share one clear opinion without apologizing for it.",
        "conversation_flow": "Use one bridge phrase to keep the exchange moving.",
        "conversation_endings": "End politely while leaving the door open for later.",
    }.get(skill, "Practice one focused social skill.")


def recommended_scenario() -> Dict[str, Any]:
    weakest = min(st.session_state.skill_scores, key=lambda s: st.session_state.skill_scores[s])
    return next((s for s in SCENARIOS if s["skill"] == weakest), SCENARIOS[0])


def weekly_sessions_count() -> int:
    cutoff = datetime.now() - timedelta(days=7)
    return sum(
        1 for s in st.session_state.session_history
        if datetime.fromisoformat(s["completed_at"]) >= cutoff
    )


def current_streak() -> int:
    session_days = sorted(
        {datetime.fromisoformat(s["completed_at"]).date() for s in st.session_state.session_history},
        reverse=True,
    )
    streak = 0
    cursor = datetime.now().date()

    # Apply streak freeze: if today has no session, treat yesterday as today
    if st.session_state.get("streak_freeze_enabled") and not st.session_state.get("streak_freeze_used"):
        today_has_session = any(
            datetime.fromisoformat(s["completed_at"]).date() == cursor
            for s in st.session_state.session_history
        )
        if not today_has_session and session_days and session_days[0] == cursor - timedelta(days=1):
            # User has a streak through yesterday — freeze protects it
            cursor = cursor - timedelta(days=1)

    for d in session_days:
        if d == cursor:
            streak += 1
            cursor -= timedelta(days=1)
        elif d == cursor - timedelta(days=1) and streak == 0:
            cursor = d
            streak += 1
            cursor -= timedelta(days=1)
        else:
            break
    return streak


def average_confidence() -> float:
    hist = st.session_state.session_history
    return round(sum(s["confidence_after"] for s in hist) / len(hist), 1) if hist else 0.0


def strongest_skill_label() -> str:
    if not any(v > 0 for v in st.session_state.skill_scores.values()):
        return "N/A"
    skill = max(st.session_state.skill_scores, key=st.session_state.skill_scores.get)
    return SKILL_LABELS[skill]


def weakest_skill_label() -> str:
    skill = min(st.session_state.skill_scores, key=st.session_state.skill_scores.get)
    return SKILL_LABELS[skill]


def coach_hint_for_skill(skill: str) -> str:
    return {
        "greeting": "Start simple: greet, mention the shared context, then invite a response.",
        "follow_ups": "Listen for one detail you can build on with a short question.",
        "confidence": "State one thought clearly before adding extra explanation.",
        "conversation_flow": "Use a bridge phrase like 'That reminds me' or 'How about you?'",
        "conversation_endings": "Close warmly, mention appreciation, and leave the interaction open.",
    }.get(skill, "Stay specific, kind, and one step at a time.")


def intermediate_sessions_count() -> int:
    return sum(1 for s in st.session_state.session_history if s.get("difficulty") == "Intermediate")


def is_scenario_unlocked(scenario: Dict[str, Any]) -> bool:
    required = scenario.get("unlock_after", 0)
    if required == 0:
        return True
    return intermediate_sessions_count() >= required


def get_contextual_tip(scenario_id: str, skill: str) -> str:
    tips = SCENARIO_TIPS.get(skill, ["Stay focused and take it one step at a time."])
    idx_map = st.session_state.tip_index
    current = idx_map.get(scenario_id, 0)
    return tips[current % len(tips)]


def advance_tip(scenario_id: str, skill: str) -> None:
    tips = SCENARIO_TIPS.get(skill, [""])
    current = st.session_state.tip_index.get(scenario_id, 0)
    st.session_state.tip_index[scenario_id] = (current + 1) % len(tips)


def is_monday() -> bool:
    return datetime.now().weekday() == 0


def last_week_summary() -> Optional[Dict[str, Any]]:
    """Return stats for the previous Mon–Sun week."""
    today = datetime.now().date()
    last_monday = today - timedelta(days=today.weekday() + 7)
    last_sunday = last_monday + timedelta(days=6)
    hist = st.session_state.session_history
    week_sessions = [
        s for s in hist
        if last_monday <= datetime.fromisoformat(s["completed_at"]).date() <= last_sunday
    ]
    if not week_sessions:
        return None
    avg_conf = round(sum(s["confidence_after"] for s in week_sessions) / len(week_sessions), 1)
    skill_counts: Dict[str, int] = {}
    for s in week_sessions:
        skill_counts[s["skill"]] = skill_counts.get(s["skill"], 0) + 1
    top_skill = max(skill_counts, key=skill_counts.get)
    return {"count": len(week_sessions), "avg_conf": avg_conf, "top_skill": top_skill}


# ---------------------------------------------------------------------------
# Backend calls
# ---------------------------------------------------------------------------

def call_backend(user_input: str) -> Dict[str, Any]:
    scenario = get_selected_scenario()
    r = requests.post(
        f"{BACKEND_URL}/chat",
        json={
            "user_input": user_input,
            "user_id": st.session_state.frontend_user_id,
            "session_id": st.session_state.backend_session_id,
            "selected_scenario": scenario["id"],
            "goal_text": st.session_state.goal_text,
            "coach_style": st.session_state.coach_style,
        },
        timeout=90,
    )
    r.raise_for_status()
    return r.json()


def call_debrief(messages: List[Dict[str, str]]) -> Optional[Dict[str, Any]]:
    scenario = get_selected_scenario()
    try:
        r = requests.post(
            f"{BACKEND_URL}/debrief",
            json={
                "messages": messages,
                "user_id": st.session_state.frontend_user_id,
                "session_id": st.session_state.backend_session_id,
                "scenario_title": scenario["title"],
                "scenario_skill": scenario["skill"],
                "goal_text": st.session_state.goal_text,
                "coach_style": st.session_state.coach_style,
                "confidence_before": st.session_state.confidence_before,
                "confidence_after": st.session_state.confidence_after,
            },
            timeout=90,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.warning(f"Debrief unavailable: {e}")
        return None


def call_warmup(scenario: Dict[str, Any]) -> List[str]:
    try:
        r = requests.post(
            f"{BACKEND_URL}/warmup",
            json={
                "scenario_id": scenario["id"],
                "user_id": st.session_state.frontend_user_id,
                "session_id": st.session_state.backend_session_id,
                "scenario_title": scenario["title"],
                "scenario_skill": scenario["skill"],
                "goal_text": st.session_state.goal_text,
                "coach_style": st.session_state.coach_style,
            },
            timeout=30,
        )
        r.raise_for_status()
        return r.json().get("starters", [])
    except Exception:
        return []


def call_reset_session() -> bool:
    try:
        r = requests.post(
            f"{BACKEND_URL}/session/reset",
            json={
                "user_id": st.session_state.frontend_user_id,
                "session_id": st.session_state.backend_session_id,
            },
            timeout=20,
        )
        r.raise_for_status()
        return True
    except Exception as e:
        st.warning(f"Could not reset backend session memory: {e}")
        return False


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------

def start_scenario(scenario_id: str) -> None:
    scenario = next((s for s in SCENARIOS if s["id"] == scenario_id), SCENARIOS[0])
    st.session_state.selected_scenario_id = scenario_id
    st.session_state.backend_session_id = f"session-{uuid4().hex}"
    st.session_state.messages = []
    st.session_state.last_debrief = None
    st.session_state.show_debrief = False
    st.session_state.warmup_starters = []
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
    st.session_state.goal_text = default_goal_for_skill(scenario["skill"])
    st.session_state.active_page = "Practice"
    st.rerun()


def reset_current_practice_session() -> None:
    call_reset_session()
    scenario = get_selected_scenario()
    st.session_state.backend_session_id = f"session-{uuid4().hex}"
    st.session_state.messages = []
    st.session_state.last_debrief = None
    st.session_state.show_debrief = False
    st.session_state.warmup_starters = []
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
    st.rerun()


# ---------------------------------------------------------------------------
# Shared components
# ---------------------------------------------------------------------------

def render_skill_bars(scores: Dict[str, int]) -> None:
    for skill, score in scores.items():
        pct = min(100, score * 10)
        st.markdown(
            f"""
            <div class="skill-row">
                <div class="skill-icon">{SKILL_ICONS.get(skill,"•")}</div>
                <div class="skill-name">{SKILL_LABELS[skill]}</div>
                <div class="skill-track"><div class="skill-fill" style="width:{pct}%"></div></div>
                <div class="skill-score">{score}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_heatmap_html() -> None:
    today = datetime.now().date()
    day_counts: Dict[str, int] = {}
    for session in st.session_state.session_history:
        day = datetime.fromisoformat(session["completed_at"]).date().isoformat()
        day_counts[day] = day_counts.get(day, 0) + 1

    label_html = "".join(
        f'<div class="hm-day-label">{d}</div>' for d in ["M","T","W","T","F","S","S"]
    )
    weeks_html = ""
    for week in range(12):
        cells = ""
        for day_offset in range(7):
            days_ago = (11 - week) * 7 + (6 - day_offset)
            date_val = today - timedelta(days=days_ago)
            count = day_counts.get(date_val.isoformat(), 0)
            level = min(count, 4)
            cells += f'<div class="heatmap-cell hm-{level}" title="{date_val}: {count} session(s)"></div>'
        weeks_html += f'<div class="heatmap-week">{cells}</div>'

    legend_html = "".join(
        f'<div style="display:inline-flex;align-items:center;gap:4px;margin-right:12px;">'
        f'<div class="heatmap-cell hm-{i}" style="width:14px;height:14px;"></div>'
        f'<span style="font-size:0.72rem;color:#6b8f8e;">{l}</span></div>'
        for i, l in enumerate(["None","Light","Moderate","Active","Peak"])
    )
    st.markdown(
        f"""
        <div style="overflow-x:auto;padding-bottom:0.4rem;">
            <div style="display:flex;gap:4px;margin-bottom:4px;">{label_html}</div>
            <div style="display:flex;flex-direction:column;gap:4px;">{weeks_html}</div>
        </div>
        <div style="margin-top:0.6rem;">{legend_html}</div>
        """,
        unsafe_allow_html=True,
    )


def render_empty_state(icon_svg: str, title: str, subtitle: str) -> None:
    st.markdown(
        f"""
        <div class="empty-state">
            {icon_svg}
            <div class="es-title">{title}</div>
            <div class="es-sub">{subtitle}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


EMPTY_HISTORY_SVG = """
<svg width="80" height="80" viewBox="0 0 80 80" fill="none" xmlns="http://www.w3.org/2000/svg">
  <circle cx="40" cy="40" r="38" fill="#e8f4f3" stroke="#b7e4c7" stroke-width="2"/>
  <rect x="22" y="24" width="36" height="8" rx="4" fill="#95d5b2"/>
  <rect x="22" y="36" width="28" height="6" rx="3" fill="#b7e4c7"/>
  <rect x="22" y="46" width="20" height="6" rx="3" fill="#d8f3dc"/>
  <circle cx="55" cy="54" r="10" fill="#2d6a4f"/>
  <text x="55" y="58" text-anchor="middle" font-size="12" fill="white">+</text>
</svg>"""

EMPTY_INSIGHTS_SVG = """
<svg width="80" height="80" viewBox="0 0 80 80" fill="none" xmlns="http://www.w3.org/2000/svg">
  <circle cx="40" cy="40" r="38" fill="#e8f4f3" stroke="#b7e4c7" stroke-width="2"/>
  <rect x="18" y="52" width="8" height="14" rx="3" fill="#95d5b2"/>
  <rect x="30" y="40" width="8" height="26" rx="3" fill="#52b788"/>
  <rect x="42" y="30" width="8" height="36" rx="3" fill="#2d6a4f"/>
  <rect x="54" y="44" width="8" height="22" rx="3" fill="#95d5b2"/>
  <path d="M22 38 L34 28 L46 20 L58 32" stroke="#1a3a3c" stroke-width="2.5" stroke-linecap="round" fill="none"/>
</svg>"""


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

def home_page() -> None:
    scenario = recommended_scenario()

    # ── Weekly recap (Mondays only, if last week had sessions) ──
    if is_monday():
        recap = last_week_summary()
        if recap:
            st.markdown(
                f"""
                <div class="recap-banner">
                    <div class="rb-icon">📊</div>
                    <div>
                        <div class="rb-title">Last week: {recap['count']} session(s) completed</div>
                        <div class="rb-sub">Avg confidence {recap['avg_conf']}/5 · Most practiced: {recap['top_skill']}</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown('<div class="page-title">Good to see you 👋</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-caption">Your personal social skills coaching workspace.</div>', unsafe_allow_html=True)

    # Hero
    st.markdown(
        f"""
        <div class="hero-banner">
            <div class="label">Today's Recommendation</div>
            <h2>{scenario["icon"]} {scenario["title"]}</h2>
            <div class="desc">{scenario["description"]}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_start, col_focus = st.columns([1, 1])
    with col_start:
        if st.button("▶  Start Recommended Session", type="primary", use_container_width=True):
            start_scenario(scenario["id"])
    with col_focus:
        # ── "What do I work on?" shortcut ──
        weakest_key = min(st.session_state.skill_scores, key=lambda s: st.session_state.skill_scores[s])
        weakest_scenario = next((s for s in SCENARIOS if s["skill"] == weakest_key), SCENARIOS[0])
        if st.button(f"🎯  Focus: {SKILL_LABELS[weakest_key]}", use_container_width=True):
            start_scenario(weakest_scenario["id"])

    st.markdown("<div style='height:0.6rem'></div>", unsafe_allow_html=True)

    # Stats
    total = len(st.session_state.session_history)
    streak = current_streak()
    avg_conf = average_confidence()
    weekly = weekly_sessions_count()
    goal = st.session_state.weekly_goal

    freeze_icon = "🛡️" if st.session_state.streak_freeze_enabled else "🔥"
    st.markdown(
        f"""
        <div class="stat-row">
            <div class="stat-card">
                <div class="icon">📚</div>
                <div class="val">{total}</div>
                <div class="lbl">Sessions Total</div>
            </div>
            <div class="stat-card">
                <div class="icon">{freeze_icon}</div>
                <div class="val">{streak}</div>
                <div class="lbl">Day Streak</div>
            </div>
            <div class="stat-card">
                <div class="icon">📈</div>
                <div class="val">{avg_conf if avg_conf else "—"}</div>
                <div class="lbl">Avg Confidence</div>
            </div>
            <div class="stat-card">
                <div class="icon">🎯</div>
                <div class="val">{weekly}/{goal}</div>
                <div class="lbl">This Week</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_left, col_right = st.columns(2)

    with col_left:
        st.markdown(
            '<div class="section-header"><h3>Skill Map</h3><span class="sh-sub">Your current progress</span></div>',
            unsafe_allow_html=True,
        )
        render_skill_bars(st.session_state.skill_scores)

    with col_right:
        st.markdown(
            '<div class="section-header"><h3>Recent Wins</h3></div>',
            unsafe_allow_html=True,
        )
        wins_html = "".join(
            f'<div class="win-item"><div class="win-bullet"></div><div>{w}</div></div>'
            for w in st.session_state.recent_wins[:5]
        )
        st.markdown(
            f'<div style="background:#fff;border:1px solid #e0eae7;border-radius:14px;padding:0.6rem 1rem;">{wins_html}</div>',
            unsafe_allow_html=True,
        )

        st.markdown('<div class="section-header"><h3>Next Steps</h3></div>', unsafe_allow_html=True)
        for step in [
            f"Practice **{scenario['title']}** next",
            f"Focus: *{default_goal_for_skill(scenario['skill'])}*",
            "End next session with a confidence check-in",
        ]:
            st.markdown(f"→ {step}")

    st.markdown(
        '<div class="section-header"><h3>Practice Consistency</h3><span class="sh-sub">Last 12 weeks</span></div>',
        unsafe_allow_html=True,
    )
    render_heatmap_html()


def practice_page() -> None:
    scenario = get_selected_scenario()
    turns = st.session_state.current_session["user_turns"]
    total_steps = 4
    current_step = min(total_steps, turns + 1)

    st.markdown('<div class="page-title">Practice</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="page-caption">{scenario["icon"]} {scenario["title"]}</div>', unsafe_allow_html=True)

    # ── Show debrief if available ──
    if st.session_state.get("show_debrief") and st.session_state.get("last_debrief"):
        debrief = st.session_state.last_debrief
        st.markdown(
            f"""
            <div class="debrief-card">
                <div class="dc-title">🎓 Session Debrief</div>
                <div class="debrief-section ds-went-well">
                    <div class="ds-label">✅ What went well</div>
                    <div class="ds-text">{html.escape(debrief.get('went_well',''))}</div>
                </div>
                <div class="debrief-section ds-improve">
                    <div class="ds-label">📍 To work on next</div>
                    <div class="ds-text">{html.escape(debrief.get('improve',''))}</div>
                </div>
                <div class="debrief-section ds-tip">
                    <div class="ds-label">💡 Micro-tip</div>
                    <div class="ds-text">{html.escape(debrief.get('micro_tip',''))}</div>
                </div>
                <div class="ds-encourage">{html.escape(debrief.get('encouragement',''))}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Start New Session", type="primary"):
            st.session_state.show_debrief = False
            st.session_state.last_debrief = None
            st.session_state.active_page = "Scenarios"
            st.rerun()
        return

    # Step dots
    dots_html = "".join(
        f'<div class="step-dot {"done" if i < current_step else "active" if i == current_step else "todo"}"></div>'
        for i in range(1, total_steps + 1)
    )
    st.markdown(
        f'<div class="step-indicator">{dots_html}</div>'
        f'<div style="font-size:0.78rem;color:#6b8f8e;margin-bottom:1rem;">Step {current_step} of {total_steps}</div>',
        unsafe_allow_html=True,
    )

    # Goal card
    st.markdown(
        f"""
        <div class="practice-header">
            <div class="ph-label">Session Goal</div>
            <h3>{html.escape(st.session_state.goal_text)}</h3>
            <div class="ph-sub">Stay inside <strong>{html.escape(scenario['title'])}</strong> — one step at a time.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    left, right = st.columns([2, 1])

    with left:
        st.markdown("**Guided Practice**")
        st.caption("Respond as if you are already in this exact social moment.")

        # Render messages
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.write(msg["content"])

        # ── Warmup starters (shown before first message) ──
        if not st.session_state.messages:
            # Fetch starters on first load of this session
            if not st.session_state.warmup_starters:
                with st.spinner("Preparing practice prompts…"):
                    st.session_state.warmup_starters = call_warmup(scenario)

            starters = st.session_state.warmup_starters
            if starters:
                st.markdown(
                    '<div style="font-size:0.82rem;font-weight:600;color:#2d4a4b;margin-bottom:0.4rem;">💬 Tap to begin with a starter:</div>',
                    unsafe_allow_html=True,
                )
                for i, starter in enumerate(starters):
                    if st.button(starter, key=f"starter_{i}"):
                        # Treat click exactly like typing that message
                        st.session_state.messages.append({"role": "user", "content": starter})
                        st.session_state.current_session["user_turns"] += 1
                        with st.spinner(""):
                            st.markdown(
                                '<div class="typing-indicator"><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div></div>',
                                unsafe_allow_html=True,
                            )
                            try:
                                payload = call_backend(starter)
                                reply = payload["response"]
                                blocked = bool(payload.get("blocked", False))
                            except Exception as e:
                                reply = "Could not reach the backend. Please ensure the server is running."
                                blocked = True
                                st.error(str(e))
                            sess = st.session_state.current_session
                            st.session_state.messages.append({"role": "assistant", "content": reply})
                            sess["assistant_turns"] += 1
                            if blocked:
                                sess["blocked_count"] += 1
                        st.rerun()

                st.markdown("<div style='height:0.4rem'></div>", unsafe_allow_html=True)
                st.caption("…or type your own message below.")

        # Chat input
        if prompt := st.chat_input("Describe your next move or social response"):
            st.session_state.messages.append({"role": "user", "content": prompt})
            st.session_state.current_session["user_turns"] += 1

            # ── Typing indicator ──
            typing_placeholder = st.empty()
            typing_placeholder.markdown(
                '<div class="typing-indicator"><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div></div>',
                unsafe_allow_html=True,
            )

            try:
                payload = call_backend(prompt)
                reply = payload["response"]
                intent = payload.get("intent", "general_interaction")
                provider = payload.get("provider", "unknown")
                latency = float(payload.get("latency_ms", 0.0))
                blocked = bool(payload.get("blocked", False))
            except Exception as e:
                reply = "Could not reach the backend. Please ensure the server is running."
                intent = "general_interaction"
                provider = "frontend_error"
                latency = 0.0
                blocked = True
                st.error(str(e))

            typing_placeholder.empty()
            st.session_state.messages.append({"role": "assistant", "content": reply})
            sess = st.session_state.current_session
            sess["assistant_turns"] += 1
            sess["last_intent"] = intent
            sess["last_provider"] = provider
            sess["last_latency_ms"] = latency
            if blocked:
                sess["blocked_count"] += 1
            st.rerun()

    with right:
        # ── Session timer ──
        elapsed_s = int(time.time() - st.session_state.current_session["started_at"])
        elapsed_str = f"{elapsed_s // 60:02d}:{elapsed_s % 60:02d}"
        st.markdown(
            f'<div class="session-timer">⏱ {elapsed_str}</div>',
            unsafe_allow_html=True,
        )

        # Coach panel
        tip = get_contextual_tip(scenario["id"], scenario["skill"])
        st.markdown(
            f"""
            <div class="coach-panel">
                <h4>🧭 Coach Panel</h4>
                <div class="coach-hint">{html.escape(coach_hint_for_skill(scenario["skill"]))}</div>
                <div class="coach-tip">💡 {html.escape(tip)}</div>
                <div class="coach-meta-row">
                    <div class="coach-meta-item">
                        <div class="cm-label">Scenario</div>
                        <div class="cm-value">{html.escape(scenario['title'])}</div>
                    </div>
                    <div class="coach-meta-item">
                        <div class="cm-label">Context</div>
                        <div class="cm-value">{scenario['context']}</div>
                    </div>
                    <div class="coach-meta-item">
                        <div class="cm-label">Focus</div>
                        <div class="cm-value">{html.escape(default_goal_for_skill(scenario['skill']))}</div>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if st.button("🔄 Next tip", key="next_tip", use_container_width=True):
            advance_tip(scenario["id"], scenario["skill"])
            st.rerun()

        st.markdown("<div style='height:0.6rem'></div>", unsafe_allow_html=True)

        if st.button("Reset Current Session", key="reset_session", use_container_width=True):
            reset_current_practice_session()

        # Confidence sliders
        st.caption("📊 Confidence check-in")
        c1, c2 = st.columns(2)
        with c1:
            st.caption("Before")
            st.session_state.confidence_before = st.slider(
                "Before", 1, 5, st.session_state.confidence_before, label_visibility="collapsed"
            )
        with c2:
            st.caption("After")
            st.session_state.confidence_after = st.slider(
                "After", 1, 5, st.session_state.confidence_after, label_visibility="collapsed"
            )

        st.markdown("<div style='height:0.4rem'></div>", unsafe_allow_html=True)
        if st.button("Change Scenario", use_container_width=True):
            st.session_state.active_page = "Scenarios"
            st.rerun()
        if st.button("End Session & Save", type="primary", use_container_width=True):
            messages_snapshot = list(st.session_state.messages)
            complete_session()
            # ── Post-session AI debrief ──
            with st.spinner("Generating your debrief…"):
                debrief_data = call_debrief(messages_snapshot)
            finalize_completed_backend_session()
            if debrief_data:
                st.session_state.last_debrief = debrief_data
                st.session_state.show_debrief = True
            # ── Confidence celebration ──
            if st.session_state.confidence_after > st.session_state.confidence_before:
                st.session_state.active_page = "Practice"   # stay to show celebration + debrief
            else:
                st.session_state.active_page = "Practice"
            st.rerun()


def scenarios_page() -> None:
    st.markdown('<div class="page-title">Scenario Library</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="page-caption">Choose a practice context that matches the skill you want to build.</div>',
        unsafe_allow_html=True,
    )

    # Extra CSS: ghost Streamlit button inside each card + card-level hover CTA
    st.markdown(
        """
        <style>
        /* Hide the real Streamlit button — only the in-card HTML button is visible */
        .scenario-btn-wrap > div { margin: 0 !important; padding: 0 !important; }
        .scenario-btn-wrap button {
            position: absolute !important;
            width: 1px !important; height: 1px !important;
            opacity: 0 !important; pointer-events: none !important;
            padding: 0 !important; border: none !important;
        }
        /* In-card start button */
        .card-start-btn {
            display: inline-flex;
            align-items: center;
            gap: 0.4rem;
            margin-top: 0.75rem;
            padding: 0.42rem 1rem;
            background: linear-gradient(135deg, #2d6a4f, #1a3a3c);
            color: #ffffff !important;
            font-size: 0.82rem;
            font-weight: 600;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            transition: opacity 0.18s;
            text-decoration: none;
        }
        .card-start-btn:hover { opacity: 0.82; }
        .card-start-btn.locked-btn {
            background: #e8eeec;
            color: #9ab0ae !important;
            cursor: not-allowed;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    intermediate_done = intermediate_sessions_count()
    unlock_needed = 2

    if intermediate_done < unlock_needed:
        st.info(
            f"\U0001f512 Complete **{unlock_needed - intermediate_done}** more Intermediate session(s) "
            f"to unlock Advanced scenarios.",
            icon=None,
        )

    c1, c2, c3, c4 = st.columns(4)
    contexts     = ["All"] + sorted({s["context"] for s in SCENARIOS})
    difficulties = ["All"] + sorted({s["difficulty"] for s in SCENARIOS})
    skills       = ["All"] + sorted({SKILL_LABELS[s["skill"]] for s in SCENARIOS})

    ctx    = c1.selectbox("Context", contexts)
    diff   = c2.selectbox("Difficulty", difficulties)
    sk     = c3.selectbox("Skill", skills)
    search = c4.text_input("Search", placeholder="Keyword\u2026")

    filtered = [
        s for s in SCENARIOS
        if (ctx  == "All" or s["context"] == ctx)
        and (diff == "All" or s["difficulty"] == diff)
        and (sk   == "All" or SKILL_LABELS[s["skill"]] == sk)
        and (not search or search.lower() in (s["title"] + s["description"]).lower())
    ]

    rec = recommended_scenario()
    st.markdown(
        f'<div style="background:#e8f4f3;border-radius:10px;padding:0.55rem 1rem;'
        f'font-size:0.86rem;color:#1a3a3c;margin-bottom:1rem;">'
        f'\u2b50 <strong>Recommended for you:</strong> {rec["title"]}</div>',
        unsafe_allow_html=True,
    )

    # Render two columns; each card contains its own styled HTML start-button.
    # A real (invisible) Streamlit button sits right below each card and is
    # triggered programmatically via JS so Streamlit routing still works.
    col_left, col_right = st.columns(2)
    col_map = {0: col_left, 1: col_right}

    for idx, s in enumerate(filtered):
        diff_class  = "tag-diff-" + s["difficulty"].lower()
        is_rec      = s["id"] == rec["id"]
        unlocked    = is_scenario_unlocked(s)
        skill_label = SKILL_LABELS[s["skill"]]
        btn_key     = "start_" + s["id"]

        badge = (
            '<span class="recommended-badge">Recommended</span>' if is_rec else ""
        )
        lock_badge = (
            ""
            if unlocked
            else (
                '<span class="lock-badge">\U0001f512 '
                + str(s["unlock_after"])
                + " Intermediate sessions</span>"
            )
        )
        locked_cls = " locked" if not unlocked else ""

        # The in-card button uses JS to click the hidden Streamlit button
        if unlocked:
            cta = (
                '<button class="card-start-btn" '
                'onclick="'
                "var btns=window.parent.document.querySelectorAll('button[data-testid=stBaseButton-secondary]');"
                "for(var i=0;i<btns.length;i++){"
                "  if(btns[i].innerText.trim()==='" + btn_key + "'){"
                "    btns[i].click(); break;"
                "  }"
                "}"
                '">'
                "\u25b6\ufe0e Start"
                "</button>"
            )
        else:
            cta = '<span class="card-start-btn locked-btn">\U0001f512 Locked</span>'

        card_html = (
            '<div class="scenario-card' + locked_cls + '">'
            + badge + lock_badge
            + '<div class="s-icon">'  + s["icon"]        + "</div>"
            + '<div class="s-title">' + s["title"]       + "</div>"
            + '<div class="s-desc">'  + s["description"] + "</div>"
            + '<div style="margin-top:0.4rem;">'
            + '<span class="tag ' + diff_class + '">' + s["difficulty"] + "</span>"
            + '<span class="tag tag-skill">'          + skill_label     + "</span>"
            + '<span class="tag tag-ctx">'            + s["context"]    + "</span>"
            + "</div>"
            + cta
            + "</div>"
        )

        with col_map[idx % 2]:
            st.markdown(card_html, unsafe_allow_html=True)
            # Real Streamlit button — invisible, label used as JS lookup key
            with st.container():
                st.markdown('<div class="scenario-btn-wrap">', unsafe_allow_html=True)
                if unlocked:
                    if st.button(btn_key, key=btn_key):
                        start_scenario(s["id"])
                else:
                    st.button("\U0001f512 Locked", key="locked_" + s["id"], disabled=True)
                st.markdown("</div>", unsafe_allow_html=True)


def insights_page() -> None:
    st.markdown('<div class="page-title">Insights</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-caption">How your practice habits and skills are evolving over time.</div>', unsafe_allow_html=True)

    hist = st.session_state.session_history
    total = len(hist)

    if total == 0:
        render_empty_state(
            EMPTY_INSIGHTS_SVG,
            "No data yet",
            "Complete your first practice session to see your confidence trend, skill progress, and weekly stats.",
        )
        if st.button("▶  Start Your First Session", type="primary"):
            start_scenario(SCENARIOS[0]["id"])
        return

    streak = current_streak()
    avg_conf = average_confidence()
    weekly = weekly_sessions_count()
    goal = st.session_state.weekly_goal
    week_pct = round((weekly / goal) * 100) if goal else 0
    best = strongest_skill_label()
    focus = weakest_skill_label()

    st.markdown(
        f"""
        <div class="insights-kpi-grid">
            <div class="kpi-card">
                <div class="kpi-icon">📚</div>
                <div class="kpi-val">{total}</div>
                <div class="kpi-label">Total Sessions</div>
                <div class="kpi-delta {'up' if total else 'neutral'}">{'↑ Keep going!' if total else 'No sessions yet'}</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-icon">🔥</div>
                <div class="kpi-val">{streak}</div>
                <div class="kpi-label">Day Streak</div>
                <div class="kpi-delta {'up' if streak >= 2 else 'neutral'}">{'↑ On a roll' if streak >= 2 else 'Build momentum'}</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-icon">💪</div>
                <div class="kpi-val">{avg_conf}</div>
                <div class="kpi-label">Avg Confidence</div>
                <div class="kpi-delta {'up' if avg_conf >= 4 else 'neutral'}">{'↑ High confidence' if avg_conf >= 4 else 'out of 5'}</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-icon">🎯</div>
                <div class="kpi-val">{weekly}/{goal}</div>
                <div class="kpi-label">Weekly Goal</div>
                <div class="kpi-delta {'up' if week_pct >= 100 else 'neutral'}">{'↑ Goal met!' if week_pct >= 100 else f'{week_pct}% complete'}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
        <div class="insight-callout">
            <div class="ic-label">🧠 AI Coach Insight</div>
            <div class="ic-text">Your strongest skill is <strong>{best}</strong>. To accelerate growth, focus next on <strong>{focus}</strong> — it has the most room to improve.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown('<div class="section-header"><h3>Confidence Over Time</h3><span class="sh-sub">Last 10 sessions</span></div>', unsafe_allow_html=True)
        import pandas as pd
        data = [s["confidence_after"] for s in hist[-10:]]
        df = pd.DataFrame({"Session": range(1, len(data)+1), "Confidence": data}).set_index("Session")
        st.line_chart(df, color="#2d6a4f", height=200)

    with col_b:
        st.markdown('<div class="section-header"><h3>Skill Breakdown</h3></div>', unsafe_allow_html=True)
        import pandas as pd
        scores = st.session_state.skill_scores
        if any(v > 0 for v in scores.values()):
            df_s = pd.DataFrame({"Skill": [SKILL_LABELS[k] for k in scores], "Score": list(scores.values())}).set_index("Skill")
            st.bar_chart(df_s, color="#52b788", height=200)

    st.markdown('<div class="section-header"><h3>Skill Progress</h3></div>', unsafe_allow_html=True)
    col_sk, col_pat = st.columns([3, 2])
    with col_sk:
        render_skill_bars(st.session_state.skill_scores)
    with col_pat:
        st.markdown(
            f"""
            <div class="coach-panel" style="margin-top:0;">
                <h4>📊 Patterns</h4>
                <div class="coach-meta-row">
                    <div class="coach-meta-item"><div class="cm-label">Strongest</div><div class="cm-value">⭐ {best}</div></div>
                    <div class="coach-meta-item"><div class="cm-label">Focus Next</div><div class="cm-value">🎯 {focus}</div></div>
                    <div class="coach-meta-item"><div class="cm-label">Avg Confidence</div><div class="cm-value">{avg_conf} / 5</div></div>
                    <div class="coach-meta-item"><div class="cm-label">This Week</div><div class="cm-value">{weekly} of {goal}</div></div>
                    <div class="coach-meta-item"><div class="cm-label">Coach Style</div><div class="cm-value">{st.session_state.coach_style}</div></div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    if total > 0:
        st.markdown('<div class="section-header"><h3>Difficulty Distribution</h3></div>', unsafe_allow_html=True)
        import pandas as pd
        diff_counts: Dict[str, int] = {}
        for s in hist:
            d = s.get("difficulty", "Unknown")
            diff_counts[d] = diff_counts.get(d, 0) + 1
        df_d = pd.DataFrame({"Difficulty": list(diff_counts.keys()), "Sessions": list(diff_counts.values())}).set_index("Difficulty")
        st.bar_chart(df_d, color="#95d5b2", height=160)

    st.markdown('<div class="section-header"><h3>Practice Heatmap</h3><span class="sh-sub">Last 12 weeks</span></div>', unsafe_allow_html=True)
    render_heatmap_html()


def history_page() -> None:
    st.markdown('<div class="page-title">Session History</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-caption">A record of every practice session you\'ve completed.</div>', unsafe_allow_html=True)

    hist = st.session_state.session_history
    if not hist:
        render_empty_state(
            EMPTY_HISTORY_SVG,
            "No sessions yet",
            "Your completed sessions will appear here. Start a practice to build your history.",
        )
        if st.button("▶  Start Your First Session", type="primary"):
            start_scenario(SCENARIOS[0]["id"])
        return

    for idx, s in enumerate(reversed(hist)):
        dt = datetime.fromisoformat(s["completed_at"])
        date_str = dt.strftime("%b %d, %Y · %H:%M")
        conf_before = s["confidence_before"]
        conf_after  = s["confidence_after"]
        delta = conf_after - conf_before
        delta_str = f"+{delta}" if delta > 0 else str(delta)
        delta_color = "#2d6a4f" if delta >= 0 else "#e63946"
        diff_class = f"tag-diff-{s['difficulty'].lower()}"

        st.markdown(
            f"""
            <div class="history-card">
                <div class="hc-top">
                    <div>
                        <div class="hc-title">{s['scenario_title']}</div>
                        <div class="hc-date">{date_str}</div>
                    </div>
                    <div style="text-align:right;">
                        <div class="conf-arrow">
                            <span>{conf_before}</span> → <span>{conf_after}</span>
                            <span style="color:{delta_color};font-size:0.8rem;margin-left:2px;">({delta_str})</span>
                        </div>
                        <div style="font-size:0.72rem;color:#6b8f8e;margin-top:2px;">Confidence</div>
                    </div>
                </div>
                <div>
                    <span class="tag {diff_class}">{s['difficulty']}</span>
                    <span class="tag tag-skill">{s['skill']}</span>
                </div>
                <div style="font-size:0.85rem;color:#4c6b6a;margin-top:0.6rem;">{s['summary']}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # ── Session replay ──
        transcript = s.get("transcript", [])
        col_replay, col_redo = st.columns([1, 1])
        with col_replay:
            if transcript:
                with st.expander("📖 View transcript"):
                    for msg in transcript:
                        role_class = "transcript-user" if msg["role"] == "user" else "transcript-coach"
                        label = "You" if msg["role"] == "user" else "Coach"
                        st.markdown(
                            f'<div class="transcript-msg {role_class}"><strong>{label}:</strong> {html.escape(msg["content"])}</div>',
                            unsafe_allow_html=True,
                        )
            else:
                st.caption("No transcript saved for this session.")
        with col_redo:
            if st.button("↩ Practice Again", key=f"redo_{idx}"):
                scenario = next((sc for sc in SCENARIOS if sc["title"] == s["scenario_title"]), SCENARIOS[0])
                start_scenario(scenario["id"])


def profile_page() -> None:
    st.markdown('<div class="page-title">Profile & Preferences</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-caption">Personalise your coaching workspace.</div>', unsafe_allow_html=True)

    col1, col2 = st.columns(2)

    with col1:
        st.markdown('<div class="profile-section"><h4>🎓 Coaching Settings</h4>', unsafe_allow_html=True)

        # ── Coach style with preview ──
        style_options = ["Supportive", "Calm", "Direct"]
        st.session_state.coach_style = st.selectbox(
            "Coach style",
            style_options,
            index=style_options.index(st.session_state.coach_style),
        )
        preview = COACH_STYLE_PREVIEWS.get(st.session_state.coach_style, "")
        st.markdown(f'<div class="style-preview">{html.escape(preview)}</div>', unsafe_allow_html=True)

        st.session_state.difficulty_pref = st.selectbox(
            "Difficulty preference",
            ["Balanced", "Comfort zone", "Stretch mode"],
            index=["Balanced", "Comfort zone", "Stretch mode"].index(st.session_state.difficulty_pref),
        )
        st.session_state.weekly_goal = st.slider("Weekly session goal", 1, 10, st.session_state.weekly_goal)
        st.markdown("</div>", unsafe_allow_html=True)

    with col2:
        st.markdown('<div class="profile-section"><h4>🛡️ Streak & Progress</h4>', unsafe_allow_html=True)

        freeze_on = st.session_state.streak_freeze_enabled
        freeze_label = "Streak Freeze: ON" if freeze_on else "Streak Freeze: OFF"
        st.markdown(
            f'<div class="streak-freeze-badge">🛡️ {freeze_label}</div>',
            unsafe_allow_html=True,
        )
        st.markdown("<div style='height:0.4rem'></div>", unsafe_allow_html=True)
        st.session_state.streak_freeze_enabled = st.toggle(
            "Enable streak freeze (one protected off-day per week)",
            value=st.session_state.streak_freeze_enabled,
        )
        st.caption(
            "When enabled, missing one day won't break your streak — "
            "as long as you practiced the day before."
        )

        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="profile-section"><h4>🎨 Theme & Display</h4>', unsafe_allow_html=True)
        st.session_state.theme_pref = st.selectbox(
            "Theme", ["Calm", "Warm", "Focus"],
            index=["Calm", "Warm", "Focus"].index(st.session_state.theme_pref),
        )
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="profile-section"><h4>🔒 Data & Privacy</h4>', unsafe_allow_html=True)
        st.checkbox("Enable tracing in backend", value=True, disabled=True)
        st.checkbox("Keep summaries locally", value=True, disabled=True)
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div style='height:0.4rem'></div>", unsafe_allow_html=True)
    if st.button("⚠ Reset Local Progress"):
        for key in ["messages", "session_history", "recent_wins", "skill_scores", "last_debrief", "warmup_starters"]:
            if key in st.session_state:
                del st.session_state[key]
        init_state()
        st.success("Progress reset successfully.")
        st.rerun()


# ---------------------------------------------------------------------------
# Session complete
# ---------------------------------------------------------------------------

def complete_session() -> None:
    if not st.session_state.messages:
        st.info("No messages to save.")
        return

    scenario = get_selected_scenario()
    dur = max(1, int((time.time() - st.session_state.current_session["started_at"]) / 60))
    skill = scenario["skill"]
    improvement = max(1, st.session_state.confidence_after - st.session_state.confidence_before + 1)
    st.session_state.skill_scores[skill] += improvement

    blocked = st.session_state.current_session["blocked_count"]
    win = f"Completed '{scenario['title']}'" + (" cleanly." if blocked == 0 else f" despite {blocked} blocked moment(s).")
    st.session_state.recent_wins.insert(0, win)
    st.session_state.recent_wins = st.session_state.recent_wins[:6]

    session = {
        "scenario_title": scenario["title"],
        "skill": SKILL_LABELS[skill],
        "difficulty": scenario["difficulty"],
        "completed_at": datetime.now().isoformat(timespec="seconds"),
        "duration_minutes": dur,
        "confidence_before": st.session_state.confidence_before,
        "confidence_after": st.session_state.confidence_after,
        "intent": st.session_state.current_session["last_intent"],
        "provider": st.session_state.current_session["last_provider"],
        "latency_ms": st.session_state.current_session["last_latency_ms"],
        "summary": (
            f"In {scenario['title'].lower()}, you practised {SKILL_LABELS[skill].lower()}. "
            + ("You stayed focused throughout." if blocked == 0 else "You recovered from off-track moments.")
        ),
        # ── Save full transcript for replay ──
        "transcript": list(st.session_state.messages),
    }
    st.session_state.session_history.insert(0, session)

    # Reset session state (keep messages for debrief call, cleared after)
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
    st.session_state.warmup_starters = []


def finalize_completed_backend_session() -> None:
    """Clear persisted backend memory after a session has been saved/debriefed."""
    call_reset_session()
    st.session_state.backend_session_id = f"session-{uuid4().hex}"


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

def render_sidebar() -> None:
    with st.sidebar:
        st.markdown(
            '<div style="font-family:\'DM Serif Display\',serif;font-size:1.3rem;color:#d4e9e2;padding:0.5rem 0 0.2rem;">🌿 Social Guide</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div style="font-size:0.78rem;color:rgba(255,255,255,0.45);margin-bottom:1rem;">Structured coaching workspace</div>',
            unsafe_allow_html=True,
        )

        selected_page = st.radio(
            "Navigation", NAV_ITEMS,
            index=NAV_ITEMS.index(st.session_state.active_page),
            label_visibility="collapsed",
        )
        if selected_page != st.session_state.active_page:
            st.session_state.active_page = selected_page
            st.rerun()

        st.markdown("---")

        scenario = get_selected_scenario()
        st.markdown(
            '<div style="font-size:0.7rem;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;color:rgba(255,255,255,0.4);margin-bottom:0.6rem;">Coach Snapshot</div>',
            unsafe_allow_html=True,
        )
        rows = [
            ("Style", st.session_state.coach_style),
            ("Scenario", scenario["title"]),
            ("Streak", f"{current_streak()} day(s)" + (" 🛡️" if st.session_state.streak_freeze_enabled else "")),
            ("This week", f"{weekly_sessions_count()} / {st.session_state.weekly_goal}"),
        ]
        rows_html = "".join(
            f'<div class="snapshot-row"><span class="snapshot-key">{k}</span><span class="snapshot-val">{v}</span></div>'
            for k, v in rows
        )
        st.markdown(
            f'<div style="background:rgba(255,255,255,0.04);border-radius:12px;padding:0.6rem 0.8rem;">{rows_html}</div>',
            unsafe_allow_html=True,
        )

        st.markdown(
            '<div style="font-size:0.7rem;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;color:rgba(255,255,255,0.4);margin:1rem 0 0.5rem;">Skills</div>',
            unsafe_allow_html=True,
        )
        for skill, score in st.session_state.skill_scores.items():
            pct = min(100, score * 10)
            st.markdown(
                f"""
                <div style="margin-bottom:6px;">
                    <div style="display:flex;justify-content:space-between;font-size:0.72rem;color:rgba(255,255,255,0.55);margin-bottom:2px;">
                        <span>{SKILL_LABELS[skill]}</span><span>{score}</span>
                    </div>
                    <div style="height:4px;background:rgba(255,255,255,0.1);border-radius:999px;">
                        <div style="height:100%;width:{pct}%;background:#52b788;border-radius:999px;"></div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # ── Confidence celebration (in sidebar so it's always visible) ──
        if (
            st.session_state.session_history
            and not st.session_state.get("show_debrief")
        ):
            last = st.session_state.session_history[0]
            if last.get("confidence_after", 0) > last.get("confidence_before", 0):
                delta = last["confidence_after"] - last["confidence_before"]
                st.markdown(
                    f"""
                    <div class="celebrate-banner" style="margin-top:1rem;">
                        <span style="font-size:1.4rem;">🌱</span>
                        <div class="cb-text">You grew today! Confidence +{delta}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    st.set_page_config(
        page_title="Social Interaction Support Guide",
        page_icon="🌿",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    inject_styles()
    init_state()

    page_map = {
        "Home":      home_page,
        "Practice":  practice_page,
        "Scenarios": scenarios_page,
        "Insights":  insights_page,
        "History":   history_page,
        "Profile":   profile_page,
    }

    render_sidebar()
    page_map[st.session_state.active_page]()


if __name__ == "__main__":
    main()
