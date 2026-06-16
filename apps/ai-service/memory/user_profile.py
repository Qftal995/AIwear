import json
import os
import threading


class UserProfile:
    def __init__(self):
        self._profiles: dict = {}
        self._lock = threading.Lock()
        self._file_path = os.getenv(
            "USER_PROFILES_PATH",
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "user_profiles.json"),
        )
        self._file_path = os.path.abspath(self._file_path)
        self._load()

    def _load(self):
        try:
            if os.path.isfile(self._file_path):
                with open(self._file_path, encoding="utf-8") as f:
                    self._profiles = json.load(f)
        except Exception:
            self._profiles = {}

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self._file_path), exist_ok=True)
            with open(self._file_path, "w", encoding="utf-8") as f:
                json.dump(self._profiles, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def get_preferences(self, user_id: str) -> dict:
        with self._lock:
            if user_id not in self._profiles:
                return {"style": [], "occasions": [], "favorites": []}
            profile = self._profiles[user_id]
            return profile.get("preferences", {"style": [], "occasions": [], "favorites": []})

    def update_preferences(self, user_id: str, feedback: dict) -> None:
        with self._lock:
            if user_id not in self._profiles:
                self._profiles[user_id] = {
                    "preferences": {"style": [], "occasions": [], "favorites": []},
                    "history": [],
                }
            prefs = self._profiles[user_id]["preferences"]
            for key, value in feedback.items():
                if key not in prefs:
                    prefs[key] = value
                elif isinstance(value, list):
                    existing = set(prefs[key])
                    for item in value:
                        existing.add(item)
                    prefs[key] = list(existing)
                else:
                    prefs[key] = value
            self._profiles[user_id]["history"].append(feedback)
            self._save()

    def get_history(self, user_id: str, limit: int = 10) -> list:
        with self._lock:
            if user_id not in self._profiles:
                return []
            return self._profiles[user_id]["history"][-limit:]

    def add_favorite(self, user_id: str, item_id: str) -> None:
        with self._lock:
            prefs = self.get_preferences(user_id)
            if item_id not in prefs["favorites"]:
                prefs["favorites"].append(item_id)
                self._profiles[user_id]["preferences"] = prefs
                self._save()

    def remove_favorite(self, user_id: str, item_id: str) -> None:
        with self._lock:
            prefs = self.get_preferences(user_id)
            if item_id in prefs["favorites"]:
                prefs["favorites"].remove(item_id)
                self._profiles[user_id]["preferences"] = prefs
                self._save()

    def clear_profile(self, user_id: str) -> None:
        with self._lock:
            if user_id in self._profiles:
                del self._profiles[user_id]
                self._save()
