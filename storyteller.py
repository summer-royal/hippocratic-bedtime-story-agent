"""Storyteller: writes the story from the planner's outline."""

from llm import call_model
from outline import Outline
from prompts.storyteller import (
    STORYTELLER_SYSTEM_PROMPT,
    build_revision_prompt,
    build_storyteller_prompt,
)

STORY_MAX_TOKENS = 6000


def write_story(outline: Outline, category: str) -> str:
    """Write the story body that follows the outline.

    Args:
        outline: The validated plan from outline.plan_outline.
        category: The guard's category, which sets the tone.

    Returns:
        The story text, without a title.

    Raises:
        RuntimeError: If the model call fails (see llm.call_model).
        ValueError: If the model returns an empty story.
    """
    return _ask_storyteller(build_storyteller_prompt(outline.to_json(), category))


def revise_story(previous_story: str, outline: Outline, category: str, notes: list[str]) -> str:
    """Revise a story using the review problems and judge notes.

    Raises:
        RuntimeError: If the model call fails (see llm.call_model).
        ValueError: If the model returns an empty story.
    """
    prompt = build_revision_prompt(previous_story, outline.to_json(), category, notes)
    return _ask_storyteller(prompt)


def _ask_storyteller(prompt: str) -> str:
    story = call_model(prompt, system=STORYTELLER_SYSTEM_PROMPT, max_tokens=STORY_MAX_TOKENS).strip()
    if not story:
        raise ValueError("The storyteller returned an empty story.")
    return story
