import sys

from guard import Route, check_request
from llm import call_model
from messages import DECLINE_MESSAGE, ESCALATION_MESSAGE

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
        # The storyteller arrives in milestone 3. Until then, the raw model answers.
        response = call_model(user_input)
    except RuntimeError as error:
        print(f"Error: {error}")
        sys.exit(1)
    print(response)


if __name__ == "__main__":
    main()
