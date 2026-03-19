let listEl = null;
let activeEl = null;

export function initConversation(el) { listEl = el; }

export function addUserMessage(content) { bubble("message-user", content); }

export function startAssistantMessage() { activeEl = bubble("message-assistant", ""); }

export function appendToken(token) {
  if (!activeEl) startAssistantMessage();
  activeEl.textContent += token;
  scroll();
}

export function finalizeAssistantMessage(content) {
  if (!activeEl) startAssistantMessage();
  if (content) activeEl.textContent = content;
  activeEl = null;
}

export function addToolMessage(title, payload) {
  if (!listEl) return;
  const el = document.createElement("div");
  el.className = "message message-tool";
  el.innerHTML = `<details><summary>${esc(title)}</summary><pre>${esc(JSON.stringify(payload, null, 2))}</pre></details>`;
  listEl.appendChild(el);
  scroll();
}

function clearEmpty() {
  const empty = document.getElementById("messages-empty");
  if (empty) empty.remove();
}

function bubble(cls, text) {
  if (!listEl) return null;
  clearEmpty();
  const el = document.createElement("div");
  el.className = `message ${cls}`;
  el.textContent = text;
  listEl.appendChild(el);
  scroll();
  return el;
}

function scroll() { if (listEl) listEl.scrollTop = listEl.scrollHeight; }
function esc(s) { return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }
