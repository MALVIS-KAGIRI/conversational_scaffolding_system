from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

from fastapi import APIRouter
from pydantic import BaseModel, Field

from .intent import classify_intent
from .memory import SlidingWindowMemory
from .model import ModelClient, ModelResult
from .retrieval import FaissKnowledgeBase, format_retrieved_context
from .rules import RuleResult, apply_rules, response_is_valid

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
knowledge_base = FaissKnowledgeBase()
RETRIEVAL_ENABLED = knowledge_base.startup_check()

if RETRIEVAL_ENABLED:
    logger.info("FAISS retrieval enabled for this server run.")
else:
    logger.info("FAISS retrieval disabled for this server run: %s", knowledge_base.disabled_reason)


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
    history = memory.summary_text()
    retrieved_context = "Retrieval unavailable for this server run."
    if RETRIEVAL_ENABLED:
        retrieved = knowledge_base.retrieve(
            query=user_input,
            scenario=rule_result.scenario,
            intent=rule_result.intent,
        )
        retrieved_context = format_retrieved_context(retrieved)
    return f"""
You are a conversational guide helping users practice social interaction.

System rules:
- Be supportive.
- Keep responses short.
- Ask a follow-up question.
- Guide interaction step-by-step.
- Do not act like a general chatbot.
- Stay within social interaction support.
- Keep the whole response to 2 or 3 short sentences.
- Do not add lists, headings, or extra explanations.

Required response structure:
Sentence 1: acknowledge the user or their situation.
Sentence 2: give exactly one practical coaching step.
Sentence 3: ask exactly one follow-up question.

Conversation history:
{history}

Relevant coaching context:
{retrieved_context}

Detected intent: {rule_result.intent}
Detected scenario: {rule_result.scenario}
Rule guidance: {rule_result.guidance}
Required coaching step: {rule_result.coaching_step}
Required follow-up: {rule_result.follow_up}

User input:
{user_input}

Write only the guide response:
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


def _repair_prompt(
    original_prompt: str,
    invalid_response: str,
    rule_result: RuleResult,
) -> str:
    return f"""
{original_prompt}

The previous response did not follow the required format closely enough.

Previous response:
{invalid_response}

Repair instructions:
- Keep the answer under 70 words.
- Use exactly 3 short sentences.
- Include exactly one follow-up question.
- Keep the coaching step aligned to: {rule_result.coaching_step}
- End with a question closely matching: {rule_result.follow_up}

Write only the repaired guide response:
""".strip()


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
        if not response_is_valid(response_text, rule_result):
            repair_result = call_model(_repair_prompt(prompt, response_text, rule_result))
            repaired_text = repair_result.text.strip()
            if response_is_valid(repaired_text, rule_result):
                model_result = repair_result
                response_text = repaired_text
            else:
                response_text = _safe_fallback_response(rule_result, user_input)
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
