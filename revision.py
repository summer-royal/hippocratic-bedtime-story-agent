"""Revision loop: review and judge each draft, revise with the notes, and keep the best draft.

Each round reviews the current draft with the code gate and the safety reviewer.
Only a draft that passes review is judged for quality. A judged score of
PASS_OVERALL or higher ends the loop. Otherwise the review problems and judge
notes go back to the storyteller, for at most MAX_REVISIONS revisions.
"""

import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from guard import GuardResult
from judge import judge_story
from outline import Outline
from review import review_story
from storyteller import revise_story

PASS_OVERALL = 8.0
MAX_REVISIONS = 2
RUNS_DIR = Path(__file__).resolve().parent / "runs"


@dataclass(frozen=True)
class RoundRecord:
    """What happened to one draft: the review, the judge, and the notes."""

    round_number: int
    draft: str
    review_problems: tuple[str, ...]
    scores: dict[str, int] | None
    overall: float | None
    judge_notes: tuple[str, ...]


@dataclass(frozen=True)
class ImprovedStory:
    """The best draft that passed review, or None if no draft passed."""

    story: str | None
    overall: float | None
    rounds: tuple[RoundRecord, ...]


def improve_story(story: str, outline: Outline, guard: GuardResult, request: str) -> ImprovedStory:
    """Review, judge, and revise a draft until it is good enough or the rounds run out.

    Args:
        story: The first draft from the storyteller.
        outline: The outline the draft was written from.
        guard: The guard's decision for the request.
        request: The text the parent or child typed.

    Returns:
        The highest-scoring draft that passed review, with a record of every round.

    Raises:
        RuntimeError: If a model call fails (see llm.call_model).
        ValueError: If the storyteller returns an empty revision.
    """
    category = guard.category or "calm_and_cozy"
    draft = story
    rounds: list[RoundRecord] = []
    best_story: str | None = None
    best_overall: float | None = None

    for round_number in range(MAX_REVISIONS + 1):
        review = review_story(draft, outline, guard, request)
        judgement = None
        if review.passed:
            try:
                judgement = judge_story(draft, outline, request, category, guard.risk_flags)
            except ValueError as error:
                # The judge checks quality only. A draft that passed review is kept even when the judge fails.
                print(f"Developer log: judge unavailable this round: {error}", file=sys.stderr)

        record = RoundRecord(
            round_number=round_number,
            draft=draft,
            review_problems=review.problems,
            scores=judgement.scores if judgement else None,
            overall=judgement.overall if judgement else None,
            judge_notes=judgement.notes if judgement else (),
        )
        rounds.append(record)
        _log_round(record, review.passed)

        if review.passed:
            overall = record.overall
            if best_story is None or (overall is not None and (best_overall is None or overall > best_overall)):
                best_story, best_overall = draft, overall
            # Stop when the draft is good enough, or when there is nothing actionable to revise.
            if overall is None or overall >= PASS_OVERALL or not record.judge_notes:
                break
        if round_number == MAX_REVISIONS:
            break

        notes = list(review.problems) + list(record.judge_notes)
        draft = revise_story(draft, outline, category, notes)

    return ImprovedStory(story=best_story, overall=best_overall, rounds=tuple(rounds))


def save_run(request: str, category: str, improved: ImprovedStory) -> Path:
    """Write every round to runs/ as JSON, so a run can be inspected later.

    The file holds the child's request and every draft, so runs/ stays gitignored.
    """
    RUNS_DIR.mkdir(exist_ok=True)
    path = RUNS_DIR / f"{datetime.now():%Y%m%d-%H%M%S-%f}.json"
    record = {
        "request": request,
        "category": category,
        "passed": improved.story is not None,
        "final_overall": improved.overall,
        "rounds": [asdict(round_record) for round_record in improved.rounds],
    }
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _log_round(record: RoundRecord, passed_review: bool) -> None:
    """Print one round's scores and problems to stderr. The child never sees this."""
    print(f"Developer log: round {record.round_number}: review passed={passed_review}", file=sys.stderr)
    for problem in record.review_problems:
        print(f"Developer log:   problem: {problem}", file=sys.stderr)
    if record.scores is not None:
        print(f"Developer log:   overall {record.overall} scores {record.scores}", file=sys.stderr)
