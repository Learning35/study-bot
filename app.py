# app.py
# The Flask part of my study bot. It saves decks and cards in a SQLite
# file (studybot.db) and the page talks to it through the /api/ routes.

import random
import sqlite3
import os
import time

import psycopg
from psycopg.rows import dict_row

from flask import Flask, g, jsonify, render_template, request

import quiz

from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
# Configure secure login sessions
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or os.urandom(32)

login_manager = LoginManager()
login_manager.init_app(app)

@login_manager.unauthorized_handler
def unauthorized():
    # Return JSON instead of redirecting API requests
    return jsonify(error="Please log in to continue."), 401

DB_FILE = os.environ.get("DATABASE_PATH", "studybot.db")
DATABASE_URL = os.environ.get("DATABASE_URL")


def execute_query(db, query, params=()):
    # PostgreSQL uses %s instead of ? for SQL values
    if DATABASE_URL:
        query = query.replace("?", "%s")

    return db.execute(query, params)


class User(UserMixin):
    # Represent a student account
    def __init__(self, id, email, password_hash):
        self.id = id
        self.email = email
        self.password_hash = password_hash


@login_manager.user_loader
def load_user(user_id):
    # Find the logged-in student in the database
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        return None

    db = get_db()

    row = execute_query(
        db,
        "SELECT id, email, password_hash FROM users WHERE id = ?",
        (user_id,)
    ).fetchone()

    if row is None:
        return None

    return User(
        id=row["id"],
        email=row["email"],
        password_hash=row["password_hash"]
    )



@app.route("/api/signup", methods=["POST"])
def signup():
    # Get the student's account information
    data = request.get_json(silent=True) or {}

    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    # Check the email and password
    if not email or "@" not in email or len(email) > 254:
        return jsonify(error="Enter a valid email address."), 400

    if len(password) < 12 or len(password) > 128:
        return jsonify(
            error="Password must be between 12 and 128 characters."
        ), 400

    db = get_db()

    # Check whether the email is already registered
    existing_user = execute_query(
        db,
        "SELECT id FROM users WHERE email = ?",
        (email,)
    ).fetchone()

    if existing_user:
        return jsonify(error="This email is already registered."), 409

    # Hash the password before storing it
    password_hash = generate_password_hash(password)

    # Create the student account
    if DATABASE_URL:
        cur = execute_query(
            db,
            """
            INSERT INTO users (email, password_hash)
            VALUES (?, ?)
            RETURNING id
            """,
            (email, password_hash)
        )
        user_id = cur.fetchone()["id"]
    else:
        cur = execute_query(
            db,
            """
            INSERT INTO users (email, password_hash)
            VALUES (?, ?)
            """,
            (email, password_hash)
        )
        user_id = cur.lastrowid

    db.commit()

    # Sign the student in after registration
    user = User(user_id, email, password_hash)
    login_user(user)

    return jsonify(
        message="Account created successfully!",
        user={"id": user_id, "email": email}
    ), 201


@app.route("/api/login", methods=["POST"])
def login():
    # Get the student's login information
    data = request.get_json(silent=True) or {}

    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return jsonify(error="Email and password are required."), 400

    db = get_db()

    # Find the student by email
    row = execute_query(
        db,
        "SELECT id, email, password_hash FROM users WHERE email = ?",
        (email,)
    ).fetchone()

    # Check the email and password
    if row is None or not check_password_hash(row["password_hash"], password):
        return jsonify(error="Invalid email or password."), 401

    # Sign the student in
    user = User(
        id=row["id"],
        email=row["email"],
        password_hash=row["password_hash"]
    )

    login_user(user)

    return jsonify(
        message="Logged in successfully!",
        user={
            "id": user.id,
            "email": user.email
        }
    ), 200

@app.route("/api/logout", methods=["POST"])
def logout():
    # Check whether the student is logged in
    if not current_user.is_authenticated:
        return jsonify(error="You are not logged in."), 401

    # End the student's login session
    logout_user()

    return jsonify(message="Logged out successfully!"), 200


@app.route("/api/me", methods=["GET"])
def get_current_user():
    # Check whether a student is logged in
    if not current_user.is_authenticated:
        return jsonify(
            authenticated=False,
            user=None
        ), 200

    # Return the logged-in student's information
    return jsonify(
        authenticated=True,
        user={
            "id": current_user.id,
            "email": current_user.email
        }
    ), 200


# ---------- database ----------

def get_db():
    # Open the database once per request and reuse it
    if "db" not in g:
        if DATABASE_URL:
            # Use PostgreSQL when deployed
            g.db = psycopg.connect(
                DATABASE_URL,
                row_factory=dict_row
            )
        else:
            # Use SQLite on my Mac
            g.db = sqlite3.connect(DB_FILE)
            g.db.row_factory = sqlite3.Row

    return g.db


@app.teardown_appcontext
def close_db(error):
    db = g.pop("db", None)
    if db is not None:
        db.close()






def make_tables():
    db = get_db()

    # Create the users table
    if DATABASE_URL:
        execute_query(db, """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL
            )
        """)
    else:
        execute_query(db, """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL
            )
        """)

    # Create the decks table
    if DATABASE_URL:
        execute_query(db, """
            CREATE TABLE IF NOT EXISTS decks (
                id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                name TEXT NOT NULL,
                user_id INTEGER REFERENCES users(id)
            )
        """)
    else:
        execute_query(db, """
            CREATE TABLE IF NOT EXISTS decks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                user_id INTEGER REFERENCES users(id)
            )
        """)

    # Add user_id to older decks tables
    if DATABASE_URL:
        execute_query(db, """
            ALTER TABLE decks
            ADD COLUMN IF NOT EXISTS user_id
            INTEGER REFERENCES users(id)
        """)
    else:
        columns = execute_query(
            db, "PRAGMA table_info(decks)"
        ).fetchall()

        column_names = [column["name"] for column in columns]

        if "user_id" not in column_names:
            execute_query(db, """
                ALTER TABLE decks
                ADD COLUMN user_id INTEGER REFERENCES users(id)
            """)

    # Create the flashcards table
    if DATABASE_URL:
        execute_query(db, """
            CREATE TABLE IF NOT EXISTS cards (
                id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                deck_id INTEGER NOT NULL REFERENCES decks(id),
                term TEXT NOT NULL,
                definition TEXT NOT NULL,
                box INTEGER NOT NULL DEFAULT 1,
                due REAL NOT NULL DEFAULT 0,
                times_seen INTEGER NOT NULL DEFAULT 0,
                times_right INTEGER NOT NULL DEFAULT 0
            )
        """)
    else:
        execute_query(db, """
            CREATE TABLE IF NOT EXISTS cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                deck_id INTEGER NOT NULL REFERENCES decks(id),
                term TEXT NOT NULL,
                definition TEXT NOT NULL,
                box INTEGER NOT NULL DEFAULT 1,
                due REAL NOT NULL DEFAULT 0,
                times_seen INTEGER NOT NULL DEFAULT 0,
                times_right INTEGER NOT NULL DEFAULT 0
            )
        """)

    # Create the study statistics table
    if DATABASE_URL:
        execute_query(db, """
            CREATE TABLE IF NOT EXISTS stats (
                id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                asked INTEGER NOT NULL DEFAULT 0,
                correct INTEGER NOT NULL DEFAULT 0,
                streak INTEGER NOT NULL DEFAULT 0,
                best INTEGER NOT NULL DEFAULT 0,
                user_id INTEGER REFERENCES users(id)
            )
        """)
    else:
        execute_query(db, """
            CREATE TABLE IF NOT EXISTS stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asked INTEGER NOT NULL DEFAULT 0,
                correct INTEGER NOT NULL DEFAULT 0,
                streak INTEGER NOT NULL DEFAULT 0,
                best INTEGER NOT NULL DEFAULT 0,
                user_id INTEGER REFERENCES users(id)
            )
        """)

    # Add user_id to older statistics tables
    if DATABASE_URL:
        execute_query(db, """
            ALTER TABLE stats
            ADD COLUMN IF NOT EXISTS user_id
            INTEGER REFERENCES users(id)
        """)
    else:
        columns = execute_query(
            db, "PRAGMA table_info(stats)"
        ).fetchall()

        column_names = [column["name"] for column in columns]

        if "user_id" not in column_names:
            execute_query(db, """
                ALTER TABLE stats
                ADD COLUMN user_id INTEGER REFERENCES users(id)
            """)

    # Keep PostgreSQL's automatic ID generation in sync
    # with any existing statistics records.
    if DATABASE_URL:
        execute_query(db, """
            SELECT setval(
                pg_get_serial_sequence('stats', 'id'),
                COALESCE((SELECT MAX(id) FROM stats), 1),
                EXISTS (SELECT 1 FROM stats)
            )
        """)

    # Remove the old single-user statistics restriction
    # from older PostgreSQL databases
    if DATABASE_URL:
        execute_query(db, """
            ALTER TABLE stats
            DROP CONSTRAINT IF EXISTS stats_id_check
        """)

    # Make sure each student has only one statistics record
    execute_query(db, """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_stats_user_id
        ON stats (user_id)
    """)

    # Keep the original shared stats record for compatibility
    execute_query(db, """
        INSERT INTO stats (id, asked, correct, streak, best)
        SELECT 1, 0, 0, 0, 0
        WHERE NOT EXISTS (
            SELECT 1 FROM stats WHERE id = 1
        )
    """)

    db.commit()





def get_stats(db):
    # Get the currently logged-in student's ID
    user_id = current_user.id

    # Look for the student's existing statistics
    row = execute_query(
        db,
        """
        SELECT asked, correct, streak, best
        FROM stats
        WHERE user_id = ?
        """,
        (user_id,)
    ).fetchone()

    # Create a statistics record for new students
    if row is None:
        if DATABASE_URL:
            execute_query(
                db,
                """
                INSERT INTO stats
                    (user_id, asked, correct, streak, best)
                VALUES (?, 0, 0, 0, 0)
                ON CONFLICT (user_id) DO NOTHING
                """,
                (user_id,)
            )
        else:
            execute_query(
                db,
                """
                INSERT OR IGNORE INTO stats
                    (user_id, asked, correct, streak, best)
                VALUES (?, 0, 0, 0, 0)
                """,
                (user_id,)
            )

        db.commit()

        # Try reading the statistics again
        row = execute_query(
            db,
            """
            SELECT asked, correct, streak, best
            FROM stats
            WHERE user_id = ?
            """,
            (user_id,)
        ).fetchone()

    # If no record exists, return safe starting values
    if row is None:
        return {
            "asked": 0,
            "correct": 0,
            "streak": 0,
            "best": 0
        }

    # Return the student's saved statistics
    return {
        "asked": row["asked"],
        "correct": row["correct"],
        "streak": row["streak"],
        "best": row["best"]
    }


# ---------- pages ----------

@app.route("/")
def home():
    return render_template("index.html")


# ---------- decks ----------

@app.route("/api/decks", methods=["GET"])
@login_required
def list_decks():
    db = get_db()

    # Only retrieve decks owned by the logged-in student
    rows = execute_query(
        db,
        """
        SELECT d.id, d.name,
               COUNT(c.id) AS total,
               COALESCE(
                   SUM(CASE WHEN c.due <= ? THEN 1 ELSE 0 END),
                   0
               ) AS due
        FROM decks d
        LEFT JOIN cards c ON c.deck_id = d.id
        WHERE d.user_id = ?
        GROUP BY d.id, d.name
        ORDER BY d.id
        """,
        (time.time(), current_user.id)
    ).fetchall()

    return jsonify([dict(row) for row in rows])


@app.route("/api/decks", methods=["POST"])
@login_required
def add_deck():
    # Get the student's deck information
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()[:40]
    notes = data.get("notes") or ""

    if not name:
        return jsonify(error="Give the deck a name."), 400

    # Convert the notes into flashcards
    cards = quiz.parse_notes(notes)

    if not cards:
        return jsonify(
            error="No cards found. Write one per line as term: definition."
        ), 400

    db = get_db()

    # Create a deck owned by the logged-in student
    if DATABASE_URL:
        cur = execute_query(
            db,
            """
            INSERT INTO decks (name, user_id)
            VALUES (?, ?)
            RETURNING id
            """,
            (name, current_user.id)
        )

        deck_id = cur.fetchone()["id"]

    else:
        cur = execute_query(
            db,
            """
            INSERT INTO decks (name, user_id)
            VALUES (?, ?)
            """,
            (name, current_user.id)
        )

        deck_id = cur.lastrowid

    # Add flashcards to the new deck
    for term, definition in cards:
        execute_query(
            db,
            """
            INSERT INTO cards (deck_id, term, definition)
            VALUES (?, ?, ?)
            """,
            (deck_id, term, definition)
        )

    db.commit()

    return jsonify(
        id=deck_id,
        name=name,
        cards=len(cards)
    ), 201



@app.route("/api/decks/<int:deck_id>/cards", methods=["POST"])
@login_required
def add_cards(deck_id):
    db = get_db()

    # Check that this deck belongs to the logged-in student
    deck = execute_query(
        db,
        """
        SELECT id FROM decks
        WHERE id = ? AND user_id = ?
        """,
        (deck_id, current_user.id)
    ).fetchone()

    if deck is None:
        return jsonify(
            error="Deck not found."
        ), 404

    # Get the student's new flashcards
    data = request.get_json(silent=True) or {}
    cards = quiz.parse_notes(data.get("notes") or "")

    if not cards:
        return jsonify(
            error="No cards found. Write one per line as term: definition."
        ), 400

    # Add flashcards only to the student's own deck
    for term, definition in cards:
        execute_query(
            db,
            """
            INSERT INTO cards (deck_id, term, definition)
            VALUES (?, ?, ?)
            """,
            (deck_id, term, definition)
        )

    db.commit()

    return jsonify(added=len(cards)), 201


@app.route("/api/decks/<int:deck_id>", methods=["DELETE"])
@login_required
def delete_deck(deck_id):
    db = get_db()

    # Check that the deck belongs to the logged-in student
    deck = execute_query(
        db,
        """
        SELECT id FROM decks
        WHERE id = ? AND user_id = ?
        """,
        (deck_id, current_user.id)
    ).fetchone()

    if deck is None:
        return jsonify(error="Deck not found."), 404

    # Delete flashcards belonging to this deck
    execute_query(
        db,
        "DELETE FROM cards WHERE deck_id = ?",
        (deck_id,)
    )

    # Delete the student's deck
    execute_query(
        db,
        """
        DELETE FROM decks
        WHERE id = ? AND user_id = ?
        """,
        (deck_id, current_user.id)
    )

    db.commit()

    return jsonify(ok=True), 200


# ---------- quizzing ----------

@app.route("/api/decks/<int:deck_id>/next")
@login_required

def next_card(deck_id):
    db = get_db()

    # Check that the deck belongs to the logged-in student
    deck = execute_query(
        db,
        """
        SELECT id FROM decks
        WHERE id = ? AND user_id = ?
        """,
        (deck_id, current_user.id)
    ).fetchone()

    if deck is None:
        return jsonify(error="Deck not found."), 404

    # Check whether the student wants to practice early
    force = request.args.get("force") == "1"

    # Remember the previous card to avoid immediate repeats
    last_id = request.args.get("last", type=int)

    # Cards already answered during this quiz attempt
    excluded_ids = set()

    excluded_text = request.args.get("exclude", "")

    if excluded_text:
        try:
            excluded_ids = {
                int(card_id)
                for card_id in excluded_text.split(",")
                if card_id.strip()
            }
        except ValueError:
            return jsonify(error="Invalid excluded card IDs."), 400

    # Get flashcards from the student's own deck
    if force:
        rows = execute_query(
            db,
            """
            SELECT * FROM cards
            WHERE deck_id = ?
            """,
            (deck_id,)
        ).fetchall()
    else:
        rows = execute_query(
            db,
            """
            SELECT * FROM cards
            WHERE deck_id = ? AND due <= ?
            """,
            (deck_id, time.time())
        ).fetchall()

    # Remove cards already answered in this quiz attempt
    rows = [
        row for row in rows
        if row["id"] not in excluded_ids
    ]

    # No cards left to quiz
    if not rows:
        return jsonify(done=True)

    # Prioritize flashcards the student knows the least
    lowest_box = min(row["box"] for row in rows)

    pool = [
        row for row in rows
        if row["box"] == lowest_box
    ]

    # Avoid repeating the previous flashcard when possible
    if len(pool) > 1 and last_id:
        pool = [
            row for row in pool
            if row["id"] != last_id
        ]

    # Randomly choose a flashcard
    pick = random.choice(pool)

    return jsonify(
        done=False,
        id=pick["id"],
        term=pick["term"]
    )


@app.route("/api/cards/<int:card_id>/answer", methods=["POST"])
@login_required
def check_answer(card_id):
    db = get_db()

    # Find the flashcard only if it belongs to the student
    card = execute_query(
        db,
        """
        SELECT c.*
        FROM cards c
        JOIN decks d ON c.deck_id = d.id
        WHERE c.id = ? AND d.user_id = ?
        """,
        (card_id, current_user.id)
    ).fetchone()

    # Don't reveal flashcards belonging to other students
    if card is None:
        return jsonify(
            error="Flashcard not found."
        ), 404

    # Get the student's answer
    data = request.get_json(silent=True) or {}

    # Compare their answer with the correct definition
    score = quiz.grade(
        data.get("answer", ""),
        card["definition"]
    )

    return jsonify(
        score=round(score, 2),
        passed=score >= quiz.PASS_SCORE,
        definition=card["definition"]
    )



@app.route("/api/cards/<int:card_id>/result", methods=["POST"])
@login_required

def save_result(card_id):
    db = get_db()

    # Find the flashcard only if it belongs to this student
    card = execute_query(
        db,
        """
        SELECT c.*
        FROM cards c
        JOIN decks d ON c.deck_id = d.id
        WHERE c.id = ? AND d.user_id = ?
        """,
        (card_id, current_user.id)
    ).fetchone()

    if card is None:
        return jsonify(error="Flashcard not found."), 404

    # Get the student's quiz result
    data = request.get_json(silent=True) or {}
    was_right = bool(data.get("correct"))

    # Calculate the next review schedule
    new_box = quiz.next_box(card["box"], was_right)

    # Update the student's flashcard progress
    execute_query(
        db,
        """
        UPDATE cards
        SET box = ?,
            due = ?,
            times_seen = times_seen + 1,
            times_right = times_right + ?
        WHERE id = ?
        """,
        (
            new_box,
            quiz.due_time(new_box),
            1 if was_right else 0,
            card_id
        )
    )

    # Load the student's current statistics
    stats = get_stats(db)

    # Update statistics for this answer
    stats["asked"] += 1

    if was_right:
        stats["correct"] += 1
        stats["streak"] += 1
        stats["best"] = max(
            stats["best"],
            stats["streak"]
        )
    else:
        stats["streak"] = 0

    # Save the student's statistics.
    # UPSERT creates the row if it doesn't exist,
    # or updates it if the student already has one.
    execute_query(
        db,
        """
        INSERT INTO stats
            (user_id, asked, correct, streak, best)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (user_id)
        DO UPDATE SET
            asked = excluded.asked,
            correct = excluded.correct,
            streak = excluded.streak,
            best = excluded.best
        """,
        (
            current_user.id,
            stats["asked"],
            stats["correct"],
            stats["streak"],
            stats["best"]
        )
    )

    # Save changes to the database
    db.commit()

    # Return the student's updated statistics
    return jsonify(stats)




@app.route("/api/stats", methods=["GET"])
@login_required
def get_study_stats():
    db = get_db()

    # Load statistics for the logged-in student
    stats = get_stats(db)

    # Return only this student's progress
    return jsonify(
        asked=stats["asked"],
        correct=stats["correct"],
        streak=stats["streak"],
        best=stats["best"]
    )




with app.app_context():
    make_tables()

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")


#  /\_/\
# ( o.o )   keep studying!
#  > ^ <
