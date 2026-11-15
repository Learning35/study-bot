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
    # cuts off endings so "sorted" and "sorts" both become "sort"
    for ending in ("ing", "ed", "es", "s"):
        if word.endswith(ending) and len(word) > len(ending) + 2:
            return word[: -len(ending)]
    return word


def get_words(text):
    text = re.sub(r"[^a-z0-9 ]", " ", text.lower())
    words = []
    for word in text.split():
        if word not in STOP_WORDS:
            words.append(chop_ending(word))
    return words


def grade(user_answer, real_answer):
    """Gives a score from 0 to 1 for how many of the answer's
    keywords were in what I typed."""
    needed = set(get_words(real_answer))
    if not needed:
        return 0.0
    given = set(get_words(user_answer))
    return len(needed & given) / len(needed)


def next_box(box, was_right):
    if was_right:
        return min(box + 1, len(WAIT_DAYS) - 1)
    return 0  # missed it, back to the start


def due_time(box, now=None):
    if now is None:
        now = time.time()
    return now + WAIT_DAYS[box] * DAY
