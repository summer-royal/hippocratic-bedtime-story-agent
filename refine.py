"""Refine: applies one piece of feedback to a story, and keeps the new version only if it is at least as good.

Feedback goes through its own guard first. An applied change is re-planned
from the previous outline, written, and then reviewed and judged like any
other draft. The new story replaces the old one only if it passes review and
its judge score is at least as high. Otherwise the old story stays.
"""

from dataclasses import dataclass, replace

from feedback import FeedbackRoute, check_feedback
from guard import GuardResult, Route
from outline import Outline, plan_outline
from revision import ImprovedStory, improve_story
from storyteller import write_story

MAX_FEEDBACK_ROUNDS = 3


@dataclass(frozen=True)
class RefineOutcome:
    """What happened to one piece of feedback.

    action is one of "updated", "kept_previous", "declined", or "escalate".
    attempt is the new story that was generated, or None if none was.
    """

    action: str
    outline: Outline
    improved: ImprovedStory
    attempt: ImprovedStory | None


def apply_feedback(
    current_outline: Outline,
    current: ImprovedStory,
    guard: GuardResult,
    request: str,
    feedback: str,
) -> RefineOutcome:
    """Apply one change to the current story, or explain why it cannot be applied.

    Args:
        current_outline: The outline of the story as it is now.
        current: The story as it is now, with its judge score.
        guard: The guard's decision for the original request.
        request: The text the parent or child typed originally.
        feedback: The change the parent or child asked for.

    Returns:
        A RefineOutcome. The current story is kept unless the new one passes review
        and scores at least as high.

    Raises:
        RuntimeError: If a model call fails (see llm.call_model).
        ValueError: If the planner or storyteller returns an unusable answer.
    """
    decision = check_feedback(feedback)
    if decision.route is FeedbackRoute.ESCALATE:
        return RefineOutcome("escalate", current_outline, current, None)
    if decision.route is FeedbackRoute.DECLINE:
        return RefineOutcome("declined", current_outline, current, None)

    planner_guard = replace(guard, route=Route.GENTLE) if decision.route is FeedbackRoute.SOFTEN else guard
    new_outline = plan_outline(request, planner_guard, previous=current_outline, feedback=feedback)
    category = guard.category or "calm_and_cozy"
    attempt = improve_story(
        write_story(new_outline, category), new_outline, planner_guard, request, feedback=feedback
    )

    if attempt.story is not None and (attempt.overall or 0.0) >= (current.overall or 0.0):
        return RefineOutcome("updated", new_outline, attempt, attempt)
    return RefineOutcome("kept_previous", current_outline, current, attempt)
