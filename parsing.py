"""Helpers for reading JSON out of model replies."""

import json


def parse_json_object(text: str) -> dict:
    """Extract and parse the JSON object in a model reply.

    Models sometimes wrap JSON in code fences or add a sentence before it, so
    this takes the text between the first "{" and the last "}" instead of
    trusting the whole reply.

    Args:
        text: The raw reply from the model.

    Returns:
        The parsed JSON object.

    Raises:
        ValueError: If the reply contains no JSON object.
    """
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("No JSON object found in model reply.")
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError as error:
        raise ValueError(f"Model reply is not valid JSON: {error}") from error
    if not isinstance(data, dict):
        raise ValueError("Model reply JSON is not an object.")
    return data
