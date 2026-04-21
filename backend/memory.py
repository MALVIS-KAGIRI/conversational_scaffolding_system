from __future__ import annotations

from collections import deque
from threading import Lock
from typing import Deque, Dict, List


class SlidingWindowMemory:
    """Stores a short interaction history using a fixed-size sliding window."""

    def __init__(self, max_items: int = 5) -> None:
        self.max_items = max_items
        self._items: Deque[Dict[str, str]] = deque(maxlen=max_items)
        self._lock = Lock()

    def add(self, user_input: str, response: str) -> None:
        with self._lock:
            self._items.append({"user": user_input, "assistant": response})

    def history(self) -> List[Dict[str, str]]:
        with self._lock:
            return list(self._items)

    def as_text(self) -> str:
        items = self.history()
        if not items:
            return "No prior interactions."

        formatted = []
        for idx, item in enumerate(items, start=1):
            formatted.append(
                f"Interaction {idx}\n"
                f"User: {item['user']}\n"
                f"Guide: {item['assistant']}"
            )
        return "\n\n".join(formatted)
