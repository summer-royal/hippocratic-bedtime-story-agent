"""Fixed messages the app shows to children and parents.

The emergency numbers are US numbers (911 and 988). Change them for another
country before using the app there.
"""

ESCALATION_MESSAGE = (
    "It sounds like something hard may be happening, and you deserve help. "
    "Please tell a grown-up you trust right now, such as a parent, teacher, or caregiver. "
    "If you are hurt or in danger, call 911 right away. "
    "You can also call or text 988 at any time to talk with someone. "
    "Asking for help was the right thing to do."
)

DECLINE_MESSAGE = (
    "I can't write that story, but I'd love to help with another one. "
    "How about a story about a brave little turtle who helps a lost puppy find home?"
)

STORY_NOT_READY_MESSAGE = (
    "I could not finish a story I am happy with this time. "
    "Please try asking again, or try a different story idea."
)

FEEDBACK_DECLINE_MESSAGE = (
    "I can't make that change, but I'd be glad to make a different one. "
    "What else would you like to change?"
)

FEEDBACK_KEPT_MESSAGE = (
    "I tried that change, but the new version did not score as well, "
    "so I kept the story as it was."
)

FEEDBACK_FAILED_MESSAGE = (
    "I could not make that change this time. Your story is unchanged. "
    "Please try the change again, or ask for something different."
)
