from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ChatSession:
    selections: dict[str, str]
    system_prompt: str
    nsfw_level: str = "medium"
    max_tokens: int = 700
    turn_count: int = 0
    story_log: list[str] = field(default_factory=list)

    def snapshot(self) -> dict:
        return {
            "selections": dict(self.selections),
            "system_prompt": self.system_prompt,
            "nsfw_level": self.nsfw_level,
            "turn_count": self.turn_count,
            "story_log": list(self.story_log),
        }

    def restore(self, data: dict) -> None:
        self.selections = dict(data["selections"])
        self.system_prompt = data["system_prompt"]
        self.nsfw_level = data.get("nsfw_level", "medium")
        self.turn_count = data["turn_count"]
        self.story_log = list(data.get("story_log", []))
