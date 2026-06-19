"""Session-level conversation memory.

Stores recent conversation history in-process with a configurable window size.
Used to provide context to the agent across multi-turn conversations.
"""

import threading
import time
from collections import OrderedDict
from typing import Optional


class SessionMemory:
    """In-process session memory with per-user conversation history.

    Each session stores up to ``max_turns`` message pairs (user + assistant).
    Oldest turns are evicted when the limit is reached.
    """

    def __init__(self, max_turns: int = 10, ttl_seconds: int = 3600):
        self._max_turns = max_turns
        self._ttl = ttl_seconds
        self._sessions: dict[str, OrderedDict] = {}
        self._lock = threading.Lock()

    def start_session(self, session_id: str, user_id: str = "default"):
        with self._lock:
            self._sessions[session_id] = OrderedDict()
            self._sessions[session_id]["user_id"] = user_id
            self._sessions[session_id]["turns"] = []
            self._sessions[session_id]["created"] = time.time()
            self._sessions[session_id]["accessed"] = time.time()

    def add_turn(self, session_id: str, user_msg: str, assistant_msg: str):
        with self._lock:
            if session_id not in self._sessions:
                self.start_session(session_id)
            session = self._sessions[session_id]
            session["turns"].append({"user": user_msg, "assistant": assistant_msg})
            session["accessed"] = time.time()
            # Evict oldest if over limit
            while len(session["turns"]) > self._max_turns:
                session["turns"].pop(0)

    def get_context(self, session_id: str, max_turns: int = 5) -> list[dict]:
        with self._lock:
            if session_id not in self._sessions:
                return []
            turns = self._sessions[session_id]["turns"]
            return turns[-max_turns:] if max_turns > 0 else turns

    def get_user_id(self, session_id: str) -> str:
        with self._lock:
            session = self._sessions.get(session_id, {})
            return session.get("user_id", "default")

    def clear_session(self, session_id: str):
        with self._lock:
            self._sessions.pop(session_id, None)

    def cleanup_expired(self):
        cutoff = time.time() - self._ttl
        with self._lock:
            expired = [
                sid for sid, s in self._sessions.items()
                if s.get("accessed", 0) < cutoff
            ]
            for sid in expired:
                del self._sessions[sid]

    def active_sessions(self) -> int:
        with self._lock:
            return len(self._sessions)


# Simple preference extraction keywords
_PREFERENCE_PATTERNS = [
    ("喜欢", "likes"),
    ("不喜欢", "dislikes"),
    ("讨厌", "dislikes"),
    ("不穿", "dislikes"),
    ("爱穿", "likes"),
    ("适合", "style"),
]


def extract_preferences_from_message(message: str, reply: str) -> dict:
    """Extract basic preference signals from conversation.

    Returns a dict that can be passed to UserProfile.update_preferences().
    """
    feedback = {}
    combined = f"{message} {reply}"

    # Check for color preferences
    colors = ["红色", "蓝色", "绿色", "黄色", "黑色", "白色", "灰色", "粉色",
              "紫色", "棕色", "橙色", "藏青", "卡其", "米色", "驼色"]
    for color in colors:
        if color in combined:
            if f"喜欢{color}" in combined or f"爱穿{color}" in combined:
                if "favorite_colors" not in feedback:
                    feedback["favorite_colors"] = []
                feedback["favorite_colors"].append(color)
            elif f"不喜欢{color}" in combined or f"讨厌{color}" in combined:
                if "avoid_colors" not in feedback:
                    feedback["avoid_colors"] = []
                feedback["avoid_colors"].append(color)

    # Check for occasion preferences
    occasions = ["面试", "约会", "通勤", "运动", "晚宴", "日常", "出游", "婚礼"]
    for occ in occasions:
        if occ in combined:
            if "occasions" not in feedback:
                feedback["occasions"] = []
            if occ not in feedback["occasions"]:
                feedback["occasions"].append(occ)

    # Check for style preferences
    styles = ["简约", "优雅", "休闲", "街头", "文艺", "商务", "运动风", "甜美", "气场"]
    for s in styles:
        if s in combined:
            if "style" not in feedback:
                feedback["style"] = []
            if s not in feedback["style"]:
                feedback["style"].append(s)

    return feedback
