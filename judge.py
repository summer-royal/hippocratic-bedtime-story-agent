"""Quality judge: scores a story and returns specific revision notes."""

from dataclasses import dataclass
from statistics import mean

from llm import call_model
from outline import Outline
from parsing import parse_json_object
from prompts.judge import CRITERIA, JUDGE_SYSTEM_PROMPT, build_judge_prompt

JUDGE_MAX_TOKENS = 3000
MAX_NOTES = 5
JUDGE_ATTEMPTS = 2


@dataclass(frozen=True)
class Judgement:
    """The judge's scores and notes for one story."""

    scores: dict[str, int]
    overall: float
    notes: tuple[str, ...]


def judge_story(
    story: str,
    outline: Outline,
    request: str,
    category: str,
    risk_flags: tuple[str, ...] = (),
    feedback: str | None = None,
) -> Judgement:
    """Score a story on quality and return revision notes.

    The overall score is the mean of the criteria, computed here in code so
    the model never sets it directly. When a change was requested, the judge
    also sees that change and scores whether the story makes it.

    Raises:
        RuntimeError: If the model call fails (see llm.call_model).
        ValueError: If the judge's reply cannot be read, even after one retry.
    """
    prompt = build_judge_prompt(request, category, risk_flags, outline.to_json(), story, feedback)
    last_error: ValueError | None = None
    for _ in range(JUDGE_ATTEMPTS):
        reply = call_model(prompt, system=JUDGE_SYSTEM_PROMPT, max_tokens=JUDGE_MAX_TOKENS)
        try:
            return _parse_judgement(reply)
        except ValueError as error:
            last_error = error
    raise ValueError(f"Judge reply could not be read after a retry: {last_error}")


def _parse_judgement(reply: str) -> Judgement:
    data = parse_json_object(reply)
    raw_scores = data.get("scores")
    if not isinstance(raw_scores, dict):
        raise ValueError("Judge reply has no scores object.")

    scores = {}
    for name in CRITERIA:
        value = raw_scores.get(name)
        if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 10:
            raise ValueError(f"Judge score for '{name}' is missing or out of range.")
        scores[name] = value

    raw_notes = data.get("revision_notes")
    if not isinstance(raw_notes, list):
        raise ValueError("Judge reply has no revision_notes list.")
    notes = tuple(note.strip() for note in raw_notes if isinstance(note, str) and note.strip())[:MAX_NOTES]
    return Judgement(scores=scores, overall=round(mean(scores.values()), 1), notes=notes)
