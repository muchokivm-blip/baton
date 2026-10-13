const board = document.getElementById("board");
const logEl = document.getElementById("log");
const who = document.getElementById("who");
const note = document.getElementById("note");
const mins = document.getElementById("mins");
const add = document.getElementById("add");
const newName = document.getElementById("newname");
const msg = document.getElementById("msg");

let resources = [];
let events = [];
let fetchedAt = Date.now();

who.value = localStorage.getItem("batonWho") || "";
who.addEventListener("input", () => {
  localStorage.setItem("batonWho", who.value.trim());
  render();
});

function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
}

function fmt(s) {
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h) return `${h}h ${String(m).padStart(2, "0")}m`;
  return `${m}m ${String(sec).padStart(2, "0")}s`;
}

function ago(ts) {
  const s = Math.max(0, Math.floor(Date.now() / 1000) - ts);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

function explain(detail) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail[0].msg;
  return `${detail.name} is held by ${detail.holder} for another ${fmt(detail.seconds_left)}`;
}

function render() {
  const me = who.value.trim();
  board.replaceChildren();
  if (!resources.length) {
    board.append(el("li", "empty", "No locks yet. Type a name above and press Claim to create one."));
  }
  for (const r of resources) {
    const free = r.holder === null;
    const mine = !free && r.holder === me;
    const row = el("li", "row " + (free ? "free" : mine ? "mine" : "held"));

    const info = el("div", "info");
    info.append(el("div", "name", r.name));
    const line = el("div", "who", free ? "Free" : `Held by ${mine ? "you" : r.holder}`);
    if (r.note) line.append(el("span", "note", r.note));
    info.append(line);
    row.append(info);

    if (!free) {
      const clock = el("div", "clock");
      clock.dataset.until = fetchedAt + r.seconds_left * 1000;
      row.append(clock);
    }

    const btns = el("div", "btns");
    const choices = free
      ? [["claim", "Claim"]]
      : mine
        ? [["extend", "+15 min"], ["release", "Release"]]
        : [["force", "Force release"]];
    for (const [action, label] of choices) {
      const b = el("button", free ? "primary" : "", label);
      b.dataset.action = action;
      b.dataset.name = r.name;
      btns.append(b);
    }
    row.append(btns);
    board.append(row);
  }

  logEl.replaceChildren(
    ...events.map((e) => {
      const li = el("li");
      const when = el("time", "", ago(e.at));
      li.append(el("b", "", e.holder), ` ${e.action} `, el("b", "", e.name), when);
      return li;
    })
  );
  tick();
}

function tick() {
  for (const node of document.querySelectorAll(".clock")) {
    const left = Math.ceil((Number(node.dataset.until) - Date.now()) / 1000);
    if (left <= 0) {
      load();
      return;
    }
    node.textContent = fmt(left);
  }
}

async function load() {
  const [r, e] = await Promise.all([
    fetch("/api/resources").then((x) => x.json()),
    fetch("/api/events").then((x) => x.json()),
  ]);
  resources = r;
  events = e;
  fetchedAt = Date.now();
  render();
}

async function send(name, action, body) {
  const res = await fetch(`/api/resources/${name}/${action}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  msg.textContent = res.ok ? "" : explain((await res.json()).detail);
  await load();
}

function act(action, name) {
  const holder = who.value.trim();
  if (!holder) {
    msg.textContent = "Put your name in first.";
    return;
  }
  if (action === "claim") return send(name, "claim", { holder, minutes: Number(mins.value), note: note.value.trim() });
  if (action === "extend") return send(name, "extend", { holder, minutes: 15 });
  if (action === "release") return send(name, "release", { holder });
  if (confirm(`Release ${name} even though it is not yours?`)) return send(name, "release", { holder, force: true });
}

board.addEventListener("click", (e) => {
  const btn = e.target.closest("button");
  if (btn) act(btn.dataset.action, btn.dataset.name);
});

add.addEventListener("submit", async (e) => {
  e.preventDefault();
  await act("claim", newName.value.trim().toLowerCase());
  if (!msg.textContent) newName.value = "";
});

setInterval(tick, 1000);
setInterval(load, 10000);
load();
