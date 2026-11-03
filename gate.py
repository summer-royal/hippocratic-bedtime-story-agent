"""Deterministic final gate: plain-Python checks that no model can argue past.

These checks run on every story after the safety reviewer. They cover length,
sentence length, banned words, web addresses, numbers, names from the request,
and the closing line. Because this is code, it applies the same rules every time.
"""

import re

MIN_WORDS = 300
MAX_WORDS = 450
MAX_AVERAGE_SENTENCE_WORDS = 12
MAX_SENTENCE_WORDS = 25

BANNED_WORDS = frozenset(
    {
        "blood", "bleed", "bleeding", "kill", "killed", "killing", "death", "died", "dies", "dying",
        "gun", "guns", "knife", "knives", "bomb", "poison", "weapon", "weapons", "stab", "stabbed",
        "medicine", "medication", "pill", "pills", "dose", "doses", "drug", "drugs", "alcohol",
        "beer", "wine", "cigarette", "cigarettes", "smoking", "kiss", "kissed", "boyfriend", "girlfriend",
    }
)

# Capitalized words that are not names, so they are not treated as personal details.
COMMON_CAPITALIZED_WORDS = frozenset(
    {
        "A", "About", "After", "And", "Can", "Could", "For", "Give", "I", "If", "In", "It", "Make",
        "Me", "My", "Once", "Please", "Story", "Tell", "The", "Then", "We", "With", "Write", "Yes",
    }
)

WEB_ADDRESS_PATTERN = re.compile(r"https?://|www\.|\S+@\S+\.\S+")


def gate_problems(story: str, closing_line: str, risk_flags: tuple[str, ...], request: str) -> list[str]:
    """Check a story against the code rules.

    Args:
        story: The storyteller's text.
        closing_line: The final line the outline promised.
        risk_flags: The guard's flags for the request.
        request: The text the parent or child typed, used for the personal-details check.

    Returns:
        A list of problems. An empty list means the story passes the gate.
    """
    if not story.strip():
        return ["The story is empty."]

    problems = []
    words = len(story.split())
    if not MIN_WORDS <= words <= MAX_WORDS:
        problems.append(f"Length is {words} words; it must be between {MIN_WORDS} and {MAX_WORDS}.")

    sentence_lengths = [len(sentence.split()) for sentence in re.split(r"[.!?]+", story) if sentence.strip()]
    average_length = sum(sentence_lengths) / len(sentence_lengths)
    if average_length > MAX_AVERAGE_SENTENCE_WORDS:
        problems.append(f"Average sentence is {average_length:.1f} words; the limit is {MAX_AVERAGE_SENTENCE_WORDS}.")
    if max(sentence_lengths) > MAX_SENTENCE_WORDS:
        problems.append(f"A sentence has {max(sentence_lengths)} words; the limit is {MAX_SENTENCE_WORDS}.")

    lowered = story.lower()
    banned_found = sorted(word for word in BANNED_WORDS if re.search(rf"\b{word}\b", lowered))
    if banned_found:
        problems.append(f"Contains banned words: {', '.join(banned_found)}.")

    if WEB_ADDRESS_PATTERN.search(story):
        problems.append("Contains a web address or email address.")
    if re.search(r"\d", story):
        problems.append("Contains digits, which can reveal a phone number or address.")

    if "personal_info" in risk_flags:
        leaked = [name for name in _names_in_request(request) if re.search(rf"\b{name}\b", story)]
        if leaked:
            problems.append(f"Repeats details from the request: {', '.join(leaked)}.")

    if not _normalize(story).endswith(_normalize(closing_line)):
        problems.append("Does not end with the closing line from the outline.")
    return problems


def _names_in_request(request: str) -> list[str]:
    capitalized = re.findall(r"\b[A-Z][a-z]+\b", request)
    return sorted({word for word in capitalized if word not in COMMON_CAPITALIZED_WORDS})


def _normalize(text: str) -> str:
    """Lowercase, drop quotes and end punctuation, and collapse spaces, so the closing-line check ignores typography."""
    text = text.lower()
    text = re.sub(r"[\"'“”‘’]", "", text)
    text = re.sub(r"[^\w\s,]", "", text)
    return " ".join(text.split())
