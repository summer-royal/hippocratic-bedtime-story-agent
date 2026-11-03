import sys

from guard import Route, check_request
from messages import (
    DECLINE_MESSAGE,
    ESCALATION_MESSAGE,
    FEEDBACK_DECLINE_MESSAGE,
    FEEDBACK_FAILED_MESSAGE,
    FEEDBACK_KEPT_MESSAGE,
    STORY_NOT_READY_MESSAGE,
)
from outline import plan_outline
from refine import MAX_FEEDBACK_ROUNDS, apply_feedback
from revision import improve_story, save_run
from storyteller import write_story

"""
Before submitting the assignment, describe here in a few sentences what you would have built next if you spent 2 more hours on this project:

DRAFT, to be rewritten in your own words:
With two more hours I would write a held-out eval set before tuning any more prompts, and run it several times to measure how much the results vary. I would check the judge against a few dozen stories rated by people, and see whether its scores agree with them. I would add a brand and medicine list in code, so the deterministic gate catches those words as well as the reviewer. I would give keep-or-revert a small score tolerance, since a 0.2 difference rejected a change the user asked for. I would move the emergency numbers into a per-country setting. Last, I would add an option to delete runs/ after each session, because those files hold children's text.

"""

example_requests = "A story about a girl named Alice and her best friend Bob, who happens to be a cat."


def main():
    user_input = input("What kind of story do you want to hear? ")
    try:
        result = check_request(user_input)
        if result.route is Route.ESCALATE:
            print(ESCALATION_MESSAGE)
            return
        if result.route is Route.DECLINE:
            print(DECLINE_MESSAGE)
            return
        outline = plan_outline(user_input, result)
        category = result.category or "calm_and_cozy"
        improved = improve_story(write_story(outline, category), outline, result, user_input)
        save_run(user_input, category, improved)
        if improved.story is None:
            print(STORY_NOT_READY_MESSAGE)
            return
    except RuntimeError as error:
        print(f"Error: {error}")
        sys.exit(1)
    except ValueError:
        print("The model gave an unusable answer. Please try again.")
        sys.exit(1)

    _show(outline.title, improved.story)
    for _ in range(MAX_FEEDBACK_ROUNDS):
        feedback = input("Would you like any changes? Type them, or press Enter to finish. ").strip()
        if not feedback:
            break
        try:
            outcome = apply_feedback(outline, improved, result, user_input, feedback)
        except (RuntimeError, ValueError):
            print(FEEDBACK_FAILED_MESSAGE)
            continue
        if outcome.attempt is not None:
            save_run(f"{user_input} | feedback: {feedback}", category, outcome.attempt)
        if outcome.action == "escalate":
            print(ESCALATION_MESSAGE)
            return
        if outcome.action == "declined":
            print(FEEDBACK_DECLINE_MESSAGE)
            continue
        if outcome.action == "kept_previous":
            print(FEEDBACK_KEPT_MESSAGE)
            continue
        outline, improved = outcome.outline, outcome.improved
        _show(outline.title, improved.story)


def _show(title: str, story: str | None) -> None:
    print()
    print(title)
    print()
    print(story)


if __name__ == "__main__":
    main()
