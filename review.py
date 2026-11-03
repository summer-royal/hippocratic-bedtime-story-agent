"""Review: runs the code gate and the safety reviewer on a finished story and its title.

A story passes only if both checks pass. The title is shown to the child too,
so it is checked the same way. The reviewer is strict: any issue it lists fails
the story, and a malformed reply fails it too.
"""

import re
from dataclasses import dataclass

from gate import BANNED_WORDS, gate_problems
from guard import GuardResult
from llm import call_model
from outline import Outline
from parsing import parse_json_object
from prompts.safety import SAFETY_CATEGORIES, SAFETY_REVIEWER_SYSTEM_PROMPT, build_safety_prompt

SAFETY_MAX_TOKENS = 3000


@dataclass(frozen=True)
class Review:
    """The result of reviewing one story."""

    passed: bool
    problems: tuple[str, ...]


def review_story(story: str, outline: Outline, guard: GuardResult, request: str) -> Review:
    """Run the code gate and the safety reviewer on the story and its title.

    Args:
        story: The storyteller's text.
        outline: The outline the story was written from. Its title is checked too.
        guard: The guard's decision for the request.
        request: The text the parent or child typed.

    Returns:
        A Review. It passes only when there are no problems from any check.

    Raises:
        RuntimeError: If the safety reviewer's model call fails (see llm.call_model).
    """
    problems = gate_problems(story, outline.closing_line, guard.risk_flags, request)
    problems += _title_problems(outline.title)
    problems += review_safety(story, outline.title)
    return Review(passed=not problems, problems=tuple(problems))


def _title_problems(title: str) -> list[str]:
    lowered = title.lower()
    banned = sorted(word for word in BANNED_WORDS if re.search(rf"\b{word}\b", lowered))
    return [f"The title contains banned words: {', '.join(banned)}."] if banned else []


def review_safety(story: str, title: str = "") -> list[str]:
    """Ask the safety reviewer for issues in the title and the story.

    Returns:
        A list of problems. An empty list means the reviewer found nothing.
        An unreadable or malformed reply is a problem, so the story fails closed.
    """
    reply = call_model(
        build_safety_prompt(story, title),
        system=SAFETY_REVIEWER_SYSTEM_PROMPT,
        max_tokens=SAFETY_MAX_TOKENS,
    )
    try:
        data = parse_json_object(reply)
    except ValueError:
        return ["Safety reviewer reply was unreadable, so the story fails closed."]

    safe = data.get("safe")
    issues = data.get("issues")
    if not isinstance(safe, bool) or not isinstance(issues, list):
        return ["Safety reviewer reply had the wrong shape, so the story fails closed."]
    if not all(isinstance(item, dict) for item in issues):
        return ["Safety reviewer listed an issue in an unreadable form, so the story fails closed."]

    problems = [_describe_issue(item) for item in issues]
    if not safe and not problems:
        problems.append("Safety reviewer marked the story unsafe without giving a reason.")
    return problems


def _describe_issue(item: dict) -> str:
    category = item.get("category") if item.get("category") in SAFETY_CATEGORIES else "other"
    reason = item.get("reason") if isinstance(item.get("reason"), str) else "No reason given."
    quote = item.get("quote") if isinstance(item.get("quote"), str) else ""
    return f'{category}: {reason} Quote: "{quote}"'
