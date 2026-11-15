
from app import app
import uuid

# Generate unique test accounts
test_id = uuid.uuid4().hex[:8]

email_a = f"student_a_{test_id}@example.com"
email_b = f"student_b_{test_id}@example.com"

password = "StudyBotTest123!"

# Create two independent test clients
student_a = app.test_client()
student_b = app.test_client()
guest = app.test_client()

# Create two separate student accounts
response_a = student_a.post("/api/signup", json={
    "email": email_a,
    "password": password
})

response_b = student_b.post("/api/signup", json={
    "email": email_b,
    "password": password
})

assert response_a.status_code == 201, response_a.get_json()
assert response_b.status_code == 201, response_b.get_json()

print("PASS: Two student accounts created")

# Student A creates a flashcard deck
response = student_a.post("/api/decks", json={
    "name": "Student A Test Deck",
    "notes": "Python: A programming language"
})

assert response.status_code == 201, response.get_json()

deck_id = response.get_json()["id"]

print("PASS: Student A created a deck")

# Student B should not see Student A's deck
response = student_b.get("/api/decks")

assert response.status_code == 200, response.get_json()
assert all(
    deck["id"] != deck_id
    for deck in response.get_json()
)

print("PASS: Student B cannot see Student A's deck")

# Student B cannot study Student A's deck
response = student_b.get(f"/api/decks/{deck_id}/next")

assert response.status_code == 404

print("PASS: Student B cannot study Student A's deck")

# Student B cannot add cards to Student A's deck
response = student_b.post(
    f"/api/decks/{deck_id}/cards",
    json={"notes": "Secret: Test"}
)

assert response.status_code == 404

print("PASS: Student B cannot modify Student A's deck")

# Student B cannot delete Student A's deck
response = student_b.delete(f"/api/decks/{deck_id}")

assert response.status_code == 404

print("PASS: Student B cannot delete Student A's deck")

# Check each student's starting statistics
stats_a = student_a.get("/api/stats")
stats_b = student_b.get("/api/stats")

assert stats_a.status_code == 200, stats_a.get_json()
assert stats_b.status_code == 200, stats_b.get_json()

starting_stats = {
    "asked": 0,
    "correct": 0,
    "streak": 0,
    "best": 0
}

assert stats_a.get_json() == starting_stats
assert stats_b.get_json() == starting_stats

print("PASS: Both students have their own starting statistics")

# Student A retrieves their own flashcard
response = student_a.get(
    f"/api/decks/{deck_id}/next?force=1"
)

assert response.status_code == 200, response.get_json()
assert response.get_json()["done"] is False

card_id = response.get_json()["id"]

print("PASS: Student A can access their own flashcard")

# Student B cannot check Student A's flashcard answer
response = student_b.post(
    f"/api/cards/{card_id}/answer",
    json={"answer": "A programming language"}
)

assert response.status_code == 404

print("PASS: Student B cannot access Student A's answer")

# Student B cannot modify Student A's quiz result
response = student_b.post(
    f"/api/cards/{card_id}/result",
    json={"correct": True}
)

assert response.status_code == 404

print("PASS: Student B cannot change Student A's quiz result")

# Guests cannot access private flashcards
response = guest.post(
    f"/api/cards/{card_id}/answer",
    json={"answer": "Python"}
)

assert response.status_code == 401

print("PASS: Guests cannot access private flashcards")

# Student A saves their own quiz result
response = student_a.post(
    f"/api/cards/{card_id}/result",
    json={"correct": True}
)

assert response.status_code == 200, response.get_json()

print("PASS: Student A can save their own quiz result")

# Verify Student A's statistics changed
stats_a = student_a.get("/api/stats")
stats_b = student_b.get("/api/stats")

assert stats_a.status_code == 200
assert stats_b.status_code == 200

assert stats_a.get_json() == {
    "asked": 1,
    "correct": 1,
    "streak": 1,
    "best": 1
}

# Verify Student B's statistics remain unchanged
assert stats_b.get_json() == starting_stats

print("PASS: Student A's statistics updated correctly")
print("PASS: Student B's statistics remained unchanged")

print("\nAll account and flashcard security tests passed!")
