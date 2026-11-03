"""Request guard: decides whether and how the app should answer a story request.

Order of checks:
1. Empty input is declined without a model call.
2. A short list of crisis phrases escalates without a model call.
3. The model classifies the request.
4. Code rules override the model for the most serious flags.
"""

import re
from dataclasses import dataclass
from enum import Enum

from llm import call_model
from parsing import parse_json_object
from prompts.guard import CATEGORY_DESCRIPTIONS, GUARD_SYSTEM_PROMPT, RISK_FLAG_DESCRIPTIONS

CATEGORIES = tuple(CATEGORY_DESCRIPTIONS)
RISK_FLAGS = tuple(RISK_FLAG_DESCRIPTIONS)
GUARD_MAX_TOKENS = 2000

# A deterministic safety net that runs before the model. Matching is
# case-insensitive and on whole phrases. The list is short on purpose: it
# catches clear disclosures, and the model handles everything else.
CRISIS_PHRASES = (
    "kill myself",
    "want to die",
    "end my life",
    "hurt myself",
    "hits me",
    "hurts me",
    "touched me",
    "touches me",
)

# Flags that always escalate, whatever route the model chose.
ESCALATE_FLAGS = frozenset({"self_harm", "abuse"})
# Flags that turn a story or gentle route into a decline.
DECLINE_FLAGS = frozenset({"sexual_content", "jailbreak_attempt"})


class Route(str, Enum):
    """What the app should do with a request."""

    STORY = "story"
    GENTLE = "gentle"
    DECLINE = "decline"
    ESCALATE = "escalate"


@dataclass(frozen=True)
class GuardResult:
    """The guard's decision about one request."""

    route: Route
    category: str | None
    risk_flags: tuple[str, ...]
    reason: str


def check_request(request: str) -> GuardResult:
    """Decide how the app should handle a story request.

    Args:
        request: The text the parent or child typed.

    Returns:
        A GuardResult. A reply the guard cannot read is declined, not guessed at.

    Raises:
        RuntimeError: If the model call itself fails (see llm.call_model).
    """
    text = request.strip()
    if not text:
        return GuardResult(Route.DECLINE, None, (), "Empty request.")
    if has_crisis_phrase(text):
        return GuardResult(Route.ESCALATE, None, (), "Matched a crisis phrase before the model ran.")

    reply = call_model(text, system=GUARD_SYSTEM_PROMPT, max_tokens=GUARD_MAX_TOKENS)
    try:
        data = parse_json_object(reply)
    except ValueError as error:
        return GuardResult(Route.DECLINE, None, (), f"Failing closed: {error}")
    return _interpret_reply(data)


def has_crisis_phrase(text: str) -> bool:
    """Return True if the text contains one of the crisis phrases, as whole words."""
    lowered = text.lower()
    return any(re.search(rf"\b{re.escape(phrase)}\b", lowered) for phrase in CRISIS_PHRASES)


def _interpret_reply(data: dict) -> GuardResult:
    """Validate the model's JSON and apply the code rules on top of it.

    Escalation flags are checked before the route and the category, so a
    malformed category cannot turn a serious-risk flag into a decline.
    Missing or malformed flags are never read as "no risk".
    """
    reason = data.get("reason") if isinstance(data.get("reason"), str) else ""
    route = _read_route(data.get("route"))
    raw_flags = _read_flags(data.get("risk_flags"))
    if raw_flags is None:
        if route is Route.ESCALATE:
            return GuardResult(Route.ESCALATE, None, (), "Escalated; the risk flags were malformed.")
        return GuardResult(Route.DECLINE, None, (), "Failing closed: risk_flags missing or malformed.")

    flags = tuple(flag for flag in raw_flags if flag in RISK_FLAGS)
    if set(flags) & ESCALATE_FLAGS:
        return GuardResult(Route.ESCALATE, None, flags, reason)
    if route is None:
        return GuardResult(Route.DECLINE, None, flags, "Failing closed: unknown route.")

    category = data.get("category")
    if route in (Route.STORY, Route.GENTLE) and category not in CATEGORIES:
        return GuardResult(Route.DECLINE, None, flags, "Failing closed: missing or unknown category.")
    if set(flags) & DECLINE_FLAGS and route in (Route.STORY, Route.GENTLE):
        route = Route.DECLINE
    if route in (Route.DECLINE, Route.ESCALATE):
        category = None
    return GuardResult(route, category, flags, reason)


def _read_route(value: object) -> Route | None:
    try:
        return Route(value)
    except ValueError:
        return None


def _read_flags(value: object) -> tuple[str, ...] | None:
    """Return the flag names, or None when the field is missing or is not a list of text."""
    if not isinstance(value, list) or not all(isinstance(flag, str) for flag in value):
        return None
    return tuple(value)
