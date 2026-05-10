from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch

from backend.intent import classify_intent
from backend.memory import SessionMemoryStore, SlidingWindowMemory
from backend.model import DEFAULT_GROQ_MODEL_NAME, GROQ_BASE_URL, ModelClient, _port_from_url
from backend.retrieval import FaissKnowledgeBase, KnowledgeDocument, format_retrieved_context
from backend.rules import apply_rules, detect_scenario, normalize_scenario_name, response_is_valid
from scripts.ingest_to_faiss import chunk_text, clean_text, flatten_json_text


class IntentTests(unittest.TestCase):
    def test_greeting_intent(self) -> None:
        self.assertEqual(classify_intent("hello there"), "greeting")

    def test_longer_message_with_hi_is_not_treated_as_greeting(self) -> None:
        self.assertEqual(
            classify_intent("I want to practice how I introduce myself in a new group"),
            "general_interaction",
        )

    def test_emotional_intent(self) -> None:
        self.assertEqual(classify_intent("I feel nervous in groups"), "emotional_expression")

    def test_general_intent(self) -> None:
        self.assertEqual(classify_intent("How do I join a conversation?"), "general_interaction")


class RuleTests(unittest.TestCase):
    def test_empty_input_blocked(self) -> None:
        result = apply_rules("", "general_interaction")
        self.assertTrue(result.blocked)
        self.assertEqual(result.reason, "empty_input")

    def test_greeting_overridden(self) -> None:
        result = apply_rules("hello", "greeting")
        self.assertTrue(result.blocked)
        self.assertIn("Which situation should we work on first?", result.response or "")

    def test_greeting_is_not_restarted_mid_session(self) -> None:
        result = apply_rules("hi", "greeting", session_started=True)
        self.assertFalse(result.blocked)
        self.assertEqual(result.intent, "general_interaction")
        self.assertIn("active scenario", result.guidance.lower())

    def test_out_of_scope_blocked(self) -> None:
        result = apply_rules("Can you give medical advice?", "general_interaction")
        self.assertTrue(result.blocked)
        self.assertEqual(result.reason, "out_of_scope")

    def test_scenario_detection_for_group_joining(self) -> None:
        scenario = detect_scenario("How do I join a lunch table conversation?", "general_interaction")
        self.assertEqual(scenario, "joining_group")

    def test_frontend_selected_scenario_is_normalized(self) -> None:
        self.assertEqual(normalize_scenario_name("meet_someone_new"), "greeting_practice")

    def test_frontend_selected_scenario_overrides_generic_input(self) -> None:
        result = apply_rules(
            "I want to practice",
            "general_interaction",
            preferred_scenario="meet_someone_new",
        )
        self.assertEqual(result.scenario, "greeting_practice")
        self.assertIn("opening line", result.follow_up.lower())


class MemoryTests(unittest.TestCase):
    def test_sliding_window_keeps_last_five(self) -> None:
        memory = SlidingWindowMemory(max_items=5)
        for index in range(7):
            memory.add(f"user {index}", f"assistant {index}")
        history = memory.history()
        self.assertEqual(len(history), 5)
        self.assertEqual(history[0]["user"], "user 2")
        self.assertEqual(history[-1]["user"], "user 6")

    def test_repeated_input_is_stored_without_breaking_window(self) -> None:
        memory = SlidingWindowMemory(max_items=5)
        for _ in range(3):
            memory.add("hello", "structured reply")
        history = memory.history()
        self.assertEqual(len(history), 3)
        self.assertTrue(all(item["user"] == "hello" for item in history))

    def test_summary_text_uses_compact_recent_context(self) -> None:
        memory = SlidingWindowMemory(max_items=5)
        memory.add("I feel awkward", "Start with one simple opener. What setting do you want to practice?")
        summary = memory.summary_text()
        self.assertIn("Recent practice count: 1.", summary)
        self.assertIn("Latest user focus: I feel awkward", summary)

    def test_session_memory_is_isolated_by_user_and_session(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = f"{temp_dir}/session_memory.sqlite3"
            store = SessionMemoryStore(max_items=5, db_path=db_path)
            session_a = store.get_memory(user_id="user-a", session_id="session-1")
            session_b = store.get_memory(user_id="user-a", session_id="session-2")
            session_c = store.get_memory(user_id="user-b", session_id="session-1")

            session_a.add("hello", "reply a")
            session_b.add("hi", "reply b")
            session_c.add("hey", "reply c")

            self.assertEqual(len(session_a.history()), 1)
            self.assertEqual(session_a.history()[0]["assistant"], "reply a")
            self.assertEqual(session_b.history()[0]["assistant"], "reply b")
            self.assertEqual(session_c.history()[0]["assistant"], "reply c")
            self.assertEqual(store.session_count(), 3)

    def test_session_memory_persists_across_store_instances(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = f"{temp_dir}/session_memory.sqlite3"
            first_store = SessionMemoryStore(max_items=5, db_path=db_path)
            first_session = first_store.get_memory(user_id="user-a", session_id="session-1")
            first_session.add("hello", "reply a")

            second_store = SessionMemoryStore(max_items=5, db_path=db_path)
            second_session = second_store.get_memory(user_id="user-a", session_id="session-1")

            self.assertEqual(len(second_session.history()), 1)
            self.assertEqual(second_session.history()[0]["user"], "hello")
            self.assertEqual(second_session.history()[0]["assistant"], "reply a")

    def test_session_memory_can_be_cleared(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = f"{temp_dir}/session_memory.sqlite3"
            store = SessionMemoryStore(max_items=5, db_path=db_path)
            session = store.get_memory(user_id="user-a", session_id="session-1")
            session.add("hello", "reply a")

            store.clear_memory(user_id="user-a", session_id="session-1")
            cleared = store.get_memory(user_id="user-a", session_id="session-1")

            self.assertEqual(cleared.history(), [])


class ModelConfigTests(unittest.TestCase):
    def test_port_parser_defaults_to_8080(self) -> None:
        self.assertEqual(_port_from_url("http://127.0.0.1"), 8080)
        self.assertEqual(_port_from_url("http://127.0.0.1:9000"), 9000)

    @patch("backend.model._server_is_ready", return_value=False)
    def test_no_auto_start_without_paths(self, _: object) -> None:
        client = ModelClient(local_url="", hf_token="")
        client.server_binary = ""
        client.model_path = ""
        client._ensure_local_server()
        self.assertEqual(client.local_url, "")

    def test_groq_defaults_are_loaded(self) -> None:
        client = ModelClient(local_url="", hf_token="")
        self.assertEqual(client.groq_model, DEFAULT_GROQ_MODEL_NAME)
        self.assertEqual(GROQ_BASE_URL, "https://api.groq.com/openai/v1")


class ResponseValidationTests(unittest.TestCase):
    def test_valid_structured_response_passes(self) -> None:
        rule_result = apply_rules("I feel nervous meeting new people", "emotional_expression")
        response = (
            "It makes sense to feel nervous in that situation. "
            "Start with one simple opener about the shared setting. "
            "What kind of introduction do you want to practice first?"
        )
        self.assertTrue(response_is_valid(response, rule_result))

    def test_missing_follow_up_question_fails(self) -> None:
        rule_result = apply_rules("I feel nervous meeting new people", "emotional_expression")
        response = "It makes sense to feel nervous. Start with one simple opener about the setting."
        self.assertFalse(response_is_valid(response, rule_result))


class RetrievalFormattingTests(unittest.TestCase):
    def test_retrieved_context_formatting(self) -> None:
        documents = [
            KnowledgeDocument(
                id="doc1",
                type="coaching_snippet",
                scenario="joining_group",
                intent="general_interaction",
                skill="follow_ups",
                content="Use one short comment tied to the topic before asking a light question.",
                source="test",
                tags=["group"],
            )
        ]
        context = format_retrieved_context(documents)
        self.assertIn("scenario=joining_group", context)
        self.assertIn("Use one short comment tied to the topic", context)

    def test_startup_check_disables_retrieval_when_files_are_missing(self) -> None:
        kb = FaissKnowledgeBase(
            index_path="C:/missing/index.faiss",
            metadata_path="C:/missing/metadata.json",
        )
        self.assertFalse(kb.startup_check())
        self.assertIn("missing", kb.disabled_reason.lower())


class IngestionUtilityTests(unittest.TestCase):
    def test_flatten_json_text_prefers_known_text_fields(self) -> None:
        payload = {"text": "First line", "metadata": {"ignored": "value"}}
        self.assertEqual(flatten_json_text(payload), "First line")

    def test_clean_text_normalizes_whitespace(self) -> None:
        self.assertEqual(clean_text("hello \n there\tfriend"), "hello there friend")

    def test_chunk_text_splits_large_input(self) -> None:
        text = "a" * 600
        chunks = chunk_text(text, chunk_size=300, chunk_overlap=50)
        self.assertGreaterEqual(len(chunks), 2)


if __name__ == "__main__":
    unittest.main()
