/**
 * Application entry: DOM wiring, panels, session UX.
 * Backend I/O lives under ./api/ (backendApi, http, sse, health).
 */
import "./styles.css";
import {
  checkHealth,
  createSession,
  sendMessage,
  getPlan,
  patchAction,
  approveAll,
  executePlan,
} from "./api/backendApi.js";
import { readSSEStream } from "./api/sse.js";
import { isHealthOk, describeHealthFailure } from "./api/health.js";
import { loadDemo } from "./demo/demoMode.js";
import { getState, setState, subscribe } from "./state/store.js";
import { routeEvent } from "./state/router.js";
import { initPlanPanel, setPlan, setPlanError, setInteractionsLocked } from "./panels/plan.js";
import {
  initConversation,
  addUserMessage,
  startAssistantMessage,
  finalizeAssistantMessage,
  addToolMessage,
} from "./panels/conversation.js";
import { initActivity, logEvent } from "./panels/activity.js";
import { setComposerState } from "./panels/composer.js";

const STATUS = {
  initializing: "Connecting...",
  idle: "Ready",
  streaming: "Thinking...",
  scanning: "Scanning files...",
  awaiting_approval: "Awaiting approval",
  executing: "Executing...",
  complete: "Done",
  error: "Offline",
};

const $ = (s) => document.querySelector(s);

const retryBtn = $("#retry-btn");
const statusDot = $("#status-dot");
const statusText = $("#status-text");
const composerInput = $("#composer-input");
const composerSend = $("#composer-send");
const messagesPanel = $("#messages-panel");
const planPanel = $("#plan-panel");
const activityPanel = $("#activity-panel");
const divider = $("#divider");
const hdivider = $("#hdivider");

const ctx = { onPlanCreated: loadPlan, composerInput, composerSend };

// --- Init panels ---

initActivity($("#activity-list"));
initConversation($("#conversation-list"));
initPlanPanel($("#plan-root"), {
  onApproveAction: (id) => patchAndRefresh(id, "APPROVED"),
  onRejectAction: (id) => patchAndRefresh(id, "REJECTED"),
  onApproveAll: async (planId) => {
    try {
      await approveAll(planId);
      setPlan(await getPlan(planId));
    } catch (e) {
      planError("Approve all failed", e);
    }
  },
  onExecute: async (planId) => {
    try {
      setState({ uiState: "executing" });
      setComposerState(composerInput, composerSend, false, "Executing...");
      const res = await executePlan(planId);
      await readSSEStream(res, (evt) => routeEvent(evt, ctx));
      if (getState().uiState === "executing") {
        setState({ uiState: "idle" });
        setComposerState(composerInput, composerSend, true, "Describe what you want to organize...");
      }
    } catch (e) {
      planError("Execution failed", e);
      setState({ uiState: "error" });
    }
  },
});

// --- Toolbar toggles ---

for (const btn of document.querySelectorAll(".toggle-btn")) {
  btn.addEventListener("click", () => {
    const target = document.getElementById(btn.dataset.target);
    if (!target) return;
    const visible = target.style.display !== "none";
    target.style.display = visible ? "none" : "";
    btn.classList.toggle("active", !visible);
    syncDividers();
  });
}

function syncDividers() {
  const msgVis = messagesPanel.style.display !== "none";
  const planVis = planPanel.style.display !== "none";
  const actVis = activityPanel.style.display !== "none";
  divider.style.display = msgVis && planVis ? "" : "none";
  hdivider.style.display = actVis ? "" : "none";
}

// --- Composer ---

composerSend.addEventListener("click", handleSend);
composerInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    handleSend();
  }
});
composerInput.addEventListener("input", () => {
  composerInput.style.height = "";
  composerInput.style.height = Math.min(composerInput.scrollHeight, 120) + "px";
});

// --- Draggable vertical divider ---

makeDraggable(divider, "col-resize", (startX, startY, ev) => {
  const panels = divider.parentElement;
  const totalW = panels.clientWidth;
  const startFlex = messagesPanel.getBoundingClientRect().width / totalW;
  return (moveEv) => {
    const pct = Math.min(0.8, Math.max(0.2, startFlex + (moveEv.clientX - startX) / totalW));
    messagesPanel.style.flex = `${pct} 1 0`;
    planPanel.style.flex = `${1 - pct} 1 0`;
  };
});

// --- Draggable horizontal divider ---

makeDraggable(hdivider, "row-resize", (startX, startY) => {
  const startH = activityPanel.getBoundingClientRect().height;
  return (moveEv) => {
    activityPanel.style.height = Math.min(500, Math.max(80, startH + (startY - moveEv.clientY))) + "px";
  };
});

function makeDraggable(handle, cursor, createMover) {
  handle.addEventListener("mousedown", (e) => {
    e.preventDefault();
    handle.classList.add("active");
    document.body.style.cursor = cursor;
    document.body.style.userSelect = "none";
    const mover = createMover(e.clientX, e.clientY, e);
    const onMove = (ev) => mover(ev);
    const onUp = () => {
      handle.classList.remove("active");
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  });
}

// --- State ---

subscribe((s) => {
  setInteractionsLocked(s.uiState === "executing" || s.uiState === "streaming");
  statusText.textContent = STATUS[s.uiState] || "Ready";
  statusDot.setAttribute("data-state", s.uiState);
  retryBtn.hidden = s.uiState !== "error";
});

retryBtn.addEventListener("click", initSession);
initSession();

// --- Session + messaging ---

async function initSession() {
  setState({ uiState: "initializing", sessionId: null, activePlanId: null });
  setComposerState(composerInput, composerSend, false, "Connecting...");

  try {
    const health = await checkHealth();
    if (!isHealthOk(health)) throw new Error(describeHealthFailure(health));
    const session = await createSession();
    setState({ sessionId: session.id, uiState: "idle" });
    setComposerState(composerInput, composerSend, true, "Describe what you want to organize...");
  } catch (e) {
    setState({ uiState: "error" });
    setComposerState(composerInput, composerSend, false, "Backend offline.");
    loadDemo({
      addUserMessage,
      startAssistantMessage,
      finalizeAssistantMessage,
      addToolMessage,
      logEvent,
      setPlan,
      setState,
      setComposerState,
      composerInput,
      composerSend,
    });
  }
}

async function handleSend() {
  const sid = getState().sessionId;
  const content = composerInput.value.trim();
  if (!sid || !content) return;
  composerInput.value = "";
  composerInput.style.height = "";
  addUserMessage(content);
  startAssistantMessage();
  setState({ uiState: "streaming", activePlanId: null });
  setComposerState(composerInput, composerSend, false, "Thinking...");
  try {
    const res = await sendMessage(sid, content);
    await readSSEStream(res, (evt) => routeEvent(evt, ctx));
    const next = getState().uiState;
    if (next === "streaming" || next === "scanning") {
      setState({ uiState: "idle" });
      setComposerState(composerInput, composerSend, true, "Describe what you want to organize...");
    }
  } catch (e) {
    setState({ uiState: "error" });
    setComposerState(composerInput, composerSend, true, "Describe what you want to organize...");
    logEvent("error", e instanceof Error ? e.message : "Send failed.");
  }
}

async function loadPlan(planId) {
  if (!planId) return;
  try {
    setPlan(await getPlan(planId));
  } catch (e) {
    planError("Plan load failed", e);
  }
}

async function patchAndRefresh(actionId, status) {
  try {
    await patchAction(actionId, status);
    const pid = getState().activePlanId;
    if (pid) setPlan(await getPlan(pid));
  } catch (e) {
    planError("Action update failed", e);
  }
}

function planError(label, e) {
  const msg = e instanceof Error ? e.message : label;
  setPlanError(msg);
  logEvent("error", `${label}: ${msg}`);
}
