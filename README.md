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

## Conclusion

This project demonstrates how to combine symbolic control and LLM generation in a practical full-stack AI application.
It balances flexibility and safety by placing a rule engine before model generation, keeping the assistant focused on
structured social interaction guidance instead of unconstrained conversation.
