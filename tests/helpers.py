"""Shared fixtures for the unit tests. Nothing here calls the model."""

import json

from outline import Beat, Outline
from prompts.planner import BEAT_NAMES
from prompts.judge import CRITERIA

CLOSING = "Goodnight, little one, sleep tight."

# 34 repeated sentences of 10 words, plus the closing line: 311 words, short sentences, passes the code gate.
GOOD_STORY = ("The little bunny hopped through the soft green meadow. " * 34) + CLOSING


def make_outline(title: str = "Test Story") -> Outline:
    beats = tuple(Beat(name=name, goal=f"goal for {name}", word_target=70, safety_intent="stay calm") for name in BEAT_NAMES)
    return Outline(title=title, characters=("Bunny",), setting="A meadow", beats=beats, closing_line=CLOSING)


def outline_reply(title: str = "Test Story") -> str:
    """A planner reply that parses into make_outline(title)."""
    return json.dumps(
        {
            "title": title,
            "characters": ["Bunny"],
            "setting": "A meadow",
            "beats": [
                {"name": name, "goal": f"goal for {name}", "word_target": 70, "safety_intent": "stay calm"}
                for name in BEAT_NAMES
            ],
            "closing_line": CLOSING,
        }
    )


def judge_reply(score: int = 9, notes: list[str] | None = None) -> str:
    """A judge reply with every criterion set to the same score."""
    return json.dumps({"scores": {name: score for name in CRITERIA}, "revision_notes": notes or []})


def safety_reply(safe: bool = True, issues: list[dict] | None = None) -> str:
    return json.dumps({"safe": safe, "issues": issues or []})
