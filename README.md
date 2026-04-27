# Rule-Guided Conversational System for Social Interaction Support

## Project Summary

This project is a full-stack AI system designed to support structured social interaction practice.
It is intentionally not a general-purpose chatbot. Instead, it uses a rule-guided pipeline to keep
every interaction focused, supportive, brief, and safely within the domain of social interaction support.

The system combines:

- A FastAPI backend for orchestration and model access
- A Streamlit frontend for the user interface
- Rule-based intent classification and response control
- A single large language model for guided response generation
- Short-term memory for conversational context
- LangSmith tracing for observability and debugging

## Project Purpose

The goal of this project is to help users practice and reflect on social interactions in a structured way.
Rather than allowing unrestricted conversation, the system guides users through manageable conversational steps.
This makes the behavior more controllable, safer, easier to evaluate, and more suitable for use cases where
structured support matters more than open-ended chat.

The system is built to demonstrate:

- Rule-guided interaction instead of free-form conversation
- Intent-aware response shaping
- Context awareness with limited memory
- Controlled use of a single LLM
- Observable execution through LangSmith traces

## Core Objective

The application is designed to:

- Guide users through structured interaction
- Use rule-based logic to control responses
- Use one LLM for generation
- Maintain short-term memory
- Classify user intent
- Track interactions and debugging signals with LangSmith

## System Architecture

The backend follows this processing pipeline:

`User Input -> Intent Classification -> Rule-Based Layer -> Prompt Builder -> LLM -> Memory Update -> Response`

### Pipeline Stages

1. `User Input`
   The user submits a message from the Streamlit interface.

2. `Intent Classification`
   The system uses keyword-based logic to classify the input as one of:
   - `greeting`
   - `emotional_expression`
   - `general_interaction`

3. `Rule-Based Layer`
   The system applies strict rules to:
   - Override simple greetings with a structured practice prompt
   - Enforce a guided response format
   - Block unsafe or out-of-scope requests

4. `Prompt Builder`
   The system constructs a prompt that includes:
   - The assistant role
   - Behavioral rules
   - Recent conversation history
   - Intent-specific guidance

5. `LLM Generation`
   A single causal language model generates the response.

6. `Memory Update`
   The latest interaction is stored in short-term memory using a sliding window.

7. `Response`
   The final output is returned to the frontend and shown to the user.

## Key Features

- FastAPI backend with `/chat` and `/health`
- Streamlit chat interface
- Keyword-based intent classification
- Rule-guided conversational scaffolding
- Short-term memory limited to the last 5 interactions
- llama.cpp local inference support
- Hugging Face Inference API fallback
- LangSmith tracing decorators across the pipeline
- Safety constraints for out-of-scope requests
- Lightweight design for low-VRAM environments such as GTX 1650

## Project Structure

```text
backend/
  main.py
  router.py
  memory.py
  rules.py
  intent.py
  model.py

frontend/
  app.py

tests/
  test_pipeline.py

requirements.txt
.env.example
README.md
```

## Backend Overview

### `backend/main.py`

Creates the FastAPI application, configures logging, and exposes the health endpoint.

### `backend/router.py`

Contains the main interaction pipeline and the `POST /chat` endpoint. It is responsible for:

- Request validation
- Running the structured pipeline
- Calling the model
- Updating memory
- Returning metadata such as latency, provider, and token usage

### `backend/intent.py`

Implements keyword-based intent classification with the following labels:

- `greeting`
- `emotional_expression`
- `general_interaction`

### `backend/rules.py`

Defines the rule engine that controls the interaction behavior. It:

- Overrides greetings with structured prompts
- Blocks empty inputs
- Rejects unsafe or out-of-scope requests
- Supplies guidance and follow-up instructions for prompt construction

### `backend/memory.py`

Implements a sliding-window short-term memory module that stores the last five user-guide exchanges.

### `backend/model.py`

Implements model access with two inference modes:

1. Local `llama.cpp` server
2. Hugging Face Inference API fallback

The default model target is:

- `Qwen/Qwen2.5-7B-Instruct`

Generation settings:

- `temperature = 0.6`
- `top_p = 0.9`
- `max_tokens = 120`

## Frontend Overview

### `frontend/app.py`

The frontend is built with Streamlit and provides:

- A chat-style interface
- Message history display
- User input box
- Request handling to the backend
- Friendly error handling when the backend is unavailable

## Prompt Design

Each generated prompt enforces the following assistant identity:

`You are a conversational guide helping users practice social interaction.`

The prompt also enforces these behavioral rules:

- Be supportive
- Keep responses short
- Ask a follow-up question
- Guide interaction step-by-step
- Stay within the social interaction support domain
- Avoid behaving like a general chatbot

The prompt includes recent conversation history from the short-term memory store to support contextual continuity.

## Rule-Guided Behavior

This system is intentionally controlled by rules before the LLM is called.

### Structured Response Requirements

Responses are guided toward this format:

1. Acknowledge the user
2. Provide one practical guidance step
3. Ask one follow-up question

### Greeting Handling

Simple greetings are not treated as open-ended conversation starters. Instead, they are redirected into a structured practice flow.

### Out-of-Scope and Unsafe Requests

The system rejects requests outside its scope, such as:

- Medical advice
- Legal advice
- Crisis support
- Harmful or self-harm related instructions

When such requests are detected, the system responds with a safe refusal and redirects toward an appropriate social-support practice alternative when possible.

## Memory Design

The application uses short-term memory only.

- Stores the last 5 interactions
- Uses a sliding window
- Injects recent interaction history into the prompt
- Keeps context small for faster responses and lower memory usage

This design supports lightweight deployment and predictable prompt size.

## LangSmith Integration

LangSmith is used for tracing and debugging the pipeline.

The project supports:

- Tracking user input, intent, and response flow
- Logging latency
- Logging token usage
- Capturing traces for prompt creation, model calls, and memory updates

### Environment Variables

Set the following variables to enable tracing:

- `LANGCHAIN_API_KEY`
- `LANGCHAIN_PROJECT`

Tracing is applied through decorators around core functions in the backend pipeline.

## Performance Considerations

This project is optimized for constrained hardware.

### Low-VRAM Support

To work better on systems like a GTX 1650:

- Limit prompt memory to 5 interactions
- Keep generation capped at 120 tokens
- Use short structured responses
- Prefer quantized local models for llama.cpp

### Recommended Local Model Setup

Use a quantized Qwen 2.5 7B Instruct GGUF build such as `Q4_K_M` when running locally with llama.cpp.

The backend now supports two local modes:

1. Connect to an already running `llama.cpp` server through `LLAMA_CPP_URL`
2. Start `llama.cpp` automatically from your downloaded GGUF model using:
   - `LLAMA_CPP_SERVER_PATH`
   - `LLAMA_CPP_MODEL_PATH`

Example managed local configuration:

```env
LLAMA_CPP_URL=http://127.0.0.1:8080
LLAMA_CPP_SERVER_PATH=C:\llama.cpp\build\bin\Release\llama-server.exe
LLAMA_CPP_MODEL_PATH=C:\models\Qwen2.5-7B-Instruct-Q4_K_M.gguf
LLAMA_CPP_CONTEXT_SIZE=2048
LLAMA_CPP_GPU_LAYERS=20
LLAMA_CPP_STARTUP_TIMEOUT=45
```

If you prefer to run the server yourself, this is the equivalent command:

```bash
./server -m ./Qwen2.5-7B-Instruct.gguf -c 2048 -ngl 20 --host 127.0.0.1 --port 8080
```

## Installation

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env` and set the values you need.

Example variables:

```env
LLAMA_CPP_URL=http://127.0.0.1:8080
LLAMA_CPP_SERVER_PATH=
LLAMA_CPP_MODEL_PATH=
LLAMA_CPP_CONTEXT_SIZE=2048
LLAMA_CPP_GPU_LAYERS=20
LLAMA_CPP_STARTUP_TIMEOUT=45
HF_API_TOKEN=
HF_MODEL_ID=Qwen/Qwen2.5-7B-Instruct
LANGCHAIN_API_KEY=
LANGCHAIN_PROJECT=rule-guided-social-support
BACKEND_URL=http://127.0.0.1:8000
```

### Running Fully Local With a Downloaded Model

If you already downloaded a GGUF file, set `LLAMA_CPP_SERVER_PATH` to your `llama-server` binary and
`LLAMA_CPP_MODEL_PATH` to the GGUF file. When the first `/chat` request arrives, the backend will start
the local `llama.cpp` server automatically and reuse it for later requests.

For example on Windows:

```env
LLAMA_CPP_URL=http://127.0.0.1:8080
LLAMA_CPP_SERVER_PATH=C:\llama.cpp\build\bin\Release\llama-server.exe
LLAMA_CPP_MODEL_PATH=C:\Users\USER\Models\Qwen2.5-7B-Instruct-Q4_K_M.gguf
LLAMA_CPP_GPU_LAYERS=10
```

Lower `LLAMA_CPP_GPU_LAYERS` if your GPU runs out of memory.

## Running the Project

### Start the Backend

```bash
uvicorn backend.main:app --reload
```

### Start the Frontend

```bash
streamlit run frontend/app.py
```

### Health Check

The backend health endpoint is available at:

```text
GET /health
```

## API Endpoints

### `POST /chat`

Main interaction endpoint.

Request body:

```json
{
  "user_input": "I feel nervous when meeting new people"
}
```

Response includes:

- Generated response
- Intent label
- Current memory window
- Latency
- Token usage
- Provider used
- Rule status metadata

### `GET /health`

Returns a simple health status response.

## Testing

The project includes tests for:

- Intent classification
- Greeting override behavior
- Empty input handling
- Out-of-scope blocking
- Sliding-window memory behavior
- Repeated input handling

Run tests with:

```bash
python -m unittest discover -s tests
```

## Sample Inputs

Use the following examples to validate behavior:

- `Hi`
- `I feel nervous when meeting new people`
- `Help me practice joining a lunch conversation`
- `I feel awkward speaking in group settings`
- `Can you give me medical advice?`
- Empty input

## Safety Boundaries

This system is limited to social interaction support and practice. It should not be used as:

- A general conversational assistant
- A medical advisor
- A therapist replacement
- A legal advisor
- A crisis intervention system

Its main purpose is to provide controlled conversational scaffolding for guided social practice.

## Future Improvements

Possible future enhancements include:

- Session-specific user memory instead of a shared in-process memory store
- More detailed intent categories
- Stronger rule authoring through configuration files
- Structured evaluation datasets for LangSmith
- Conversation scoring for training and assessment workflows
- Authentication and multi-user session support

## Smaller Model Optimization Notes

The backend now includes several changes that help a smaller model behave more like a larger one for this narrow use case:

- Scenario detection before prompt construction
- Compact memory summaries instead of longer raw history injection
- Explicit three-sentence response scaffolding
- One silent repair attempt when the model misses the expected structure

These changes improve consistency for smaller local models such as `Qwen2.5-3B-Instruct` without changing the high-level architecture.

### What Is Already Handled In Code

- The rule layer identifies a likely practice scenario
- The prompt asks the model for one short acknowledgement, one coaching step, and one follow-up question
- The response is checked for brevity and structure
- If the first answer drifts, the backend asks for one repaired response before falling back

### What Still Needs To Be Done Manually

To push a 3B model closer to 7B quality for this project, the next steps are mostly data and evaluation work:

1. Build a small supervised fine-tuning dataset
   - 500 to 2,000 examples is a good starting range
   - Include greetings, emotional expression, general interaction, and safe refusals
   - Keep the outputs short and in the exact three-part format used by the app

2. Add preference pairs for weak cases
   - Create `chosen` and `rejected` response pairs for vague, overly long, or off-domain outputs
   - Use these later for DPO if SFT alone is not enough

3. Create a fixed evaluation set
   - 50 to 100 representative prompts
   - Score format compliance, brevity, in-domain behavior, and safety

4. Track failures from real sessions
   - Export LangSmith traces
   - Collect examples where the model missed the follow-up question, got too generic, or drifted out of scope
   - Rewrite those into ideal outputs and add them to the training set

5. Fine-tune with LoRA instead of full training
   - Prefer `Qwen/Qwen2.5-3B-Instruct`
   - Use SFT first
   - Add DPO only if you still need better style alignment after SFT

## FAISS Retrieval Layer

The project now includes a lightweight FAISS-based retrieval path for curated coaching knowledge.
This is intended to improve smaller models by giving them short, relevant social-support snippets
before generation.

### Retrieval Design

The retrieval layer stores compact knowledge documents with this schema:

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

These documents are embedded and indexed in FAISS. At runtime, the backend:

1. Detects intent and scenario
2. Queries FAISS with the user input
3. Filters the results by scenario and intent
4. Injects the top retrieved coaching snippets into the prompt

### Files Added

- `data/knowledge_base.jsonl` - curated coaching knowledge source
- `backend/retrieval.py` - FAISS loader and retrieval utilities
- `scripts/build_faiss_index.py` - index builder script
- `scripts/ingest_to_faiss.py` - automation for importing downloaded files and rebuilding the index

### Build The FAISS Index

After installing dependencies, build the local index:

```bash
python scripts/build_faiss_index.py
```

This creates:

- `data/faiss/coaching.index`
- `data/faiss/coaching_metadata.json`

### Retrieval Environment Variables

Optional settings:

```env
FAISS_INDEX_PATH=
FAISS_METADATA_PATH=
EMBEDDING_MODEL_NAME=sentence-transformers/all-MiniLM-L6-v2
RETRIEVAL_TOP_K=3
```

If the FAISS index is missing, the backend simply skips retrieval and continues with the existing rule-guided flow.

### Import Downloaded Files Automatically

If you download relevant source files yourself, you can ingest them into the knowledge base and optionally rebuild FAISS in one step.

Supported formats:

- `.txt`
- `.md`
- `.json`
- `.jsonl`
- `.csv`

Example:

```bash
python scripts/ingest_to_faiss.py ^
  C:\Users\USER\Downloads\social-support-data ^
  --source downloaded_social_data ^
  --scenario social_anxiety_support ^
  --intent emotional_expression ^
  --skill confidence ^
  --tags empathy,support ^
  --replace-source ^
  --rebuild
```

What this does:

1. Finds supported files in the given folder
2. Extracts text content from each file
3. Chunks the text into smaller coaching documents
4. Writes them into `data/knowledge_base.jsonl`
5. Rebuilds the FAISS index if `--rebuild` is provided

This makes it easier to refresh your vector store whenever you download better source material.

## Conclusion

This project demonstrates how to combine symbolic control and LLM generation in a practical full-stack AI application.
It balances flexibility and safety by placing a rule engine before model generation, keeping the assistant focused on
structured social interaction guidance instead of unconstrained conversation.
