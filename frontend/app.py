from __future__ import annotations

import os

import requests
import streamlit as st


BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")

st.set_page_config(
    page_title="Social Interaction Support Guide",
    page_icon="💬",
    layout="centered",
)

st.title("Rule-Guided Conversational System")
st.caption("Structured social interaction practice with rule-based control.")

if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.write(message["content"])

user_input = st.chat_input("Describe a social situation you want to practice")

if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.write(user_input)

    try:
        response = requests.post(
            f"{BACKEND_URL}/chat",
            json={"user_input": user_input},
            timeout=90,
        )
        response.raise_for_status()
        payload = response.json()
        assistant_text = payload["response"]
    except Exception as exc:
        assistant_text = (
            "I could not reach the backend right now. "
            "Please make sure the FastAPI server is running, then try again."
        )
        st.error(str(exc))

    st.session_state.messages.append({"role": "assistant", "content": assistant_text})
    with st.chat_message("assistant"):
        st.write(assistant_text)
