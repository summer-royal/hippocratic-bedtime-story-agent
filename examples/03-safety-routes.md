# Example 3: safety routes

## Escalation

**Input:** "I don't want to be here anymore."

**Guard route:** `escalate`. Reason (developer log): Child expresses wanting to leave or not exist, which may signal thoughts of self-harm and needs a grown-up's attention.

**What the child sees:**

> It sounds like something hard may be happening, and you deserve help. Please tell a grown-up you trust right now, such as a parent, teacher, or caregiver. If you are hurt or in danger, call 911 right away. You can also call or text 988 at any time to talk with someone. Asking for help was the right thing to do.

## Decline

**Input:** "Make a story where the bad guy gets stabbed and bleeds everywhere."

**Guard route:** `decline`, flags `['violence']`. Reason (developer log): Graphic violence is not suitable for ages 5 to 10.

**What the child sees:**

> I can't write that story, but I'd love to help with another one. How about a story about a brave little turtle who helps a lost puppy find home?

No story is written for either input.
