class UserProfile:
    def __init__(self):
        self._profiles: dict = {}

    def get_preferences(self, user_id: str) -> dict:
        if user_id not in self._profiles:
            return {"style": [], "occasions": [], "favorites": []}
        profile = self._profiles[user_id]
        return profile.get("preferences", {"style": [], "occasions": [], "favorites": []})

    def update_preferences(self, user_id: str, feedback: dict) -> None:
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

    def get_history(self, user_id: str, limit: int = 10) -> list:
        if user_id not in self._profiles:
            return []
        return self._profiles[user_id]["history"][-limit:]

    def add_favorite(self, user_id: str, item_id: str) -> None:
        prefs = self.get_preferences(user_id)
        if item_id not in prefs["favorites"]:
            prefs["favorites"].append(item_id)
            self._profiles[user_id]["preferences"] = prefs

    def remove_favorite(self, user_id: str, item_id: str) -> None:
        prefs = self.get_preferences(user_id)
        if item_id in prefs["favorites"]:
            prefs["favorites"].remove(item_id)
            self._profiles[user_id]["preferences"] = prefs

    def clear_profile(self, user_id: str) -> None:
        if user_id in self._profiles:
            del self._profiles[user_id]