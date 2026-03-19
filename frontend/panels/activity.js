let listEl = null;

const BADGES = {
  tool_call:   { label: "CALL",   cls: "badge-call" },
  tool_result: { label: "RESULT", cls: "badge-result" },
  plan:        { label: "PLAN",   cls: "badge-plan" },
  action:      { label: "ACTION", cls: "badge-action" },
  complete:    { label: "DONE",   cls: "badge-done" },
  error:       { label: "ERROR",  cls: "badge-error" },
};

export function initActivity(el) { listEl = el; }

export function logEvent(type, content) {
  if (!listEl) return;
  const empty = document.getElementById("activity-empty");
  if (empty) empty.remove();

  const b = BADGES[type] || { label: type.toUpperCase(), cls: "" };
  const t = new Date();
  const time = `${pad(t.getHours())}:${pad(t.getMinutes())}:${pad(t.getSeconds())}`;

  const row = document.createElement("div");
  row.className = "activity-row";
  row.innerHTML = `<span class="evt-badge ${b.cls}">${b.label}</span><span class="evt-content"><code>${esc(content)}</code></span><span class="evt-time">${time}</span>`;
  listEl.appendChild(row);
  listEl.scrollTop = listEl.scrollHeight;
}

function pad(n) { return String(n).padStart(2, "0"); }
function esc(s) { return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }
