let rootEl = null;
let handlers = null;
let plan = null;
let locked = false;
let err = "";

export function initPlanPanel(el, h) { rootEl = el; handlers = h; render(); }
export function setPlan(p) { plan = p; err = ""; render(); }
export function setPlanError(msg) { err = msg; render(); }
export function setInteractionsLocked(v) { locked = v; render(); }

export function applyActionOutcome(actionId, outcome) {
  if (!plan?.actions) return;
  const a = plan.actions.find((x) => x.id === actionId);
  if (a) a.status = outcome === "SUCCESS" ? "EXECUTED" : "FAILED";
  render();
}

function render() {
  if (!rootEl) return;

  if (!plan) {
    rootEl.innerHTML = "";
    return;
  }

  const acts = plan.actions || [];
  const approved = acts.filter((a) => a.status === "APPROVED").length;
  const pending = acts.filter((a) => a.status === "PENDING").length;

  rootEl.innerHTML = `
    <h2 class="plan-goal">${e(plan.goal || "Untitled plan")}</h2>
    <p class="plan-rationale">${e(plan.rationale_summary || "")}</p>
    <div class="plan-stats">
      <span class="stat">${acts.length} actions</span>
      <span class="stat">${approved} approved</span>
      <span class="stat">${pending} pending</span>
    </div>
    <div class="plan-controls">
      <button class="btn" data-do="approve-all" ${pending === 0 || locked ? "disabled" : ""}>Approve all</button>
      <button class="btn btn-primary" data-do="execute" ${approved === 0 || locked ? "disabled" : ""}>Execute</button>
    </div>
    <div class="action-list">${acts.map(card).join("")}</div>
    ${err ? `<p class="inline-error">${e(err)}</p>` : ""}
  `;

  for (const btn of rootEl.querySelectorAll("button[data-do]")) {
    btn.addEventListener("click", () => {
      const k = btn.dataset.do, id = btn.dataset.id;
      if (k === "approve" && id) handlers.onApproveAction(id);
      else if (k === "reject" && id) handlers.onRejectAction(id);
      else if (k === "approve-all" && plan) handlers.onApproveAll(plan.id);
      else if (k === "execute" && plan) handlers.onExecute(plan.id);
    });
  }
}

function card(a) {
  const pl = a.action_payload_json || {};
  const from = pl.from_path || "(none)";
  const to = pl.to_path || "(none)";
  const canAct = a.status === "PENDING" && !locked;
  return `
    <div class="action-card">
      <div class="action-card-header">
        <span class="action-type">${e(a.action_type)}</span>
        <span class="badge badge-${a.status.toLowerCase()}">${e(a.status)}</span>
      </div>
      <div class="action-paths"><div>${e(from)}</div><div class="path-to">&rarr; ${e(to)}</div></div>
      ${canAct ? `<div class="action-btns"><button class="btn" data-do="approve" data-id="${a.id}">Approve</button><button class="btn" data-do="reject" data-id="${a.id}">Reject</button></div>` : ""}
    </div>`;
}

function e(s) { return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }
