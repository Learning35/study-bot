// app.js
// The front end for my study bot. The data is saved in app.py,
// this file just shows the chat and talks to the /api/ routes.

const log = document.getElementById("log");
const chatInput = document.getElementById("chatInput");

let decks = [];
let activeDeck = null;     // the deck I picked
let currentCard = null;    // the card I'm answering right now
let lastCardId = null;     // so the same card doesn't come up twice in a row
let settleMiss = null;     // saves a missed card if I move on without clicking a button
let quizSession = null; // tracks the current quiz attempt

// Start a fresh quiz attempt for the selected deck
function startQuizSession() {
  quizSession = {
    deckId: activeDeck.id,
    answeredIds: new Set(),
    correct: 0,
    total: 0,
    fullDeck: true
  };
}

// Clear quiz progress when switching or changing decks
function resetQuizSession() {
  quizSession = null;
}


const SAMPLE_NOTES = [
  "Stack: last in, first out data structure",
  "Queue: first in, first out data structure",
  "Binary search: repeatedly halves a sorted list to find a target in O(log n) time",
  "Hash table: maps keys to values using a hash function for average O(1) lookup",
  "Linked list: nodes that each store a value and a pointer to the next node",
  "Big O notation: describes how runtime grows as input size grows",
  "Recursion: a function that solves a problem by calling itself on smaller inputs",
  "Merge sort: divide and conquer sort that splits, sorts, and merges in O(n log n)",
].join("\n");


// ---------- talking to the backend ----------

async function api(url, method, body) {
  const options = { method: method || "GET", headers: {} };
  if (body) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  const res = await fetch(url, options);
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.error || "Something went wrong.");
  }
  return data;
}

// wraps a handler so an error shows up in the chat
// instead of only showing in the console
function safely(fn) {
  return async function (...args) {
    try {
      await fn(...args);
    } catch (err) {
      console.error(err);
      say("Hmm, that didn't work: " + err.message);
    }
  };
}


// ---------- chat bubbles ----------

function say(text, who, extraClass) {
  const bubble = document.createElement("div");
  bubble.className = "msg " + (who || "bot") + " " + (extraClass || "");
  bubble.textContent = text;
  log.appendChild(bubble);
  log.scrollTop = log.scrollHeight;
  return bubble;
}

function makeChip(label, onClick) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.textContent = label;
  btn.addEventListener("click", safely(onClick));
  return btn;
}


// ---------- decks and stats ----------

async function loadDecks() {
  decks = await api("/api/decks");

  // keep the same deck picked if it's still there
  if (activeDeck) {
    activeDeck = decks.find((d) => d.id === activeDeck.id) || null;
  }
  if (!activeDeck && decks.length > 0) {
    activeDeck = decks[0];
  }
  drawDecks();
}

function drawDecks() {
  const select = document.getElementById("deckSelect");
  select.textContent = "";

  // no decks yet, so hide the dropdown and Manage button
  const hasDecks = decks.length > 0;
  select.hidden = !hasDecks;
  document.getElementById("manageBtn").hidden = !hasDecks;

  for (const deck of decks) {
    const opt = document.createElement("option");
    opt.value = deck.id;
    opt.textContent = deck.name + " (" + deck.due + " due)";
    if (activeDeck && deck.id === activeDeck.id) opt.selected = true;
    select.appendChild(opt);
  }
}

function drawStats(stats) {
  const percent = stats.asked ? Math.round((stats.correct / stats.asked) * 100) : 0;
  document.getElementById("streakNum").textContent = stats.streak;
  document.getElementById("pctNum").textContent = percent + "%";
}

async function loadStats() {
  const stats = await api("/api/stats");
  drawStats(stats);
  return stats;
}


async function pickDeck(id) {
  if (settleMiss) await settleMiss();

  activeDeck = decks.find((d) => d.id === id);
  currentCard = null;
  lastCardId = null;

  // Don't carry quiz progress into another deck
  resetQuizSession();

  drawDecks();

  say(
    "Switched to " + activeDeck.name + ". " +
    activeDeck.due + " cards due. Type quiz when you're ready."
  );
}


async function deleteDeck(deck) {
  await api("/api/decks/" + deck.id, "DELETE");
  if (activeDeck && activeDeck.id === deck.id) {
    activeDeck = null;
  }
  currentCard = null;
  lastCardId = null;
  await loadDecks();
  await loadStats(); // the streak and accuracy go back to 0 when a deck is deleted
  say('Deleted "' + deck.name + '". ' + (activeDeck ? "Now using " + activeDeck.name + "." : "Make a new deck whenever you're ready."));
  return true;
}

async function addDeck(name, notes) {
  const made = await api("/api/decks", "POST", { name: name, notes: notes });
  activeDeck = { id: made.id };
  currentCard = null;
  lastCardId = null;
  await loadDecks();
  say('Deck "' + made.name + '" is ready with ' + made.cards + (made.cards === 1 ? " card" : " cards") + ". Type quiz to start.");
}


// ---------- quiz flow ----------


async function nextCard(force) {
  if (settleMiss) await settleMiss();

  if (!activeDeck) {
    say("Add a deck first. Paste your notes in the form on the left, one card per line.");
    return;
  }

  // Start a new quiz session if one doesn't exist
  if (!quizSession || quizSession.deckId !== activeDeck.id) {
    startQuizSession();
  }

  // A full-deck quiz includes cards that aren't due yet
  const fullDeck = quizSession.fullDeck;
  let url = "/api/decks/" + activeDeck.id + "/next?force=" + (fullDeck ? 1 : 0);

  // Tell Flask which cards we've already answered
  if (quizSession.answeredIds.size > 0) {
    url += "&exclude=" + Array.from(quizSession.answeredIds).join(",");
  }

  // Avoid showing the previous card when possible
  if (lastCardId) {
    url += "&last=" + lastCardId;
  }

  const data = await api(url);

  // No more cards left in this attempt
  if (data.done) {
    currentCard = null;

    if (quizSession.total === 0) {
      say("This deck doesn't have any cards yet.");
      resetQuizSession();
      return;
    }

    const percent = Math.round(
      (quizSession.correct / quizSession.total) * 100
    );

    say(
      "🎉 Quiz complete!\n" +
      "You answered " + quizSession.total + " flashcards.\n" +
      "Your score: " + quizSession.correct + "/" +
      quizSession.total + " (" + percent + "%)"
    );

    // Retake button
    const row = document.createElement("div");
    row.className = "chip-row";

    row.append(
      makeChip("🔄 Retake Quiz", async () => {
        resetQuizSession();
        lastCardId = null;
        await nextCard(true);
      })
    );

    log.appendChild(row);
    log.scrollTop = log.scrollHeight;

    resetQuizSession();
    return;
  }

  currentCard = data;
  lastCardId = data.id;

  say("What does \"" + data.term + "\" mean? 🤔");
  chatInput.focus();
}


async function saveResult(cardId, correct) {
  const stats = await api("/api/cards/" + cardId + "/result", "POST", { correct: correct });
  drawStats(stats);
  await loadDecks();
}


async function checkAnswer(text) {
  const card = currentCard;
  currentCard = null;

  const result = await api(
    "/api/cards/" + card.id + "/answer",
    "POST",
    { answer: text }
  );

  // Record an answer in the current quiz attempt
  function recordAnswer(correct) {
    if (!quizSession || quizSession.answeredIds.has(card.id)) {
      return;
    }

    quizSession.answeredIds.add(card.id);
    quizSession.total += 1;

    if (correct) {
      quizSession.correct += 1;
    }
  }

  if (result.passed) {
    say(
      "Yes! 🎉 " + card.term + ": " + result.definition,
      "bot",
      "good"
    );

    await saveResult(card.id, true);
    recordAnswer(true);
    await nextCard(false);
    return;
  }

  // Show the correct answer and let the student challenge the grader
  const bubble = say(
    "Almost 😅 " + card.term + ": " + result.definition,
    "bot",
    "bad"
  );

  const row = document.createElement("div");
  row.className = "chip-row";

  let settled = false;

  async function settle(correct, goNext) {
    if (settled) return;

    settled = true;
    settleMiss = null;
    row.remove();

    await saveResult(card.id, correct);
    recordAnswer(correct);

    if (goNext) {
      await nextCard(false);
    }
  }

  row.append(
    makeChip("I was right", () => settle(true, true)),
    makeChip("Next card", () => settle(false, true))
  );

  bubble.appendChild(row);
  log.scrollTop = log.scrollHeight;

  settleMiss = () => settle(false, false);
}



async function skipCard() {
  if (!currentCard) {
    say("Nothing to skip. Type quiz to get a card.");
    return;
  }

  const card = currentCard;
  currentCard = null;

  // Get the correct definition
  const result = await api(
    "/api/cards/" + card.id + "/answer",
    "POST",
    { answer: "" }
  );

  // Show the answer to the student
  say(
    "Skipped 😅 " + card.term + ": " + result.definition,
    "bot",
    "bad"
  );

  // Save the skipped card as incorrect
  await saveResult(card.id, false);

  // Count this card as answered during the current quiz
  if (quizSession && !quizSession.answeredIds.has(card.id)) {
    quizSession.answeredIds.add(card.id);
    quizSession.total += 1;
  }

  // Continue to the next flashcard
  await nextCard(false);
}


async function showStats() {
  const s = await loadStats();
  const percent = s.asked ? Math.round((s.correct / s.asked) * 100) : 0;
  say("Answered " + s.asked + ", got " + s.correct + " right (" + percent + "%). Streak: " + s.streak + ", best: " + s.best + ".");
}

async function clearChat() {
  if (settleMiss) await settleMiss(); // save the missed card first
  log.textContent = "";
  currentCard = null;
  say("Chat cleared! \u2728 Your decks and progress are still here. Type quiz when you're ready.");
}

function showHelp() {
  say(
    "Commands:\n" +
    "quiz: ask me a card\n" +
    "quiz anyway: practice cards that aren't due\n" +
    "skip: show the answer and move on\n" +
    "stats: see your progress\n" +
    "clear: wipe the chat (your decks and progress stay)\n\n" +
    "Answer in your own words. I look for the key terms."
  );
}

async function handleInput(raw) {
  const text = raw.trim();
  if (text === "") return;

  if (text.toLowerCase() === "clear") return clearChat();

  say(text, "user");
  const cmd = text.toLowerCase();

  if (cmd === "help") return showHelp();
  if (cmd === "stats") return showStats();
  if (cmd === "skip" || cmd === "pass") return skipCard();

  if (cmd === "quiz anyway") {
    currentCard = null;
    return nextCard(true);
  }
  if (cmd === "quiz" || cmd === "next" || cmd === "start") {
    currentCard = null;
    return nextCard(false);
  }

  if (currentCard) return checkAnswer(text);
  say("I only know quiz, skip, stats, and help. Type quiz to start.");
}


// ---------- focus timer ----------
// the - and + buttons change the time by 5 minutes

let workSeconds = 25 * 60;
try {
  const saved = Number(localStorage.getItem("studybot-minutes"));
  if (saved >= 5 && saved <= 90) workSeconds = saved * 60;
} catch (e) {}
let secondsLeft = workSeconds;
let timer = null;

function drawClock() {
  const mins = String(Math.floor(secondsLeft / 60)).padStart(2, "0");
  const secs = String(secondsLeft % 60).padStart(2, "0");
  document.getElementById("clock").textContent = mins + ":" + secs;
  document.title = timer ? mins + ":" + secs + " | Study Bot" : "Study Bot";
}

function stopTimer() {
  clearInterval(timer);
  timer = null;
  document.getElementById("timerIcon").textContent = "\u23f1";
}

function changeTime(minutes) {
  const newTotal = Math.min(90 * 60, Math.max(5 * 60, workSeconds + minutes * 60));
  const change = newTotal - workSeconds;
  if (change === 0) return;
  workSeconds = newTotal;
  if (timer) {
    secondsLeft = Math.max(60, secondsLeft + change);
  } else {
    secondsLeft = workSeconds;
  }
  try { localStorage.setItem("studybot-minutes", workSeconds / 60); } catch (e) {}
  drawClock();
}

document.getElementById("timerLess").addEventListener("click", () => changeTime(-5));
document.getElementById("timerMore").addEventListener("click", () => changeTime(5));

document.getElementById("timerBtn").addEventListener("click", () => {
  if (timer) {
    stopTimer();
    drawClock();
    return;
  }
  document.getElementById("timerIcon").textContent = "\u23f8";
  timer = setInterval(() => {
    secondsLeft -= 1;
    if (secondsLeft <= 0) {
      const done = workSeconds / 60;
      secondsLeft = workSeconds;
      stopTimer();
      say(done + " minutes are up! Take a 5 minute break, then come back for a quiz.");
    }
    drawClock();
  }, 1000);
  drawClock();
});

document.getElementById("timerReset").addEventListener("click", () => {
  stopTimer();
  secondsLeft = workSeconds;
  drawClock();
});


// ---------- hooking up the page ----------

document.getElementById("deckForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const msg = document.getElementById("formMsg");
  try {
    await addDeck(
      document.getElementById("deckName").value,
      document.getElementById("deckNotes").value
    );
    msg.textContent = "";
    deckDialog.close();
    document.getElementById("deckName").value = "";
    document.getElementById("deckNotes").value = "";
  } catch (err) {
    msg.textContent = err.message;
  }
});

const deckDialog = document.getElementById("deckDialog");

document.getElementById("newDeckBtn").addEventListener("click", () => {
  document.getElementById("formMsg").textContent = "";
  deckDialog.showModal();
  document.getElementById("deckName").focus();
});

document.getElementById("cancelDeck").addEventListener("click", () => deckDialog.close());

document.getElementById("sampleBtn").addEventListener(
  "click",
  safely(async () => {
    await addDeck("Data structures sample", SAMPLE_NOTES);
    deckDialog.close();
  })
);

document.getElementById("chatForm").addEventListener("submit", (e) => {
  e.preventDefault();
  const value = chatInput.value;
  chatInput.value = "";
  safely(handleInput)(value);
});

document.querySelectorAll(".chips button[data-cmd]").forEach((btn) => {
  btn.addEventListener("click", () => safely(handleInput)(btn.dataset.cmd));
});

document.getElementById("clearBtn").addEventListener("click", safely(clearChat));


// ---------- manage deck (edit name, add cards, delete) ----------

const manageDialog = document.getElementById("manageDialog");

document.getElementById("deckSelect").addEventListener(
  "change",
  safely(() => pickDeck(Number(document.getElementById("deckSelect").value)))
);

document.getElementById("manageBtn").addEventListener("click", () => {
  if (!activeDeck) return;

  document.getElementById("manageTitle").textContent = activeDeck.name;
  document.getElementById("manageCount").textContent =
    activeDeck.total + (activeDeck.total === 1 ? " card" : " cards") + " in this deck";

  document.getElementById("editDeckName").value = activeDeck.name;
  document.getElementById("manageMsg").textContent = "";
  document.getElementById("moreNotes").value = "";

  showConfirm(false);
  manageDialog.showModal();
  loadEditableCards().catch((err) => {
    document.getElementById("editCardMsg").textContent = err.message;
});
  document.getElementById("editDeckName").focus();
});

// Close the Manage Deck window
document.getElementById("closeManage").addEventListener("click", () => {
  manageDialog.close();
});

// Save the updated deck name
document.getElementById("saveDeckName").addEventListener("click", async () => {
  const message = document.getElementById("manageMsg");
  const name = document.getElementById("editDeckName").value.trim();

  if (!name) {
    message.textContent = "Give the deck a name.";
    return;
  }

  try {
    const deckId = activeDeck.id;

    await api("/api/decks/" + deckId, "PUT", {
      name: name
    });

    await loadDecks();

    document.getElementById("manageTitle").textContent = activeDeck.name;
    document.getElementById("editDeckName").value = activeDeck.name;

    message.textContent = "Deck name updated successfully!";
    say('Renamed your deck to "' + activeDeck.name + '".');
  } catch (err) {
    message.textContent = err.message;
  }
});

// Cancel editing and restore the original deck name
document.getElementById("cancelEditDeck").addEventListener("click", () => {
  if (!activeDeck) return;

  document.getElementById("editDeckName").value = activeDeck.name;
  document.getElementById("manageMsg").textContent =
    "Name changes canceled.";
});


 // ---------- edit existing flashcards ----------

let editableCards = [];

// Load all flashcards from the selected deck
async function loadEditableCards() {
  const select = document.getElementById("editCardSelect");

  editableCards = await api(
    "/api/decks/" + activeDeck.id + "/cards"
  );

  select.textContent = "";

  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = "Select a flashcard";
  select.appendChild(placeholder);

  for (const card of editableCards) {
    const option = document.createElement("option");
    option.value = card.id;
    option.textContent = card.term;
    select.appendChild(option);
  }

  clearCardEditor();
}

// Clear the editing fields
function clearCardEditor() {
  document.getElementById("editCardSelect").value = "";
  document.getElementById("editCardTerm").value = "";
  document.getElementById("editCardDefinition").value = "";
  document.getElementById("editCardMsg").textContent = "";
}

// Show the selected flashcard's question and answer
document.getElementById("editCardSelect").addEventListener("change", () => {
  const cardId = Number(
    document.getElementById("editCardSelect").value
  );

  const card = editableCards.find((c) => c.id === cardId);

  document.getElementById("editCardTerm").value =
    card ? card.term : "";

  document.getElementById("editCardDefinition").value =
    card ? card.definition : "";

  document.getElementById("editCardMsg").textContent = "";
});

// Cancel editing
document.getElementById("cancelEditCard").addEventListener("click", () => {
  clearCardEditor();
});

// Save the updated flashcard
document.getElementById("saveEditCard").addEventListener("click", async () => {
  const message = document.getElementById("editCardMsg");

  const cardId = Number(
    document.getElementById("editCardSelect").value
  );

  const term = document.getElementById("editCardTerm").value.trim();
  const definition =
    document.getElementById("editCardDefinition").value.trim();

  if (!cardId) {
    message.textContent = "Select a flashcard first.";
    return;
  }

  if (!term || !definition) {
    message.textContent = "Question and answer cannot be empty.";
    return;
  }

  try {
    await api("/api/cards/" + cardId, "PUT", {
      term: term,
      definition: definition
    });

    await loadEditableCards();

    // Keep the edited flashcard selected
    document.getElementById("editCardSelect").value = String(cardId);
    document.getElementById("editCardTerm").value = term;
    document.getElementById("editCardDefinition").value = definition;

    message.textContent = "Flashcard updated successfully!";

    // Refresh deck counts without deleting quiz statistics
    await loadDecks();

    say("Updated a flashcard in " + activeDeck.name + ".");
  } catch (err) {
    message.textContent = err.message;
  }
});


// Add more flashcards to the selected deck
document.getElementById("addCardsBtn").addEventListener("click", async () => {
  try {
    const result = await api(
      "/api/decks/" + activeDeck.id + "/cards",
      "POST",
      { notes: document.getElementById("moreNotes").value }
    );

    const name = activeDeck.name;
    manageDialog.close();

    await loadDecks();

    say("Added " + result.added + " new cards to " + name + "! \u{1F389}");
  } catch (err) {
    document.getElementById("manageMsg").textContent = err.message;
  }
});

// Show or hide the delete confirmation
function showConfirm(on) {
  document.getElementById("confirmRow").hidden = !on;
  document.getElementById("manageRow").hidden = on;
}

document.getElementById("deleteDeckBtn").addEventListener("click", () => {
  showConfirm(true);
});

document.getElementById("keepDeck").addEventListener("click", () => {
  showConfirm(false);
});

document.getElementById("confirmDelete").addEventListener(
  "click",
  safely(async () => {
    await deleteDeck(activeDeck);
    manageDialog.close();
  })
);

// ---------- phone keyboard ----------
// when the keyboard opens, make the page shorter so the answer box stays visible

if (window.visualViewport) {
  const fitToScreen = () => {
    const vv = window.visualViewport;
    if (vv.scale !== 1) return; // skip this if the page is zoomed in
    document.documentElement.style.setProperty("--app-height", vv.height + "px");
    window.scrollTo(0, 0);
    log.scrollTop = log.scrollHeight;
  };
  window.visualViewport.addEventListener("resize", fitToScreen);
  window.visualViewport.addEventListener("scroll", () => {
    if (window.visualViewport.scale === 1) window.scrollTo(0, 0);
  });
  fitToScreen();
}


// ---------- mascot ----------
// uses robot.png from the static folder as the mascot if it's there

const robotPic = new Image();
robotPic.onload = () => document.body.classList.add("has-robot");
robotPic.src = "/static/robot.png";


// ---------- start ----------

(async function start() {
  drawClock();

  // Check whether the student is already logged in.
  const loggedIn = await checkSession();

  if (!loggedIn) {
    return;
  }

  // Only load student information after authentication.
  try {
    await loadDecks();
    await loadStats();

    say(
      "Welcome back to Study Bot! 🤖 " +
      "Make a deck from your notes and I'll quiz you. " +
      "Type help if you get stuck."
    );
  } catch (err) {
    console.error(err);
    say("I couldn't load your study data. Please try refreshing.");
  }
})();
