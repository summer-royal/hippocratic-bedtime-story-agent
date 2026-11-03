"""Thin wrapper around the Anthropic Messages API.

Every model call in the project goes through call_model(), so the model name,
API key handling, and error messages live in one place.
"""

import os

import anthropic
from dotenv import load_dotenv

MODEL = "claude-haiku-5-5"
API_KEY_ENV_VAR = "ANTHROPIC_API_KEY"


def get_client() -> anthropic.Anthropic:
    """Create an Anthropic client, reading the key from the environment or .env.

    Returns:
        A client ready to make Messages API calls.

    Raises:
        RuntimeError: If ANTHROPIC_API_KEY is not set.
    """
    load_dotenv()
    if not os.getenv(API_KEY_ENV_VAR):
        raise RuntimeError(
            f"{API_KEY_ENV_VAR} is not set. Copy .env.example to .env "
            "and add your Anthropic API key."
        )
    return anthropic.Anthropic()


def call_model(prompt: str, system: str | None = None, max_tokens: int = 3000) -> str:
    """Send one user message to Claude Haiku 5.5 and return the text reply.

    Args:
        prompt: The user message.
        system: Optional system prompt that sets the model's role and rules.
        max_tokens: Upper limit on the length of the reply, in tokens.

    Returns:
        The text of the reply. Thinking blocks are skipped.

    Raises:
        RuntimeError: If the key is missing or rejected, the network fails,
            the model declines the request, or the reply was cut off at max_tokens.
    """
    client = get_client()
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=max_tokens,
            system=system or anthropic.NOT_GIVEN,
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.AuthenticationError as error:
        raise RuntimeError(
            f"The API key was rejected. Check {API_KEY_ENV_VAR} in .env."
        ) from error
    except anthropic.APIConnectionError as error:
        raise RuntimeError(
            "Could not reach the Anthropic API. Check your internet connection."
        ) from error
    except anthropic.RateLimitError as error:
        raise RuntimeError("The Anthropic API is busy right now. Please wait a minute and try again.") from error
    except anthropic.APIError as error:
        raise RuntimeError(
            f"The Anthropic API returned an error ({type(error).__name__}). Please try again."
        ) from error

    if response.stop_reason == "refusal":
        raise RuntimeError("The model declined this request.")
    # A cut-off reply is unusable: a story or JSON that stops mid-way must never reach a child.
    if response.stop_reason == "max_tokens":
        raise RuntimeError("The model's reply was cut off before it finished. Please try again.")

    return "".join(block.text for block in response.content if block.type == "text")
