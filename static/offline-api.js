// offline-api.js
// Lets the page work without Flask, like when I open it with Live Server.
// It acts like the /api/ routes in app.py but saves everything in the
// browser (localStorage). Only the main index.html loads this file, so
// it isn't used when I run python app.py.
(function () {
  const DAY = 86400, WAIT = [0, 1, 3, 7, 14], PASS = 0.6;
  const STOP = new Set("a an the of to in on is are was were be and or for with as by it its that this at from".split(" "));
  let db = { decks: [], cards: [], stats: { asked: 0, correct: 0, streak: 0, best: 0 }, nid: 1 };
  try { const s = JSON.parse(localStorage.getItem("sb-preview")); if (s && s.decks) db = s; } catch (e) {}
  const save = () => { try { localStorage.setItem("sb-preview", JSON.stringify(db)); } catch (e) {} };
  const now = () => Date.now() / 1000;
  const chop = (w) => { for (const e of ["ing", "ed", "es", "s"]) if (w.endsWith(e) && w.length > e.length + 2) return w.slice(0, -e.length); return w; };
  const words = (t) => t.toLowerCase().replace(/[^a-z0-9 ]/g, " ").split(/\s+/).filter((w) => w && !STOP.has(w)).map(chop);
  const grade = (a, real) => { const need = new Set(words(real)); if (!need.size) return 0; const got = new Set(words(a)); let n = 0; need.forEach((w) => got.has(w) && n++); return n / need.size; };
  const parse = (text) => text.split("\n").map((l) => l.trim()).filter(Boolean).map((l) => l.match(/^(.+?)\s*(?::|\s[-\u2013]\s)\s*(.+)$/)).filter(Boolean).map((m) => [m[1], m[2]]);
  const reply = (data, status = 200) => new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });

  window.fetch = async (url, opt = {}) => {
    const method = (opt.method || "GET").toUpperCase();
    const body = opt.body ? JSON.parse(opt.body) : {};
    const u = new URL(url, location.href);
    const path = u.pathname.replace(/^.*?(\/api\/)/, "/api/");
    let m;
    if (path === "/api/decks" && method === "GET")
      return reply(db.decks.map((d) => { const cs = db.cards.filter((c) => c.deck === d.id); return { id: d.id, name: d.name, total: cs.length, due: cs.filter((c) => c.due <= now()).length }; }));
    if (path === "/api/decks" && method === "POST") {
      const name = (body.name || "").trim().slice(0, 40);
      if (!name) return reply({ error: "Give the deck a name." }, 400);
      const cards = parse(body.notes || "");
      if (!cards.length) return reply({ error: "No cards found. Write one per line as term: definition." }, 400);
      const id = db.nid++; db.decks.push({ id, name });
      cards.forEach(([term, def]) => db.cards.push({ id: db.nid++, deck: id, term, def, box: 0, due: 0 }));
      save(); return reply({ id, name, cards: cards.length }, 201);
    }
    if ((m = path.match(/^\/api\/decks\/(\d+)\/cards$/)) && method === "POST") {
      const id = +m[1];
      if (!db.decks.find((d) => d.id === id)) return reply({ error: "That deck doesn't exist anymore." }, 404);
      const cards = parse(body.notes || "");
      if (!cards.length) return reply({ error: "No cards found. Write one per line as term: definition." }, 400);
      cards.forEach(([term, def]) => db.cards.push({ id: db.nid++, deck: id, term, def, box: 0, due: 0 }));
      save(); return reply({ added: cards.length }, 201);
    }
    if ((m = path.match(/^\/api\/decks\/(\d+)$/)) && method === "DELETE") {
      const id = +m[1]; db.decks = db.decks.filter((d) => d.id !== id); db.cards = db.cards.filter((c) => c.deck !== id); db.stats.streak = 0; db.stats.asked = 0; db.stats.correct = 0; save(); return reply({ ok: true });
    }
    if ((m = path.match(/^\/api\/decks\/(\d+)\/next$/))) {
      const force = u.searchParams.get("force") === "1", last = +u.searchParams.get("last") || 0;
      const rows = db.cards.filter((c) => c.deck === +m[1] && (force || c.due <= now()));
      if (!rows.length) return reply({ done: true });
      const low = Math.min(...rows.map((c) => c.box)); let pool = rows.filter((c) => c.box === low);
      if (pool.length > 1 && last) pool = pool.filter((c) => c.id !== last);
      const p = pool[Math.floor(Math.random() * pool.length)]; return reply({ done: false, id: p.id, term: p.term });
    }
    if ((m = path.match(/^\/api\/cards\/(\d+)\/answer$/))) {
      const c = db.cards.find((x) => x.id === +m[1]); if (!c) return reply({ error: "That card doesn't exist anymore." }, 404);
      const s = grade(body.answer || "", c.def); return reply({ score: Math.round(s * 100) / 100, passed: s >= PASS, definition: c.def });
    }
    if ((m = path.match(/^\/api\/cards\/(\d+)\/result$/))) {
      const c = db.cards.find((x) => x.id === +m[1]); if (!c) return reply({ error: "That card doesn't exist anymore." }, 404);
      const ok = !!body.correct; c.box = ok ? Math.min(c.box + 1, 4) : 0; c.due = now() + WAIT[c.box] * DAY;
      const s = db.stats; s.asked++; if (ok) { s.correct++; s.streak++; s.best = Math.max(s.best, s.streak); } else s.streak = 0;
      save(); return reply(s);
    }
    if (path === "/api/stats") return reply(db.stats);
    return reply({ error: "Not found" }, 404);
  };
})();
