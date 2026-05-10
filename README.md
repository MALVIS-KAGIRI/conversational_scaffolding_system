# Social Interaction Support Guide

A full-stack AI coaching system for structured social interaction practice.
Not a general-purpose chatbot — every interaction is rule-guided, focused, and safely bounded to social skills training.

---

## Project Summary

This system helps users build social confidence through guided, repeatable practice sessions. A rule engine shapes every interaction before the LLM is called, keeping responses short, structured, and on-topic. A Streamlit frontend provides a rich multi-page coaching workspace with analytics, session history, and progressive skill unlocks.

The stack combines:

- **FastAPI backend** — orchestration, rule enforcement, model access
- **Streamlit frontend** — multi-page coaching UI with insights and session management
- **Groq API** (primary LLM) — `llama-3.1-8b-instant`, fast and free-tier friendly
- **llama.cpp local server** — offline/rate-limit fallback
- **Hugging Face Inference API** — last-resort fallback
- **FAISS retrieval** — optional curated coaching snippets injected into prompts
- **Langfuse tracing** — full OTEL-based observability across the pipeline

---

## Project Purpose

The goal is to give users a low-stakes environment to rehearse social situations — joining a group conversation, greeting someone new, recovering from an awkward silence — with a structured AI coach that advances the session rather than repeating generic questions.

The system demonstrates:

- Rule-guided interaction with phase-aware conversation advancement
- Intent-aware response shaping
- Short-term memory with proper dialogue formatting
- Controlled LLM use with a repair-and-fallback loop
- Full observability via Langfuse traces, spans, and generation metadata

---

## System Architecture

```
User Input
    │
    ▼
Intent Classification (keyword-based)
    │
    ▼
Rule-Based Layer (block / redirect / shape)
    │         │
    │     [blocked] ──► Safe Response
    │
    ▼
Prompt Builder (phase-aware, history-formatted)
    │
    ▼
LLM Generation (Groq → llama.cpp → HuggingFace)
    │
    ▼
Response Validator ──[invalid]──► Repair Attempt ──[still invalid]──► Fallback
    │
    ▼
Memory Update (sliding window, 5 turns)
    │
    ▼
Response → Frontend
```

### Pipeline Stages

1. **Intent Classification** — classifies input as `greeting`, `emotional_expression`, or `general_interaction` using keyword matching.

2. **Rule-Based Layer** — applies strict pre-LLM rules to block unsafe requests, redirect greetings to structured practice prompts, and supply scenario-specific guidance for the prompt builder.

3. **Prompt Builder** — constructs a phase-aware prompt. The phase changes based on turn count:
   - Turn 0: Set up scenario, ask one context question
   - Turn 1: Acknowledge answer, begin active roleplay
   - Turns 2–3: Mid-session coaching, no setup repetition
   - Turn 4+: Introduce complications to deepen practice

4. **LLM Generation** — calls Groq first, falls back to llama.cpp on network failure or rate limiting (HTTP 429/403/503/529), then to Hugging Face as a last resort.

5. **Response Validation & Repair** — validates the response for brevity, structure, and required follow-up question. If invalid, one silent repair attempt is made before using a safe fallback.

6. **Memory Update** — stores the exchange in a 5-turn sliding window, formatted as `[Turn N] User: / [Turn N] Coach:` for proper dialogue injection.

7. **Response** — returned to the Streamlit frontend with metadata: provider, latency, token usage, intent, and rule reason.

---

## Backend

### Files

```
backend/
  main.py        FastAPI app, CORS, health endpoint
  router.py      Pipeline, all endpoints, Langfuse tracing
  tracing.py     Langfuse SDK v3 initialisation and no-op shims
  intent.py      Keyword-based intent classifier
  rules.py       Rule engine, scenario detection, safety blocking
  memory.py      SlidingWindowMemory (5-turn window)
  model.py       ModelClient: Groq → llama.cpp → HuggingFace
  retrieval.py   FAISS knowledge base loader and retrieval
```

### `main.py`

Creates the FastAPI app, loads `.env`, configures logging, registers the router, and exposes `/health`. The health endpoint reports which inference backends are configured:

```json
{
  "status": "ok",
  "groq_configured": "true",
  "llama_cpp_url_configured": "false",
  "llama_cpp_managed_configured": "false",
  "huggingface_configured": "false"
}
```

### `router.py`

Contains all three API endpoints and the full pipeline logic. Every function is traced with Langfuse `@observe` decorators. Key responsibilities:

- `run_pipeline` — root trace for `/chat`, enriches trace with user/session context
- `call_model` — annotated as a Langfuse `generation` with token usage and model metadata
- `build_prompt` — phase-aware prompt construction with history formatted as a dialogue
- `traced_classify_intent` / `traced_apply_rules` — individually observed child spans
- Response repair wrapped in its own named child span for visibility in Langfuse

### `tracing.py`

Initialises the Langfuse SDK v3 client once at import time using `get_client()`. Provides no-op shims for `langfuse`, `observe`, and `propagate_attributes` so the app starts cleanly without Langfuse credentials — every traced function silently becomes a pass-through.

### `intent.py`

Keyword-based intent classifier returning one of:

| Intent | Trigger keywords |
|---|---|
| `greeting` | hello, hi, hey, good morning, good afternoon, good evening |
| `emotional_expression` | nervous, anxious, worried, sad, upset, lonely, awkward, scared, frustrated, embarrassed |
| `general_interaction` | everything else |

### `rules.py`

Pre-LLM rule engine with full scenario detection and safety blocking. Responsibilities:

- **Empty input** — blocked with a prompt to share a practice situation
- **Unsafe content** — blocked on keywords such as `suicide`, `medical advice`, `legal advice`, `self-harm`; returns a safe refusal
- **Greeting intent** — redirected to a structured practice prompt
- **Scenario detection** — maps user input and frontend selection to one of five internal scenarios: `greeting_practice`, `joining_group`, `social_anxiety_support`, `small_talk_flow`, `conversation_exit`
- Supplies `coaching_step` and `follow_up` strings for the prompt builder

### `memory.py`

`SlidingWindowMemory` stores up to 5 user-assistant exchanges in a thread-safe deque. The router reads history via `.history()` which returns structured `{user, assistant}` dicts, then formats them into a labelled dialogue (`[Turn N] User: / [Turn N] Coach:`) before prompt injection.

### `model.py`

`ModelClient` implements a three-tier provider chain:

**1. Groq (primary)**
- Model: `llama-3.1-8b-instant` (configurable via `GROQ_MODEL_ID`)
- Endpoint: `https://api.groq.com/openai/v1/chat/completions`
- Falls back on: HTTP 429 (rate limit), 403 (Cloudflare block), 503/529 (overload), or any `OSError`/`TimeoutError` (no internet)
- Uses `User-Agent: python-groq-client/1.0` to pass Cloudflare bot checks

**2. llama.cpp local (fallback)**
- Connects to an already-running server via `LLAMA_CPP_URL`, or auto-starts one using `LLAMA_CPP_SERVER_PATH` + `LLAMA_CPP_MODEL_PATH`
- Auto-start uses `atexit` to cleanly terminate the process on shutdown

**3. Hugging Face Inference API (last resort)**
- Only used if `HF_API_TOKEN` is set and both Groq and llama.cpp are unavailable

### `retrieval.py`

Optional FAISS-based retrieval layer. At startup, `FaissKnowledgeBase.startup_check()` checks whether the index and metadata files exist and whether `faiss-cpu` and `sentence-transformers` are installed. If either condition fails, retrieval is silently disabled and the pipeline continues without it.

When enabled, the retrieval step:
1. Embeds the user input using `sentence-transformers/all-MiniLM-L6-v2`
2. Queries the FAISS index
3. Filters results by scenario and intent
4. Injects the top-K coaching snippets into the prompt

---

## API Endpoints

### `POST /chat`

Main interaction endpoint.

Request:
```json
{
  "user_input": "I feel nervous joining conversations at work",
  "selected_scenario": "lunch_group",
  "goal_text": "Ask one natural follow-up question",
  "coach_style": "Supportive",
  "session_id": "optional-session-uuid",
  "user_id": "optional-user-id"
}
```

Response:
```json
{
  "response": "It sounds like joining mid-conversation feels daunting...",
  "intent": "emotional_expression",
  "memory": [...],
  "latency_ms": 423.5,
  "token_usage": {"prompt_tokens": 210, "completion_tokens": 58, "total_tokens": 268},
  "provider": "groq",
  "blocked": false,
  "rule_reason": null
}
```

### `POST /debrief`

Generates a structured post-session AI debrief from the full conversation transcript.

Request:
```json
{
  "messages": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}],
  "scenario_title": "Join a Lunch Conversation",
  "scenario_skill": "follow_ups",
  "goal_text": "Ask one natural follow-up question",
  "coach_style": "Supportive",
  "confidence_before": 2,
  "confidence_after": 4,
  "session_id": "optional",
  "user_id": "optional"
}
```

Response:
```json
{
  "went_well": "You picked up on the food topic naturally and built on it.",
  "improve": "Try to ask about the other person rather than describing your own experience.",
  "micro_tip": "Use the 'echo and ask' technique: repeat one word they said, then ask about it.",
  "encouragement": "Your confidence jumped two points today — that progress is real.",
  "provider": "groq",
  "latency_ms": 891.2
}
```

### `POST /warmup`

Returns 3 suggested opening messages tailored to the selected scenario and skill.

Request:
```json
{
  "scenario_id": "lunch_group",
  "scenario_title": "Join a Lunch Conversation",
  "scenario_skill": "follow_ups",
  "goal_text": "Ask one natural follow-up question",
  "coach_style": "Supportive",
  "session_id": "optional",
  "user_id": "optional"
}
```

Response:
```json
{
  "starters": [
    "I want to join a lunch table where people are already mid-conversation.",
    "People are talking about a topic I know a little about. How do I step in?",
    "I sat down next to a group but haven't said anything yet."
  ],
  "provider": "groq",
  "latency_ms": 312.0
}
```

### `GET /health`

Returns backend status and configured provider flags.

---

## Frontend

The frontend is a Streamlit multi-page application with a themed coaching workspace.

### Pages

| Page | Purpose |
|---|---|
| **Home** | Overview dashboard, recommended session, stats, skill map, consistency heatmap |
| **Practice** | Active coaching session with step progress, warmup starters, typing indicator, session timer, coach panel |
| **Scenarios** | Scenario library with filtering, difficulty tags, skill unlock progression |
| **Insights** | Analytics: KPI cards, confidence trend, skill breakdown charts, heatmap, AI coach insight |
| **History** | Session log with confidence deltas, full transcript replay, practice-again shortcut |
| **Profile** | Coach style (with live preview), difficulty preference, streak freeze, weekly goal |

### Features

**Session flow**
- Warmup starters — 3 AI-generated opening messages fetched before the first turn, tappable to begin
- Typing indicator — animated 3-dot bounce while the backend responds
- Session timer — live `MM:SS` clock in the Practice sidebar
- Contextual coach tips — rotating scenario-specific tips with a "Next tip" button
- Step progress dots — 4-step visual indicator showing session phase
- Confidence sliders — before/after rating captured at the end of each session
- Post-session AI debrief — structured feedback card (what went well, to improve, micro-tip, encouragement) generated by calling `/debrief`
- Confidence celebration — animated banner in the sidebar when confidence improves

**Progress & motivation**
- Skill unlock progression — Advanced scenarios locked until 2 Intermediate sessions are completed
- Streak freeze — one protected off-day per week that does not break the streak
- Weekly recap banner — shown on Mondays, summarises last week's session count, avg confidence, and top skill
- "What do I work on?" shortcut — one-tap button on Home that starts the weakest-skill scenario

**Analytics (Insights page)**
- 4 KPI cards: total sessions, day streak, average confidence, weekly goal progress
- Personalised AI coach insight (strongest and weakest skill callout)
- Confidence over time line chart (last 10 sessions)
- Skill breakdown bar chart
- Difficulty distribution bar chart
- 12-week practice heatmap

**History**
- Full conversation transcript saved per session
- Expandable replay in the History page
- Confidence before/after delta with colour coding

**Empty states**
- Illustrated SVG empty states on History and Insights when no sessions exist

### Scenario Library

Five practice scenarios across three difficulty levels:

| Scenario | Skill | Difficulty | Unlock Requirement |
|---|---|---|---|
| Join a Lunch Conversation | Follow-ups | Beginner | None |
| Meet Someone New | Greeting | Beginner | None |
| Speak in a Group Setting | Confidence | Intermediate | None |
| Recover From Awkward Silence | Flow | Intermediate | None |
| End a Conversation Smoothly | Endings | Advanced | 2 Intermediate sessions |

### Coach Styles

Three coaching styles selectable in Profile, each with a live example preview:

| Style | Approach |
|---|---|
| **Supportive** | Warm acknowledgement, reflective questions |
| **Calm** | Measured, steady, one refinement at a time |
| **Direct** | Specific, actionable, no padding |

---

## Observability — Langfuse

The backend uses Langfuse SDK v3 (OTEL-based) for full pipeline tracing.

### What is traced

| Trace / Span | Type | Captures |
|---|---|---|
| `chat-pipeline` | Root trace | user_id, session_id, scenario tags, trace-level I/O |
| `classify-intent` | Span | Input text, classified intent |
| `apply-rules` | Span | Input, scenario, blocked flag, reason |
| `build-prompt` | Span | Turn count, prompt length, retrieval status, phase |
| `llm-generation` | **Generation** | Full prompt, response text, model, token usage, latency |
| `response-repair` | Span | Original response, repair success/failure |
| `update-memory` | Span | Exchange stored, memory size |
| `debrief-pipeline` | Root trace | Scenario, skill, confidence delta, message count |
| `warmup-pipeline` | Root trace | Scenario, skill, generated starters |

### Session and user linking

Pass `session_id` and `user_id` in any request body to group traces by session or user in the Langfuse UI. Both fields are optional — they default to `"default"` and `"anonymous"` respectively.

### Setup

Add to `.env`:

```env
LLAMA_CPP_URL=http://127.0.0.1:8080
LLAMA_CPP_SERVER_PATH=
LLAMA_CPP_MODEL_PATH=
LLAMA_CPP_CONTEXT_SIZE=2048
LLAMA_CPP_GPU_LAYERS=20
LLAMA_CPP_STARTUP_TIMEOUT=45
HF_API_TOKEN=
HF_MODEL_ID=
LANGCHAIN_API_KEY=
LANGCHAIN_PROJECT=rule-guided-social-support
BACKEND_URL=http://127.0.0.1:8000
FAISS_INDEX_PATH=
FAISS_METADATA_PATH=
EMBEDDING_MODEL_NAME=sentence-transformers/all-MiniLM-L6-v2
RETRIEVAL_TOP_K=3
GROQ_API_KEY=gsk...
GROQ_MODEL_ID=llama-3.1-8b-instant

OTEL_RESOURCE_ATTRIBUTES=service.name=social-ai-backend
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
OTEL_EXPORTER_OTLP_PROTOCOL=grpc
OTEL_METRICS_EXPORTER=none

LANGFUSE_HOST=https://cloud.langfuse.com
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_BASE_URL=http://localhost:3000
```

If the keys are not set, all tracing silently becomes a no-op — the application runs normally without Langfuse configured.

---

## Installation

### 1. Clone and install dependencies

```bash
pip install -r requirements.txt
```

Required packages include: `fastapi`, `uvicorn`, `pydantic`, `python-dotenv`, `streamlit`, `requests`, `langfuse`.

Optional for FAISS retrieval: `faiss-cpu`, `sentence-transformers`.

### 2. Configure environment

Copy `.env.example` to `.env` and fill in the values you need:

```env
# ── Primary inference (required) ─────────────────────────────────────────────
GROQ_API_KEY=gsk_...
GROQ_MODEL_ID=llama-3.1-8b-instant        # default, can be omitted

# ── Local fallback (optional) ─────────────────────────────────────────────────
LLAMA_CPP_URL=http://127.0.0.1:8080
LLAMA_CPP_SERVER_PATH=                    # path to llama-server binary (auto-start)
LLAMA_CPP_MODEL_PATH=                     # path to .gguf model file   (auto-start)
LLAMA_CPP_CONTEXT_SIZE=2048
LLAMA_CPP_GPU_LAYERS=20
LLAMA_CPP_STARTUP_TIMEOUT=45

# ── HuggingFace last resort (optional) ───────────────────────────────────────
HF_API_TOKEN=
HF_MODEL_ID=Qwen/Qwen2.5-7B-Instruct

# ── Langfuse observability (optional) ────────────────────────────────────────
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com

# ── FAISS retrieval (optional) ────────────────────────────────────────────────
FAISS_INDEX_PATH=
FAISS_METADATA_PATH=
EMBEDDING_MODEL_NAME=sentence-transformers/all-MiniLM-L6-v2
RETRIEVAL_TOP_K=3

# ── Frontend ──────────────────────────────────────────────────────────────────
BACKEND_URL=http://127.0.0.1:8000

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_LEVEL=INFO
```

### 3. Provider priority

The backend selects inference providers in this order:

```
Groq (primary) → llama.cpp (offline / rate-limited) → HuggingFace (last resort)
```

Groq is always tried first. Local llama.cpp is used only when Groq is unreachable or returns a rate-limit/overload error. HuggingFace is the final fallback if neither is available.

### 4. Build the FAISS index (optional)

If you want retrieval-augmented prompts:

```bash
python scripts/build_faiss_index.py
```

This creates `data/faiss/coaching.index` and `data/faiss/coaching_metadata.json`. If these files are absent, the pipeline skips retrieval silently.

To ingest your own source documents:

```bash
python scripts/ingest_to_faiss.py /path/to/documents \
  --source my_source \
  --scenario joining_group \
  --intent general_interaction \
  --skill follow_ups \
  --tags group,follow-up \
  --rebuild
```

Supported formats: `.txt`, `.md`, `.json`, `.jsonl`, `.csv`.

---

## Running the Project

### Start the backend

```bash
uvicorn backend.main:app --reload
```

### Start the frontend

```bash
streamlit run frontend/frontend.py
```

### Health check

```
GET http://127.0.0.1:8000/health
```

---

## Project Structure

```
backend/
  main.py           FastAPI app entry point
  router.py         Pipeline logic and API endpoints
  tracing.py        Langfuse SDK v3 initialisation and no-op shims
  intent.py         Keyword-based intent classifier
  rules.py          Rule engine and scenario detection
  memory.py         Sliding-window short-term memory
  model.py          ModelClient: Groq → llama.cpp → HuggingFace
  retrieval.py      FAISS knowledge base loader

frontend/
  frontend.py       Streamlit multi-page coaching UI

data/
  knowledge_base.jsonl        Curated coaching snippets
  faiss/
    coaching.index            FAISS vector index (generated)
    coaching_metadata.json    Document metadata (generated)

scripts/
  build_faiss_index.py        Builds the FAISS index from the knowledge base
  ingest_to_faiss.py          Ingests new documents and optionally rebuilds the index

.env.example
requirements.txt
README.md
```

---

## Prompt Design

The prompt builder produces a phase-aware instruction that changes based on how many turns have already occurred, preventing the model from repeating setup questions or resetting context on every turn.

**System identity:**

> You are a social interaction coach running a live practice session with a user.

**Core rules (injected every turn):**
- Never repeat a question or coaching point already made this session
- Never re-introduce scenario context that has already been established
- Each response must move the conversation forward
- Keep responses to 2–3 short sentences
- No lists, headings, or meta-commentary
- Stay inside the social interaction scenario

**History format:**

Conversation history is injected as a structured dialogue:
```
[Turn 1] User: I want to join a lunch table where people are already talking.
[Turn 1] Coach: Great choice — let's set the scene. Who are these people?
[Turn 2] User: My colleagues. They're talking about food.
```

This format allows the model to understand turn order and avoids the flat summary text that caused repeated questions in earlier versions.

---

## Rule-Guided Behavior

### Safety blocking

Requests containing any of these keywords are blocked and return a safe refusal:
`diagnose`, `diagnosis`, `prescribe`, `prescription`, `medical advice`, `legal advice`, `suicide`, `self-harm`, `harm someone`, `kill`, `overdose`

### Greeting handling

Simple greetings are redirected into a structured practice prompt rather than treated as open-ended conversation openers.

### Response validation

Every generated response is checked for:
- Non-empty text
- At least one question mark (follow-up question required)
- Fewer than 5 sentences
- Fewer than 70 words

If the response fails, one silent repair attempt is made. If the repair also fails, a deterministic safe fallback is used. Both outcomes are recorded as child spans in Langfuse.

---

## Performance Notes

Optimised for constrained hardware (tested on GTX 1650, 4 GB VRAM):

- Memory limited to 5 interactions to keep prompts short
- Generation capped at 120 tokens for chat, 300 for debrief
- Groq API eliminates local GPU load during normal operation
- Quantized GGUF models recommended for local fallback (`Q4_K_M`)
- Lower `LLAMA_CPP_GPU_LAYERS` if your GPU runs out of memory

---

## Testing

Run the test suite with:

```bash
python -m unittest discover -s tests
```

Tests cover:
- Intent classification
- Greeting redirect behavior
- Empty input blocking
- Out-of-scope safety blocking
- Sliding-window memory behavior
- Repeated input handling

---

## Sample Inputs

Use these to validate pipeline behavior end-to-end:

| Input | Expected behavior |
|---|---|
| `Hi` | Redirected to practice prompt (greeting rule) |
| `I feel nervous when meeting new people` | Emotional expression — model responds with acknowledgement and coaching step |
| `Help me practice joining a lunch conversation` | `joining_group` scenario detected, practice begins |
| `Can you give me medical advice?` | Blocked — safety rule returns safe refusal |
| *(empty)* | Blocked — prompts user to share a practice situation |
| `I feel awkward speaking in groups` | `social_anxiety_support` scenario, emotional intent |

---

## Safety Boundaries

This system is limited to social interaction support and practice only. It must not be used as:

- A general conversational assistant
- A medical advisor
- A therapist replacement
- A legal advisor
- A crisis intervention system

Its purpose is controlled conversational scaffolding for guided social skills practice.

---

## Future Improvements

- Per-user persistent memory instead of a shared in-process store
- Authentication and multi-user session isolation
- More granular intent categories (e.g. `topic_change`, `exit_signal`)
- Langfuse-based structured evaluation datasets with LLM-as-judge scoring
- Conversation scoring for session assessment and progress tracking
- Configurable rule authoring via external YAML/JSON files
- Fine-tuning pipeline: SFT dataset construction from Langfuse traces, LoRA fine-tuning on `Qwen2.5-3B-Instruct`

---

## FAISS Retrieval Schema

Each document in the knowledge base follows this structure:

```json
{
  "id": "group_01",
  "type": "coaching_snippet",
  "scenario": "joining_group",
  "intent": "general_interaction",
  "skill": "follow_ups",
  "content": "To join a group conversation, start with a short comment tied to the current topic, then ask one light follow-up question.",
  "source": "curated_internal",
  "tags": ["group", "follow-up"]
}
```

Valid scenario values: `joining_group`, `greeting_practice`, `social_anxiety_support`, `small_talk_flow`, `conversation_exit`, `any`

Valid intent values: `greeting`, `emotional_expression`, `general_interaction`, `any`
