# router.py (with Langfuse monitoring enhancements)

from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from .intent import classify_intent
from .memory import SessionMemoryStore, SlidingWindowMemory
from .model import ModelClient, ModelResult
from .retrieval import FaissKnowledgeBase, format_retrieved_context
from .rules import RuleResult, apply_rules, response_is_valid
from .tracing import langfuse, observe, propagate_attributes, start_as_current_span, get_current_trace_id

logger = logging.getLogger(__name__)
router = APIRouter()
memory_store = SessionMemoryStore(max_items=5)
model_client = ModelClient()
knowledge_base = FaissKnowledgeBase()
RETRIEVAL_ENABLED = knowledge_base.startup_check()

if RETRIEVAL_ENABLED:
    logger.info("FAISS retrieval enabled for this server run.")
else:
    logger.info("FAISS retrieval disabled for this server run: %s", knowledge_base.disabled_reason)


# ============================================================================
# Pydantic models
# ============================================================================

class ChatRequest(BaseModel):
    user_input: str = Field(..., description="The user's message")
    user_id: Optional[str] = Field(default=None, description="Unique user identifier")
    session_id: Optional[str] = Field(default=None, description="Session identifier")
    selected_scenario: Optional[str] = Field(default=None, description="Selected practice scenario")
    goal_text: Optional[str] = Field(default=None, description="User's specific goal for the session")
    coach_style: Optional[str] = Field(default="supportive", description="Coaching style preference")


class ChatResponse(BaseModel):
    response: str = Field(..., description="Coach response text")
    intent: str = Field(..., description="Detected intent")
    memory: List[Dict[str, str]] = Field(default_factory=list, description="Conversation history")
    latency_ms: float = Field(default=0.0, description="Generation latency in milliseconds")
    token_usage: Dict[str, int] = Field(default_factory=dict, description="Token usage stats")
    provider: str = Field(default="unknown", description="LLM provider used")
    blocked: bool = Field(default=False, description="Whether response was blocked by rules")
    rule_reason: Optional[str] = Field(default=None, description="Reason for blocking if blocked")
    trace_id: Optional[str] = Field(default=None, description="Langfuse trace ID for monitoring")


class DebriefRequest(BaseModel):
    scenario_title: str = Field(..., description="Title of the practiced scenario")
    scenario_skill: str = Field(..., description="Skill tag for the scenario")
    confidence_before: int = Field(default=5, ge=1, le=10, description="Confidence before session")
    confidence_after: int = Field(default=5, ge=1, le=10, description="Confidence after session")
    messages: List[Dict[str, str]] = Field(default_factory=list, description="Conversation messages")
    user_id: Optional[str] = Field(default=None)
    session_id: Optional[str] = Field(default=None)


class DebriefResponse(BaseModel):
    went_well: str = Field(..., description="What went well")
    improve: str = Field(..., description="What to improve")
    micro_tip: str = Field(..., description="One actionable micro-tip")
    encouragement: str = Field(..., description="Encouraging closing message")
    provider: str = Field(default="unknown")
    latency_ms: float = Field(default=0.0)
    trace_id: Optional[str] = Field(default=None, description="Langfuse trace ID for monitoring")


class WarmupRequest(BaseModel):
    scenario_id: str = Field(..., description="Scenario identifier")
    scenario_skill: str = Field(..., description="Skill category")
    coach_style: Optional[str] = Field(default="supportive")
    user_id: Optional[str] = Field(default=None)
    session_id: Optional[str] = Field(default=None)


class WarmupResponse(BaseModel):
    starters: List[str] = Field(..., description="Three conversation starters")
    provider: str = Field(default="unknown")
    latency_ms: float = Field(default=0.0)
    trace_id: Optional[str] = Field(default=None, description="Langfuse trace ID for monitoring")


# ============================================================================
# NEW: Feedback & Scoring models
# ============================================================================

class FeedbackRequest(BaseModel):
    trace_id: str = Field(..., description="Langfuse trace ID from the response")
    score: float = Field(..., ge=0.0, le=1.0, description="User rating (0.0 = bad, 1.0 = great)")
    comment: Optional[str] = Field(default=None, description="Optional user comment")


class FeedbackResponse(BaseModel):
    status: str = Field(default="ok")
    trace_id: str
    score: float


class SessionResetRequest(BaseModel):
    user_id: Optional[str] = Field(default=None, description="Unique user identifier")
    session_id: Optional[str] = Field(default=None, description="Session identifier")


class SessionResetResponse(BaseModel):
    status: str = Field(default="ok")
    user_id: str
    session_id: str


# ============================================================================
# Pipeline helpers
# ============================================================================

def _format_history_as_dialogue(memory: SlidingWindowMemory) -> tuple[str, int]:
    """Format memory history as dialogue text and return turn count."""
    history = memory.history()
    lines = []
    for turn in history:
        user_msg = turn.get("user") or turn.get("user_input", "")
        coach_msg = turn.get("assistant") or turn.get("response", "")
        if user_msg:
            lines.append(f"User: {user_msg}")
        if coach_msg:
            lines.append(f"Coach: {coach_msg}")
    return "\n".join(lines), len(history)


def _phase_instruction(turn_count: int, selected_scenario: str | None, goal_text: str | None) -> str:
    """Generate phase-specific instruction based on turn count."""
    if turn_count == 0:
        return (
            "This is the FIRST turn. Open the scenario naturally. "
            "Set context briefly and ask an open question to start the practice."
        )
    elif turn_count < 3:
        return (
            "Early session: guide the user through the scenario. "
            "Give gentle nudges, ask follow-up questions, keep momentum."
        )
    else:
        return (
            "Mid-to-late session: help the user reflect and refine. "
            "Offer specific feedback and encourage natural flow."
        )


def _safe_fallback_response(rule_result: RuleResult, user_input: str, goal_text: str | None) -> str:
    """Return a safe fallback when the model fails or validation fails."""
    if goal_text:
        return f"Let's keep working on that. {goal_text} What would you like to try next?"
    if rule_result and rule_result.guidance:
        return f"{rule_result.guidance} How does that feel as a next step?"
    return "I'm here to help. What would you like to practise next?"


def _repair_prompt(original_prompt: str, bad_response: str, rule_result: RuleResult) -> str:
    """Build a repair prompt when the initial response fails validation."""
    return f"""{original_prompt}

---

IMPORTANT: Your previous response was invalid because it broke one of the core rules.
Previous (invalid) response: "{bad_response[:300]}"

Please rewrite your response, ensuring you:
- Do NOT repeat anything from the conversation history above
- Stay fully in the scenario
- Keep it to 2-3 short sentences
- Move the conversation forward
""".strip()


def _build_debrief_prompt(request: DebriefRequest) -> str:
    """Build the prompt for the debrief endpoint."""
    messages_text = "\n".join(
        f"{msg.get('role', 'user').capitalize()}: {msg.get('content', '')}"
        for msg in request.messages[-20:]
    )
    return f"""You are a social-skills coach reviewing a practice session.

Scenario: {request.scenario_title}
Skill: {request.scenario_skill}
Confidence before: {request.confidence_before}/10
Confidence after: {request.confidence_after}/10

Conversation transcript:
{messages_text}

Provide a brief debrief in EXACTLY this format:

WENT_WELL: <one sentence>
IMPROVE: <one sentence>
MICRO_TIP: <one actionable tip>
ENCOURAGEMENT: <one encouraging closing sentence>

Keep each section to one concise sentence.""".strip()


def _parse_debrief(text: str, request: DebriefRequest) -> DebriefResponse:
    """Parse debrief text into structured response."""
    defaults = {
        "went_well": "You engaged with the scenario — that's progress.",
        "improve": f"Keep practising {request.scenario_skill.replace('_', ' ')} to build fluency.",
        "micro_tip": "Take a breath before responding; it gives you time to think.",
        "encouragement": "Every session makes you stronger. Keep going!",
    }

    patterns = {
        "went_well": re.compile(r"WENT_WELL:\s*(.+)", re.IGNORECASE),
        "improve": re.compile(r"IMPROVE:\s*(.+)", re.IGNORECASE),
        "micro_tip": re.compile(r"MICRO_TIP:\s*(.+)", re.IGNORECASE),
        "encouragement": re.compile(r"ENCOURAGEMENT:\s*(.+)", re.IGNORECASE),
    }

    for key, pattern in patterns.items():
        match = pattern.search(text)
        if match:
            defaults[key] = match.group(1).strip()

    return DebriefResponse(
        went_well=defaults["went_well"],
        improve=defaults["improve"],
        micro_tip=defaults["micro_tip"],
        encouragement=defaults["encouragement"],
        provider="unknown",
        latency_ms=0.0,
    )


def _build_warmup_prompt(request: WarmupRequest) -> str:
    """Build the prompt for the warmup endpoint."""
    return f"""You are a social-skills coach preparing a user for a practice scenario.

Scenario: {request.scenario_id}
Skill focus: {request.scenario_skill}
Style: {request.coach_style or "supportive"}

Generate exactly 3 natural conversation starters the user could say in this scenario.
Format as a plain list, one per line, no numbering, no bullets, no extra commentary.

Starters:""".strip()


def _parse_warmup(text: str) -> List[str]:
    """Parse warmup text into list of starters."""
    lines = [line.strip() for line in text.strip().split("\n") if line.strip()]
    cleaned = []
    for line in lines:
        line = re.sub(r"^(\d+[.):-]\s*|[•\-*]\s+)", "", line)
        if line:
            cleaned.append(line)
    return cleaned


# ============================================================================
# Scoring helpers
# ============================================================================

def _score_response_quality(response_text: str, rule_result: RuleResult) -> None:
    """Attach automated quality scores to the current observation."""
    word_count = len(response_text.split())
    sentence_count = len([s for s in response_text.split(".") if s.strip()])

    # Conciseness score: ideal is 2-3 sentences, ~20-40 words
    if 15 <= word_count <= 50 and 1 <= sentence_count <= 4:
        conciseness = 1.0
    elif 50 < word_count <= 80:
        conciseness = 0.5
    else:
        conciseness = 0.0

    # Rule compliance score
    compliance = 0.0 if rule_result.blocked else 1.0

    try:
        langfuse.score(
            name="response_conciseness",
            value=conciseness,
            data_type="BOOLEAN",
            comment=f"Words: {word_count}, Sentences: {sentence_count}",
        )
    except Exception:
        pass

    try:
        langfuse.score(
            name="rule_compliance",
            value=compliance,
            data_type="BOOLEAN",
            comment="Passed rule validation" if compliance else f"Blocked: {rule_result.reason}",
        )
    except Exception:
        pass


def _score_repair_attempted(repair_attempted: bool, repair_succeeded: bool | None) -> None:
    """Score whether response repair was needed and if it succeeded."""
    if not repair_attempted:
        return
    try:
        langfuse.score(
            name="repair_needed",
            value=1.0,
            data_type="BOOLEAN",
            comment="Repair succeeded" if repair_succeeded else "Repair failed, fallback used",
        )
    except Exception:
        pass


def _score_debrief(request: DebriefRequest) -> None:
    """Score confidence improvement from the debrief."""
    delta = request.confidence_after - request.confidence_before
    try:
        langfuse.score(
            name="confidence_delta",
            value=float(delta),
            data_type="NUMERIC",
            comment=f"Before: {request.confidence_before}, After: {request.confidence_after}",
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Traced pipeline helpers
# ---------------------------------------------------------------------------

@observe(name="classify-intent")
def traced_classify_intent(user_input: str) -> str:
    result = classify_intent(user_input)
    langfuse.update_current_span(
        input={"user_input": user_input},
        output={"intent": result},
        metadata={"component": "intent_classifier"},
    )
    return result


@observe(name="apply-rules")
def traced_apply_rules(
    user_input: str,
    intent: str,
    selected_scenario: str | None = None,
    session_started: bool = False,
) -> RuleResult:
    result = apply_rules(
        user_input,
        intent,
        preferred_scenario=selected_scenario,
        session_started=session_started,
    )
    langfuse.update_current_span(
        input={
            "user_input": user_input,
            "intent": intent,
            "selected_scenario": selected_scenario,
            "session_started": session_started,
        },
        output={
            "scenario": result.scenario,
            "blocked": result.blocked,
            "reason": result.reason,
            "guidance": result.guidance,
        },
        metadata={"component": "rule_engine"},
    )
    return result


@observe(name="build-prompt")
def build_prompt(
    user_input: str,
    memory: SlidingWindowMemory,
    rule_result: RuleResult,
    selected_scenario: str | None = None,
    goal_text: str | None = None,
    coach_style: str | None = None,
) -> str:
    history_text, turn_count = _format_history_as_dialogue(memory)
    phase = _phase_instruction(turn_count, selected_scenario, goal_text)

    retrieved_context = "Retrieval unavailable for this server run."
    if RETRIEVAL_ENABLED:
        retrieved = knowledge_base.retrieve(
            query=user_input,
            scenario=rule_result.scenario,
            intent=getattr(rule_result, "intent", None),
        )
        retrieved_context = format_retrieved_context(retrieved)

    prompt = f"""
You are a social interaction coach running a live practice session with a user.

CORE RULES — follow these on every single turn:
- Never repeat a question or coaching point you have already made this session.
- Never re-introduce the scenario or re-establish context that was already set.
- Each response must move the conversation FORWARD from where it currently is.
- Keep the whole response to 2-3 short sentences maximum.
- No lists, no headings, no meta-commentary like "Great job!" at the start of every message.
- Stay fully inside the social interaction scenario — do not break character unnecessarily.

Coach style: {coach_style or "Supportive"}
Scenario: {selected_scenario or rule_result.scenario or "general social interaction"}
Session goal: {goal_text or rule_result.guidance or "practise natural social interaction"}

--- CONVERSATION SO FAR ---
{history_text}
--- END OF HISTORY ---

CURRENT TURN INSTRUCTION ({turn_count} prior turn(s) completed):
{phase}

Relevant coaching context:
{retrieved_context}

Detected intent: {getattr(rule_result, "intent", "unknown")}
Rule guidance: {rule_result.guidance}

User's latest message:
{user_input}

Write only your next coach response. Do not repeat anything from the history above.
""".strip()

    langfuse.update_current_span(
        input={"user_input": user_input, "turn_count": turn_count},
        output={"prompt_length": len(prompt)},
        metadata={
            "component": "prompt_builder",
            "turn_count": str(turn_count),
            "retrieval_enabled": str(RETRIEVAL_ENABLED),
            "phase": phase[:60],
        },
    )
    return prompt


@observe(name="llm-generation")
def call_model(prompt: str, max_tokens: int = 120) -> ModelResult:
    langfuse.update_current_span(
        input=[{"role": "user", "content": prompt}],
        metadata={"max_tokens": str(max_tokens)},
    )

    result = model_client.generate(
        prompt=prompt,
        temperature=0.6,
        top_p=0.9,
        max_tokens=max_tokens,
    )

    langfuse.update_current_span(
        output=result.text,
        metadata={
            "provider": result.provider,
            "latency_ms": str(result.latency_ms),
            "usage_input": str(result.token_usage.get("prompt_tokens", 0)),
            "usage_output": str(result.token_usage.get("completion_tokens", 0)),
            "usage_total": str(result.token_usage.get("total_tokens", 0)),
        },
    )
    return result


@observe(name="update-memory")
def update_memory(memory: SlidingWindowMemory, user_input: str, response: str) -> None:
    memory.add(user_input=user_input, response=response)
    langfuse.update_current_span(
        input={"user_input": user_input},
        output={"stored": True, "memory_size": len(memory.history())},
        metadata={"component": "sliding_window_memory"},
    )


# ---------------------------------------------------------------------------
# Main chat pipeline
# ---------------------------------------------------------------------------

@router.post("/chat", response_model=ChatResponse)
@observe(name="chat-pipeline")
def run_pipeline(request: ChatRequest) -> ChatResponse:
    """Root trace for a single /chat request."""
    user_input = request.user_input
    session_memory = memory_store.get_memory(user_id=request.user_id, session_id=request.session_id)

    with propagate_attributes(
        trace_name="chat-pipeline",
        user_id=request.user_id or "anonymous",
        session_id=request.session_id or "default",
        tags=[
            "chat",
            f"scenario:{request.selected_scenario or 'unknown'}",
            f"style:{request.coach_style or 'default'}",
        ],
        metadata={
            "selected_scenario": str(request.selected_scenario or ""),
            "goal_text": str(request.goal_text or ""),
            "coach_style": str(request.coach_style or ""),
        },
    ):
        langfuse.update_current_span(
            input={"user_input": user_input, "scenario": request.selected_scenario}
        )

        session_started = len(session_memory.history()) > 0
        intent = traced_classify_intent(user_input)
        rule_result = traced_apply_rules(
            user_input,
            intent,
            request.selected_scenario,
            session_started=session_started,
        )

        if rule_result.blocked and rule_result.response:
            response_text = rule_result.response
            update_memory(session_memory, user_input, response_text)
            _score_response_quality(response_text, rule_result)
            langfuse.update_current_span(
                output={"response": response_text, "blocked": True}
            )
            logger.info(
                "Rule-based response returned",
                extra={"intent": intent, "blocked": True, "rule_reason": rule_result.reason},
            )
            return ChatResponse(
                response=response_text,
                intent=intent,
                memory=session_memory.history(),
                latency_ms=0.0,
                token_usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                provider="rule_engine",
                blocked=True,
                rule_reason=rule_result.reason,
                trace_id=get_current_trace_id(),
            )

        prompt = build_prompt(
            user_input,
            session_memory,
            rule_result,
            selected_scenario=request.selected_scenario,
            goal_text=request.goal_text,
            coach_style=request.coach_style,
        )

        repair_attempted = False
        repair_succeeded: bool | None = None
        try:
            model_result = call_model(prompt)
            response_text = model_result.text or _safe_fallback_response(rule_result, user_input, request.goal_text)

            if not response_is_valid(response_text, rule_result):
                repair_attempted = True
                with start_as_current_span(
                    name="response-repair",
                    metadata={"reason": "validation_failed", "original_response": response_text[:200]},
                ):
                    repair_result = call_model(_repair_prompt(prompt, response_text, rule_result))
                    repaired_text = repair_result.text.strip()
                    if response_is_valid(repaired_text, rule_result):
                        model_result = repair_result
                        response_text = repaired_text
                        repair_succeeded = True
                        langfuse.update_current_span(output={"repair_succeeded": True})
                    else:
                        response_text = _safe_fallback_response(rule_result, user_input, request.goal_text)
                        repair_succeeded = False
                        langfuse.update_current_span(output={"repair_succeeded": False, "used_fallback": True})

        except Exception:
            logger.exception("Model call failed")
            response_text = _safe_fallback_response(rule_result, user_input, request.goal_text)
            model_result = ModelResult(
                text=response_text,
                latency_ms=0.0,
                token_usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                provider="fallback",
            )

        update_memory(session_memory, user_input, response_text)
        _score_response_quality(response_text, rule_result)
        _score_repair_attempted(repair_attempted, repair_succeeded)

        langfuse.update_current_span(
            output={"response": response_text, "provider": model_result.provider}
        )

        logger.info(
            "Pipeline completed",
            extra={
                "intent": intent,
                "blocked": False,
                "provider": model_result.provider,
                "latency_ms": model_result.latency_ms,
                "token_usage": model_result.token_usage,
                "repair_attempted": repair_attempted,
            },
        )

        return ChatResponse(
            response=response_text,
            intent=intent,
            memory=session_memory.history(),
            latency_ms=model_result.latency_ms,
            token_usage=model_result.token_usage,
            provider=model_result.provider,
            blocked=False,
            rule_reason=rule_result.reason,
            trace_id=get_current_trace_id(),
        )


# ---------------------------------------------------------------------------
# Debrief pipeline
# ---------------------------------------------------------------------------

@router.post("/debrief", response_model=DebriefResponse)
@observe(name="debrief-pipeline")
def debrief(request: DebriefRequest) -> DebriefResponse:
    logger.info("Processing debrief request for scenario: %s", request.scenario_title)

    with propagate_attributes(
        trace_name="debrief-pipeline",
        user_id=request.user_id or "anonymous",
        session_id=request.session_id or "default",
        tags=["debrief", f"scenario:{request.scenario_title}", f"skill:{request.scenario_skill}"],
        metadata={
            "scenario_title": request.scenario_title,
            "scenario_skill": request.scenario_skill,
            "confidence_before": str(request.confidence_before),
            "confidence_after": str(request.confidence_after),
            "message_count": str(len(request.messages)),
        },
    ):
        if not request.messages:
            empty_response = DebriefResponse(
                went_well="You opened this session — that's the first step.",
                improve=f"Try to get a few exchanges in next time to build momentum on {request.scenario_skill.replace('_', ' ')}.",
                micro_tip="Set a small target: just two back-and-forth exchanges to start.",
                encouragement="Every session counts. See you next time.",
                provider="fallback",
                latency_ms=0.0,
            )
            langfuse.update_current_span(
                input={"messages": []},
                output={"used_fallback": True, "reason": "no_messages"},
            )
            return empty_response

        prompt = _build_debrief_prompt(request)
        langfuse.update_current_span(
            input={
                "scenario": request.scenario_title,
                "skill": request.scenario_skill,
                "message_count": len(request.messages),
                "confidence_delta": request.confidence_after - request.confidence_before,
            }
        )

        try:
            result = call_model(prompt, max_tokens=300)
            parsed = _parse_debrief(result.text, request)
            parsed.provider = result.provider
            parsed.latency_ms = result.latency_ms
        except Exception:
            logger.exception("Debrief model call failed")
            parsed = _parse_debrief("", request)
            parsed.provider = "fallback"

        _score_debrief(request)

        langfuse.update_current_span(
            output={
                "went_well": parsed.went_well,
                "improve": parsed.improve,
                "micro_tip": parsed.micro_tip,
                "provider": parsed.provider,
            }
        )
        parsed.trace_id = get_current_trace_id()
        return parsed


# ---------------------------------------------------------------------------
# Warmup pipeline
# ---------------------------------------------------------------------------

@router.post("/warmup", response_model=WarmupResponse)
@observe(name="warmup-pipeline")
def warmup(request: WarmupRequest) -> WarmupResponse:
    logger.info("Processing warmup request for scenario: %s", request.scenario_id)

    with propagate_attributes(
        trace_name="warmup-pipeline",
        user_id=request.user_id or "anonymous",
        session_id=request.session_id or "default",
        tags=["warmup", f"scenario:{request.scenario_id}", f"skill:{request.scenario_skill}"],
        metadata={
            "scenario_id": request.scenario_id,
            "scenario_skill": request.scenario_skill,
            "coach_style": str(request.coach_style or ""),
        },
    ):
        skill_fallbacks: Dict[str, List[str]] = {
            "greeting": [
                "Hi — I just arrived and don't know many people here yet.",
                "I'm trying to introduce myself but I'm not sure how to start.",
                "There's someone I'd like to meet. How do I open without it feeling forced?",
            ],
            "follow_ups": [
                "I want to join a lunch table where people are already mid-conversation.",
                "People are talking about a topic I know a little about. How do I step in?",
                "I sat down next to a group but haven't said anything yet.",
            ],
            "confidence": [
                "We're in a meeting and I have an opinion but keep waiting for a gap.",
                "I want to share one idea in class without second-guessing myself.",
                "Everyone seems more confident than me. How do I speak up?",
            ],
            "conversation_flow": [
                "We were talking and then it just went completely silent.",
                "The conversation kind of died and now it feels awkward.",
                "I changed the subject and now neither of us knows what to say.",
            ],
            "conversation_endings": [
                "I need to leave this conversation but I don't want to seem rude.",
                "The chat has run its course but I'm not sure how to wrap it up.",
                "I want to end this on a good note and leave the door open for later.",
            ],
        }

        prompt = _build_warmup_prompt(request)
        langfuse.update_current_span(
            input={"scenario": request.scenario_id, "skill": request.scenario_skill}
        )

        try:
            result = call_model(prompt, max_tokens=120)
            starters = _parse_warmup(result.text)
            if len(starters) < 3:
                starters = skill_fallbacks.get(request.scenario_skill, skill_fallbacks["greeting"])
            response = WarmupResponse(starters=starters[:3], provider=result.provider, latency_ms=result.latency_ms)
        except Exception:
            logger.exception("Warmup model call failed")
            starters = skill_fallbacks.get(request.scenario_skill, skill_fallbacks["greeting"])
            response = WarmupResponse(starters=starters[:3], provider="fallback", latency_ms=0.0)

        langfuse.update_current_span(
            output={"starters": response.starters, "provider": response.provider}
        )
        response.trace_id = get_current_trace_id()
        return response


# ---------------------------------------------------------------------------
# NEW: User feedback endpoint
# ---------------------------------------------------------------------------

@router.post("/feedback", response_model=FeedbackResponse)
def submit_feedback(request: FeedbackRequest) -> FeedbackResponse:
    """Attach user feedback to a specific Langfuse trace."""
    try:
        langfuse.score(
            trace_id=request.trace_id,
            name="user_feedback",
            value=request.score,
            data_type="NUMERIC",
            comment=request.comment or "User submitted feedback",
        )
        logger.info(
            "User feedback recorded",
            extra={"trace_id": request.trace_id, "score": request.score},
        )
    except Exception as exc:
        logger.warning("Failed to record feedback score: %s", exc)

    return FeedbackResponse(
        status="ok",
        trace_id=request.trace_id,
        score=request.score,
    )


@router.post("/session/reset", response_model=SessionResetResponse)
def reset_session(request: SessionResetRequest) -> SessionResetResponse:
    memory_store.clear_memory(user_id=request.user_id, session_id=request.session_id)
    cleared_user = request.user_id or "anonymous"
    cleared_session = request.session_id or "default"
    logger.info(
        "Session memory cleared",
        extra={"user_id": cleared_user, "session_id": cleared_session},
    )
    return SessionResetResponse(
        status="ok",
        user_id=cleared_user,
        session_id=cleared_session,
    )
