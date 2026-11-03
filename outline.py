"""Story outline: the planner's output, parsed and checked before anything is written.

The outline is the contract for the rest of the pipeline. The storyteller writes
from it, and the judge will check the story against it.
"""

import json
from dataclasses import asdict, dataclass

from guard import GuardResult
from llm import call_model
from parsing import parse_json_object
from prompts.planner import BEAT_NAMES, PLANNER_SYSTEM_PROMPT, build_planner_prompt

PLANNER_MAX_TOKENS = 4000
MIN_BEAT_WORDS = 50
MAX_BEAT_WORDS = 90


@dataclass(frozen=True)
class Beat:
    """One part of the story, such as the setup or the calm wind-down."""

    name: str
    goal: str
    word_target: int
    safety_intent: str


@dataclass(frozen=True)
class Outline:
    """A five-beat plan for one bedtime story."""

    title: str
    characters: tuple[str, ...]
    setting: str
    beats: tuple[Beat, ...]
    closing_line: str

    def to_json(self) -> str:
        """Serialize the outline for the storyteller's prompt."""
        return json.dumps(asdict(self), indent=2)


def plan_outline(
    request: str,
    guard: GuardResult,
    previous: "Outline | None" = None,
    feedback: str | None = None,
) -> Outline:
    """Ask the planner for an outline and validate the reply.

    Args:
        request: The text the parent or child typed.
        guard: The guard's decision. Its category and flags shape the outline.
        previous: The outline of the story being changed, when revising.
        feedback: The change the parent or child asked for, when revising.

    Returns:
        A validated Outline.

    Raises:
        RuntimeError: If the model call fails (see llm.call_model).
        ValueError: If the planner's reply is not a usable outline.
    """
    prompt = build_planner_prompt(
        request,
        guard.category or "calm_and_cozy",
        guard.route.value,
        guard.risk_flags,
        previous.to_json() if previous else None,
        feedback,
    )
    reply = call_model(prompt, system=PLANNER_SYSTEM_PROMPT, max_tokens=PLANNER_MAX_TOKENS)
    return parse_outline(reply)


def parse_outline(reply: str) -> Outline:
    """Parse the planner's reply and check that it follows the outline rules.

    Raises:
        ValueError: If the JSON is missing, a field is wrong, or the beats are
            out of order or out of range.
    """
    data = parse_json_object(reply)
    beats = _read_beats(data.get("beats"))
    return Outline(
        title=_read_text(data, "title"),
        characters=_read_characters(data.get("characters")),
        setting=_read_text(data, "setting"),
        beats=beats,
        closing_line=_read_text(data, "closing_line"),
    )


def _read_text(data: dict, key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Outline field '{key}' is missing or empty.")
    return value.strip()


def _read_characters(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not 1 <= len(value) <= 3:
        raise ValueError("Outline needs between one and three characters.")
    if not all(isinstance(name, str) and name.strip() for name in value):
        raise ValueError("Outline characters must be non-empty text.")
    return tuple(name.strip() for name in value)


def _read_beats(value: object) -> tuple[Beat, ...]:
    if not isinstance(value, list) or len(value) != len(BEAT_NAMES):
        raise ValueError(f"Outline needs exactly {len(BEAT_NAMES)} beats.")
    beats = []
    for expected_name, item in zip(BEAT_NAMES, value):
        if not isinstance(item, dict) or item.get("name") != expected_name:
            raise ValueError(f"Beats must appear in order; expected '{expected_name}'.")
        word_target = item.get("word_target")
        if not isinstance(word_target, int) or isinstance(word_target, bool):
            raise ValueError(f"Beat '{expected_name}' needs a whole-number word target.")
        if not MIN_BEAT_WORDS <= word_target <= MAX_BEAT_WORDS:
            raise ValueError(f"Beat '{expected_name}' word target {word_target} is out of range.")
        beats.append(
            Beat(
                name=expected_name,
                goal=_read_text(item, "goal"),
                word_target=word_target,
                safety_intent=_read_text(item, "safety_intent"),
            )
        )
    return tuple(beats)
