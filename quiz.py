# quiz.py
# The quiz logic for my study bot: reading notes, grading answers, and
# deciding when a card comes back. I kept Flask out of this file so I
# can test it on its own.

import re
import time

DAY = 24 * 60 * 60  # seconds

# Every card sits in a box from 0 to 4. A higher box means I know it better,
# so it waits longer before it shows up again.
WAIT_DAYS = [0, 1, 3, 7, 14]

# how much of the answer I need to match to count as right
PASS_SCORE = 0.6

# little words I ignore when checking an answer
STOP_WORDS = {
    "a", "an", "the", "of", "to", "in", "on", "is", "are", "was", "were",
    "be", "and", "or", "for", "with", "as", "by", "it", "its", "that",
    "this", "at", "from",
}


def parse_notes(text):
    """Turns pasted notes into a list of (term, definition) pairs.

    Each line should look like "term: definition" or "term - definition".
    Lines that don't match are skipped.
    """
    cards = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        match = re.match(r"^(.+?)\s*(?::|\s[-\u2013]\s)\s*(.+)$", line)
        if match:
            cards.append((match.group(1), match.group(2)))
    return cards



def chop_ending(word):
    """Remove common word endings without changing the meaning too much."""

    # Handle common spelling changes
    special_words = {
        "coding": "code",
        "programming": "programming",
        "programs": "program",
        "creating": "create",
        "created": "create",
        "building": "build",
        "built": "build",
        "storing": "store",
        "stored": "store",
        "saving": "save",
        "saved": "save",
    }

    if word in special_words:
        return special_words[word]

    # Remove simple plural endings
    if word.endswith("s") and not word.endswith(("ss", "us", "is")) and len(word) > 4:
        return word[:-1]

    return word



def get_words(text):
    text = re.sub(r"[^a-z0-9 ]", " ", text.lower())
    words = []
    for word in text.split():
        if word not in STOP_WORDS:
            words.append(chop_ending(word))
    return words



def grade(user_answer, real_answer):
    """Compare answers while allowing common wording differences."""

    # Common words that students might use interchangeably
    synonyms = {
        "create": "make",
        "build": "make",
        "develop": "make",
        "generate": "make",
        "produce": "make",
        "program": "software",
        "application": "software",
        "app": "software",
        "coding": "programming",
        "code": "programming",
        "developer": "programmer",
        "dev": "programmer",
        "quick": "fast",
        "rapid": "fast",
        "large": "big",
        "small": "little",
        "store": "save",
        "keep": "save",
        "retrieve": "get",
        "fetch": "get",
        "find": "get",
    }

    def normalize(text):
        words = get_words(text)

        normalized = set()

        for word in words:
            normalized.add(synonyms.get(word, word))

        return normalized

    needed = normalize(real_answer)
    given = normalize(user_answer)

    if not needed:
        return 0.0

    # Give credit for matching keywords or common synonyms
    matches = len(needed & given)

    return matches / len(needed)



def next_box(box, was_right):
    if was_right:
        return min(box + 1, len(WAIT_DAYS) - 1)
    return 0  # missed it, back to the start


def due_time(box, now=None):
    if now is None:
        now = time.time()
    return now + WAIT_DAYS[box] * DAY
