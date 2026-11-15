
// auth.js
// Handles student signup, login, logout, and account sessions.

let authMode = "login";

const authScreen = document.getElementById("authScreen");
const studyApp = document.getElementById("studyApp");
const authForm = document.getElementById("authForm");
const authMessage = document.getElementById("authMessage");
const authEmail = document.getElementById("authEmail");
const authPassword = document.getElementById("authPassword");
const confirmPassword = document.getElementById("confirmPassword");
const confirmPasswordGroup = document.getElementById("confirmPasswordGroup");
const passwordHelp = document.getElementById("passwordHelp");
const authSubmit = document.getElementById("authSubmit");

// Switch between login and signup
function setAuthMode(mode) {
  authMode = mode;
  const signingUp = mode === "signup";

  authMessage.textContent = "";

  document.getElementById("authTitle").textContent =
    signingUp ? "Create your account! ✨" : "Welcome back! 👋";

  authSubmit.textContent =
    signingUp ? "Create account 🚀" : "Log in 🚀";

  document.getElementById("loginTab").className =
    signingUp ? "btn" : "btn blue";

  document.getElementById("signupTab").className =
    signingUp ? "btn blue" : "btn";

  // Only show signup requirements during signup
  passwordHelp.hidden = !signingUp;
  confirmPasswordGroup.hidden = !signingUp;
  confirmPassword.required = signingUp;

  authPassword.autocomplete =
    signingUp ? "new-password" : "current-password";

  authPassword.minLength = signingUp ? 12 : 0;
  authPassword.maxLength = signingUp ? 128 : 524288;

  // Clear confirmation when switching tabs
  confirmPassword.value = "";

  // Reset password visibility
  setPasswordVisibility(authPassword, "togglePassword", false);
  setPasswordVisibility(
    confirmPassword,
    "toggleConfirmPassword",
    false
  );
}

// Show or hide a password
function setPasswordVisibility(input, buttonId, visible) {
  const button = document.getElementById(buttonId);

  input.type = visible ? "text" : "password";
  button.textContent = visible ? "Hide" : "Show";
  button.setAttribute("aria-pressed", String(visible));
  button.setAttribute(
    "aria-label",
    visible ? "Hide password" : "Show password"
  );
}

// Connect password visibility buttons
function connectPasswordToggle(buttonId, input) {
  document.getElementById(buttonId).addEventListener("click", () => {
    setPasswordVisibility(
      input,
      buttonId,
      input.type === "password"
    );
  });
}

connectPasswordToggle("togglePassword", authPassword);
connectPasswordToggle("toggleConfirmPassword", confirmPassword);

// Show the account screen
function showAuthScreen() {
  studyApp.hidden = true;
  authScreen.hidden = false;
  authPassword.value = "";
  confirmPassword.value = "";
}

// Show the student's dashboard
function showStudyApp(user) {
  authScreen.hidden = true;
  studyApp.hidden = false;

  document.getElementById("accountEmail").textContent =
    user.email;
}

// Reset information belonging to the previous student
function resetStudySession() {
  decks = [];
  activeDeck = null;
  currentCard = null;
  lastCardId = null;
  settleMiss = null;

  document.getElementById("log").textContent = "";
  document.getElementById("deckSelect").textContent = "";

  drawStats({
    asked: 0,
    correct: 0,
    streak: 0,
    best: 0
  });

  drawDecks();
  stopTimer();
  secondsLeft = workSeconds;
  drawClock();

  // Close any open deck dialogs
  for (const dialog of document.querySelectorAll("dialog")) {
    if (dialog.open) {
      dialog.close();
    }
  }
}

// Check whether the student is already logged in
async function checkSession() {
  try {
    const response = await fetch("/api/me", {
      credentials: "same-origin"
    });

    if (!response.ok) {
      throw new Error("Could not check your login session.");
    }

    const data = await response.json();

    if (data.authenticated && data.user) {
      showStudyApp(data.user);
      return true;
    }

    showAuthScreen();
    return false;

  } catch (error) {
    console.error("Session check failed:", error);
    showAuthScreen();

    authMessage.textContent =
      "Couldn't connect to Study Bot. Please try again.";

    return false;
  }
}

// Load the student's personal dashboard
async function loadStudentDashboard(user) {
  resetStudySession();

  await loadDecks();
  await loadStats();

  showStudyApp(user);

  say(
    "Welcome to Study Bot! 🤖 " +
    "Make a deck from your notes and I'll quiz you. " +
    "Type help if you get stuck."
  );
}

// Handle login and signup
authForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  authMessage.textContent = "";

  const email = authEmail.value.trim().toLowerCase();
  const password = authPassword.value;

  // Check password requirements before signup
  if (authMode === "signup") {
    if (password.length < 12 || password.length > 128) {
      authMessage.textContent =
        "Your password must be between 12 and 128 characters.";
      return;
    }

    if (password !== confirmPassword.value) {
      authMessage.textContent =
        "Your passwords don't match. Please try again.";
      return;
    }
  }

  const endpoint =
    authMode === "signup" ? "/api/signup" : "/api/login";

  authSubmit.disabled = true;

  try {
    const response = await fetch(endpoint, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ email, password })
    });

    const data = await response.json();

    if (!response.ok) {
      if (response.status === 409) {
        throw new Error(
          "This email already has an account. Switch to Log in instead."
        );
      }

      throw new Error(data.error || "Something went wrong.");
    }

    // Confirm that Flask created the login session
    const sessionResponse = await fetch("/api/me", {
      credentials: "same-origin"
    });

    if (!sessionResponse.ok) {
      throw new Error("Could not verify your login.");
    }

    const sessionData = await sessionResponse.json();

    if (!sessionData.authenticated || !sessionData.user) {
      throw new Error(
        "Your account was created, but we couldn't log you in. Try logging in."
      );
    }

    authPassword.value = "";
    confirmPassword.value = "";

    await loadStudentDashboard(sessionData.user);

  } catch (error) {
    console.error(error);
    authMessage.textContent = error.message;
  } finally {
    authSubmit.disabled = false;
  }
});

// Handle logout
document.getElementById("logoutBtn").addEventListener("click", async () => {
  const logoutButton = document.getElementById("logoutBtn");
  logoutButton.disabled = true;

  try {
    const response = await fetch("/api/logout", {
      method: "POST",
      credentials: "same-origin"
    });

    if (!response.ok) {
      const data = await response.json();
      throw new Error(data.error || "Could not log out.");
    }

    resetStudySession();
    authForm.reset();
    setAuthMode("login");
    showAuthScreen();

  } catch (error) {
    console.error(error);
    say("Couldn't log out: " + error.message);
  } finally {
    logoutButton.disabled = false;
  }
});

// Login and signup tabs
document.getElementById("loginTab").addEventListener("click", () => {
  setAuthMode("login");
});

document.getElementById("signupTab").addEventListener("click", () => {
  setAuthMode("signup");
});

// Set the default account screen
setAuthMode("login");
