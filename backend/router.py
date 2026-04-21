from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

from fastapi import APIRouter
from pydantic import BaseModel, Field

from .intent import classify_intent
from .memory import SlidingWindowMemory
from .model import ModelClient, ModelResult
from .rules import RuleResult, apply_rules

try:
    from langsmith import traceable
except ImportError:  # pragma: no cover
    def traceable(*args: Any, **kwargs: Any):  # type: ignore[misc]
        def decorator(func: Any) -> Any:
            return func

        return decorator


logger = logging.getLogger(__name__)
router = APIRouter()
memory_store = SlidingWindowMemory(max_items=5)
model_client = ModelClient()


class ChatRequest(BaseModel):
    user_input: str = Field(..., description="The user's latest message.")


class ChatResponse(BaseModel):
    response: str
    intent: str
    memory: List[Dict[str, str]]
    latency_ms: float
    token_usage: Dict[str, int]
    provider: str
    blocked: bool
    rule_reason: str | None = None


@traceable(name="classify_intent", run_type="chain")
def traced_classify_intent(user_input: str) -> str:
    return classify_intent(user_input)


@traceable(name="apply_rules", run_type="chain")
def traced_apply_rules(user_input: str, intent: str) -> RuleResult:
    return apply_rules(user_input, intent)


@traceable(name="build_prompt", run_type="prompt")
def build_prompt(user_input: str, memory: SlidingWindowMemory, rule_result: RuleResult) -> str:
    history = memory.as_text()
    return f"""
You are a conversational guide helping users practice social interaction.

System rules:
- Be supportive.
- Keep responses short.
- Ask a follow-up question.
- Guide interaction step-by-step.
- Do not act like a general chatbot.
- Stay within social interaction support.
- Use this response format:
  1. Acknowledge the user.
  2. Provide one practical guidance step.
  3. Ask one follow-up question.

Conversation history:
{history}

Detected intent: {rule_result.intent}
Rule guidance: {rule_result.guidance}
Required follow-up: {rule_result.follow_up}

User input:
{user_input}

Guide response:
""".strip()


@traceable(name="call_model", run_type="llm")
def call_model(prompt: str) -> ModelResult:
    return model_client.generate(
        prompt=prompt,
        temperature=0.6,
        top_p=0.9,
        max_tokens=120,
    )


@traceable(name="update_memory", run_type="chain")
def update_memory(user_input: str, response: str) -> None:
    memory_store.add(user_input=user_input, response=response)


def _safe_fallback_response(rule_result: RuleResult, user_input: str) -> str:
    base = "I hear what you are saying."

    if rule_result.intent == "emotional_expression":
        base = "I hear that this feels difficult."
    elif rule_result.intent == "general_interaction":
        base = "I understand the situation you want to practice."

    return (
        f"{base} {rule_result.guidance} {rule_result.follow_up}"
        if user_input.strip()
        else "Please share one short situation you want to practice. What would you like to rehearse?"
    )


@traceable(name="social_interaction_pipeline", run_type="chain")
def run_pipeline(user_input: str) -> ChatResponse:
    intent = traced_classify_intent(user_input)
    rule_result = traced_apply_rules(user_input, intent)

    if rule_result.blocked and rule_result.response:
        response_text = rule_result.response
        update_memory(user_input, response_text)
        logger.info(
            "Rule-based response returned",
            extra={
                "intent": intent,
                "blocked": True,
                "rule_reason": rule_result.reason,
                "provider": "rule_engine",
            },
        )
        return ChatResponse(
            response=response_text,
            intent=intent,
            memory=memory_store.history(),
            latency_ms=0.0,
            token_usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            provider="rule_engine",
            blocked=True,
            rule_reason=rule_result.reason,
        )

    prompt = build_prompt(user_input, memory_store, rule_result)

    try:
        model_result = call_model(prompt)
        response_text = model_result.text or _safe_fallback_response(rule_result, user_input)
    except Exception as exc:  # pragma: no cover
        logger.exception("Model call failed")
        response_text = _safe_fallback_response(rule_result, user_input)
        model_result = ModelResult(
            text=response_text,
            latency_ms=0.0,
            token_usage={
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            },
            provider="fallback",
        )

    update_memory(user_input, response_text)
    logger.info(
        "Pipeline completed",
        extra={
            "intent": intent,
            "blocked": False,
            "provider": model_result.provider,
            "latency_ms": model_result.latency_ms,
            "token_usage": model_result.token_usage,
        },
    )

    return ChatResponse(
        response=response_text,
        intent=intent,
        memory=memory_store.history(),
        latency_ms=model_result.latency_ms,
        token_usage=model_result.token_usage,
        provider=model_result.provider,
        blocked=False,
        rule_reason=rule_result.reason,
    )


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    logger.info(
        "Processing chat request",
        extra={
            "project": os.getenv("LANGCHAIN_PROJECT", "social-interaction-support"),
            "user_input": request.user_input,
        },
    )
    return run_pipeline(request.user_input)
