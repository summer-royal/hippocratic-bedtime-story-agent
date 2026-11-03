"""Feedback guard: decides whether a requested change can be applied to the story.

Order of checks:
1. Empty feedback is declined without a model call.
2. A crisis phrase escalates without a model call (same list as the request guard).
3. The model classifies the feedback.
4. Code rules override the model for the most serious flags.
"""

from dataclasses import dataclass
from enum import Enum

from guard import has_crisis_phrase
from llm import call_model
from parsing import parse_json_object
from prompts.feedback import build_feedback_system_prompt
from prompts.guard import RISK_FLAG_DESCRIPTIONS

FEEDBACK_MAX_TOKENS = 2000
FEEDBACK_SYSTEM_PROMPT = build_feedback_system_prompt(RISK_FLAG_DESCRIPTIONS)
RISK_FLAGS = tuple(RISK_FLAG_DESCRIPTIONS)

# Flags that always escalate, whatever route the model chose.
ESCALATE_FLAGS = frozenset({"self_harm", "abuse"})
# Flags that always decline a change, even when the model chose apply or soften.
DECLINE_FLAGS = frozenset(
    {"violence", "sexual_content", "jailbreak_attempt", "personal_info", "medical_or_drugs", "real_person_or_brand"}
)


class FeedbackRoute(str, Enum):
    """What the app should do with one piece of feedback."""

    APPLY = "apply"
    SOFTEN = "soften"
    DECLINE = "decline"
    ESCALATE = "escalate"


@dataclass(frozen=True)
class FeedbackResult:
    """The feedback guard's decision about one change request."""

    route: FeedbackRoute
    risk_flags: tuple[str, ...]
    reason: str


def check_feedback(feedback: str) -> FeedbackResult:
    """Decide whether the app can make the requested change.

    Args:
        feedback: The change the parent or child asked for.

    Returns:
        A FeedbackResult. A reply the guard cannot read is declined, not guessed at.

    Raises:
        RuntimeError: If the model call itself fails (see llm.call_model).
    """
    text = feedback.strip()
    if not text:
        return FeedbackResult(FeedbackRoute.DECLINE, (), "Empty feedback.")
    if has_crisis_phrase(text):
        return FeedbackResult(FeedbackRoute.ESCALATE, (), "Matched a crisis phrase before the model ran.")

    reply = call_model(f"<feedback>\n{text}\n</feedback>", system=FEEDBACK_SYSTEM_PROMPT, max_tokens=FEEDBACK_MAX_TOKENS)
    try:
        data = parse_json_object(reply)
    except ValueError as error:
        return FeedbackResult(FeedbackRoute.DECLINE, (), f"Failing closed: {error}")

    route = _read_route(data.get("route"))
    flags = tuple(flag for flag in _read_flags(data.get("risk_flags")) if flag in RISK_FLAGS)
    reason = data.get("reason") if isinstance(data.get("reason"), str) else ""
    if route is None:
        return FeedbackResult(FeedbackRoute.DECLINE, flags, "Failing closed: unknown route.")
    if set(flags) & ESCALATE_FLAGS:
        return FeedbackResult(FeedbackRoute.ESCALATE, flags, reason)
    if set(flags) & DECLINE_FLAGS:
        return FeedbackResult(FeedbackRoute.DECLINE, flags, reason)
    return FeedbackResult(route, flags, reason)


def _read_route(value: object) -> FeedbackRoute | None:
    try:
        return FeedbackRoute(value)
    except ValueError:
        return None


def _read_flags(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [flag for flag in value if isinstance(flag, str)]
