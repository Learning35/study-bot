# app.py
# The Flask part of my study bot. It saves decks and cards in a SQLite
# file (studybot.db) and the page talks to it through the /api/ routes.

import random
import sqlite3
import time

from flask import Flask, g, jsonify, render_template, request

import quiz

app = Flask(__name__)
DB_FILE = "studybot.db"


# ---------- database ----------

def get_db():
    # open the database once per request and reuse it
    if "db" not in g:
        g.db = sqlite3.connect(DB_FILE)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(error):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def make_tables():
    db = sqlite3.connect(DB_FILE)
    db.executescript("""
        CREATE TABLE IF NOT EXISTS decks (
            id   INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS cards (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            deck_id     INTEGER NOT NULL,
            term        TEXT NOT NULL,
            definition  TEXT NOT NULL,
            box         INTEGER NOT NULL DEFAULT 0,
            due         REAL NOT NULL DEFAULT 0,
            times_seen  INTEGER NOT NULL DEFAULT 0,
            times_right INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS stats (
            id      INTEGER PRIMARY KEY CHECK (id = 1),
            asked   INTEGER NOT NULL DEFAULT 0,
            correct INTEGER NOT NULL DEFAULT 0,
            streak  INTEGER NOT NULL DEFAULT 0,
            best    INTEGER NOT NULL DEFAULT 0
        );
        INSERT OR IGNORE INTO stats (id) VALUES (1);
    """)
    db.commit()
    db.close()


def get_stats(db):
    row = db.execute("SELECT asked, correct, streak, best FROM stats WHERE id = 1").fetchone()
    return dict(row)


# ---------- pages ----------

@app.route("/")
def home():
    return render_template("index.html")


# ---------- decks ----------

@app.route("/api/decks", methods=["GET"])
def list_decks():
    db = get_db()
    rows = db.execute("""
        SELECT d.id, d.name,
               COUNT(c.id) AS total,
               COALESCE(SUM(CASE WHEN c.due <= ? THEN 1 ELSE 0 END), 0) AS due
        FROM decks d
        LEFT JOIN cards c ON c.deck_id = d.id
        GROUP BY d.id
        ORDER BY d.id
    """, (time.time(),)).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/decks", methods=["POST"])
def add_deck():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()[:40]
    notes = data.get("notes") or ""

    if not name:
        return jsonify(error="Give the deck a name."), 400

    cards = quiz.parse_notes(notes)
    if not cards:
        return jsonify(error="No cards found. Write one per line as term: definition."), 400

    db = get_db()
    cur = db.execute("INSERT INTO decks (name) VALUES (?)", (name,))
    deck_id = cur.lastrowid
    for term, definition in cards:
        db.execute(
            "INSERT INTO cards (deck_id, term, definition) VALUES (?, ?, ?)",
            (deck_id, term, definition),
        )
    db.commit()
    return jsonify(id=deck_id, name=name, cards=len(cards)), 201


@app.route("/api/decks/<int:deck_id>/cards", methods=["POST"])
def add_cards(deck_id):
    db = get_db()
    deck = db.execute("SELECT id FROM decks WHERE id = ?", (deck_id,)).fetchone()
    if deck is None:
        return jsonify(error="That deck doesn't exist anymore."), 404

    data = request.get_json(silent=True) or {}
    cards = quiz.parse_notes(data.get("notes") or "")
    if not cards:
        return jsonify(error="No cards found. Write one per line as term: definition."), 400

    for term, definition in cards:
        db.execute(
            "INSERT INTO cards (deck_id, term, definition) VALUES (?, ?, ?)",
            (deck_id, term, definition),
        )
    db.commit()
    return jsonify(added=len(cards)), 201


@app.route("/api/decks/<int:deck_id>", methods=["DELETE"])
def delete_deck(deck_id):
    db = get_db()
    db.execute("DELETE FROM cards WHERE deck_id = ?", (deck_id,))
    db.execute("DELETE FROM decks WHERE id = ?", (deck_id,))
    # deleting a deck also resets the streak and accuracy (the best streak stays)
    db.execute("UPDATE stats SET streak = 0, asked = 0, correct = 0 WHERE id = 1")
    db.commit()
    return jsonify(ok=True)


# ---------- quizzing ----------

@app.route("/api/decks/<int:deck_id>/next")
def next_card(deck_id):
    db = get_db()
    force = request.args.get("force") == "1"
    last_id = request.args.get("last", type=int)

    if force:
        rows = db.execute("SELECT * FROM cards WHERE deck_id = ?", (deck_id,)).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM cards WHERE deck_id = ? AND due <= ?",
            (deck_id, time.time()),
        ).fetchall()

    if not rows:
        return jsonify(done=True)

    # ask the cards I know the least first, and don't repeat the last one
    lowest_box = min(r["box"] for r in rows)
    pool = [r for r in rows if r["box"] == lowest_box]
    if len(pool) > 1 and last_id:
        pool = [r for r in pool if r["id"] != last_id]

    pick = random.choice(pool)
    return jsonify(done=False, id=pick["id"], term=pick["term"])


@app.route("/api/cards/<int:card_id>/answer", methods=["POST"])
def check_answer(card_id):
    # this only grades the answer. The score gets saved in /result below,
    # since sometimes I was right even if the grader says no.
    db = get_db()
    card = db.execute("SELECT * FROM cards WHERE id = ?", (card_id,)).fetchone()
    if card is None:
        return jsonify(error="That card doesn't exist anymore."), 404

    data = request.get_json(silent=True) or {}
    score = quiz.grade(data.get("answer", ""), card["definition"])
    return jsonify(
        score=round(score, 2),
        passed=score >= quiz.PASS_SCORE,
        definition=card["definition"],
    )


@app.route("/api/cards/<int:card_id>/result", methods=["POST"])
def save_result(card_id):
    db = get_db()
    card = db.execute("SELECT * FROM cards WHERE id = ?", (card_id,)).fetchone()
    if card is None:
        return jsonify(error="That card doesn't exist anymore."), 404

    data = request.get_json(silent=True) or {}
    was_right = bool(data.get("correct"))

    new_box = quiz.next_box(card["box"], was_right)
    db.execute(
        """UPDATE cards
           SET box = ?, due = ?, times_seen = times_seen + 1,
               times_right = times_right + ?
           WHERE id = ?""",
        (new_box, quiz.due_time(new_box), 1 if was_right else 0, card_id),
    )

    stats = get_stats(db)
    stats["asked"] += 1
    if was_right:
        stats["correct"] += 1
        stats["streak"] += 1
        stats["best"] = max(stats["best"], stats["streak"])
    else:
        stats["streak"] = 0

    db.execute(
        "UPDATE stats SET asked = ?, correct = ?, streak = ?, best = ? WHERE id = 1",
        (stats["asked"], stats["correct"], stats["streak"], stats["best"]),
    )
    db.commit()
    return jsonify(stats)


@app.route("/api/stats")
def stats():
    return jsonify(get_stats(get_db()))


make_tables()

if __name__ == "__main__":
    app.run(debug=True)


#  /\_/\
# ( o.o )   keep studying!
#  > ^ <
