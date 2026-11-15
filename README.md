# Study Bot

A study app I made with Python (Flask) and JavaScript. You paste your notes
and a chatbot quizzes you on them. Cards you get wrong come back sooner, and
cards you know come back later.

## What it does
- Make a deck from your notes, one card per line like `term: meaning`
- Pick a deck from the dropdown, add more cards, or delete it
- Chat commands: `quiz`, `quiz anyway`, `skip`, `stats`, `clear`, `help`
- Checks your answer for the important words
- If it marks you wrong but you were right, click "I was right"
- Shows your streak and how often you're right
- Focus timer (starts at 25 minutes, you can change it with + and -)
- Works on iPhone, iPad, and laptop

## Built with
Python, Flask, SQLite, JavaScript, HTML/CSS

## Files
- `app.py` - the Flask routes and the database
- `quiz.py` - reads notes, grades answers, and decides when a card comes back
- `templates/index.html`, `static/style.css`, `static/app.js` - what you see on the page

## How to run it
```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python app.py
```
On Mac, use `source venv/bin/activate` instead of the second line.
Then go to http://127.0.0.1:5000

## Without Python
You can also open `index.html` with Live Server in VS Code. It saves your
decks in the browser instead of the database.

## Things to fix later
The grader only looks for words, so it can't tell if an answer says the
opposite thing (like "first in" instead of "last in").

## Ideas for later
- Make cards from notes automatically with an AI API
- Save and load decks as files
- Edit or delete single cards
