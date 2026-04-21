from __future__ import annotations

import unittest
from unittest.mock import patch

from backend.intent import classify_intent
from backend.memory import SlidingWindowMemory
from backend.model import ModelClient, _port_from_url
from backend.rules import apply_rules


class IntentTests(unittest.TestCase):
    def test_greeting_intent(self) -> None:
        self.assertEqual(classify_intent("hello there"), "greeting")

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

    def test_out_of_scope_blocked(self) -> None:
        result = apply_rules("Can you give medical advice?", "general_interaction")
        self.assertTrue(result.blocked)
        self.assertEqual(result.reason, "out_of_scope")


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


if __name__ == "__main__":
    unittest.main()
