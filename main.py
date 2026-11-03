import sys

from guard import Route, check_request
from messages import DECLINE_MESSAGE, ESCALATION_MESSAGE, STORY_NOT_READY_MESSAGE
from outline import plan_outline
from review import review_story
from storyteller import write_story

"""
Before submitting the assignment, describe here in a few sentences what you would have built next if you spent 2 more hours on this project:

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
        story = write_story(outline, result.category or "calm_and_cozy")
        review = review_story(story, outline, result, user_input)
        if not review.passed:
            # Developer log only: the child sees the friendly message below, never these details.
            for problem in review.problems:
                print(f"Developer log: {problem}", file=sys.stderr)
            print(STORY_NOT_READY_MESSAGE)
            return
    except RuntimeError as error:
        print(f"Error: {error}")
        sys.exit(1)
    except ValueError:
        print("The story planner gave an unusable answer. Please try again.")
        sys.exit(1)
    print(outline.title)
    print()
    print(story)


if __name__ == "__main__":
    main()
