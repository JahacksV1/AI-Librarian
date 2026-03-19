import { logEvent } from "../panels/activity.js";
import { appendToken, addToolMessage, finalizeAssistantMessage } from "../panels/conversation.js";
import { applyActionOutcome } from "../panels/plan.js";
import { setComposerState } from "../panels/composer.js";
import { getState, setState } from "./store.js";

export function routeEvent(event, ctx) {
  switch (event.type) {
    case "token":
      appendToken(event.token || "");
      return;

    case "tool_call":
      logEvent("tool_call", `${event.tool}(${fmtArgs(event.args)})`);
      addToolMessage(`Using ${event.tool}`, event.args);
      if (event.tool === "scan_folder") {
        setState({ uiState: "scanning" });
        setComposerState(ctx.composerInput, ctx.composerSend, false, "Scanning files...");
      }
      return;

    case "tool_result":
      logEvent("tool_result", `${event.tool} — ${summarize(event.result)}`);
      addToolMessage(`Result: ${event.tool}`, event.result);
      return;

    case "plan_created":
      logEvent("plan", `Plan created: ${event.plan_id?.slice(0, 8)} — ${event.action_count} actions`);
      setState({ activePlanId: event.plan_id, uiState: "awaiting_approval" });
      setComposerState(ctx.composerInput, ctx.composerSend, false, "Review the plan.");
      ctx.onPlanCreated(event.plan_id);
      return;

    case "action_executed":
      logEvent("action", `${event.action_type} — ${event.outcome}`);
      applyActionOutcome(event.action_id, event.outcome);
      return;

    case "execution_complete":
      logEvent("complete", `${event.succeeded} succeeded, ${event.failed} failed`);
      setState({ uiState: "idle" });
      setComposerState(ctx.composerInput, ctx.composerSend, true, "Ask AIJAH to organize files...");
      return;

    case "message_complete":
      finalizeAssistantMessage(event.content || "");
      if (!getState().activePlanId) {
        setState({ uiState: "idle" });
        setComposerState(ctx.composerInput, ctx.composerSend, true, "Ask AIJAH to organize files...");
      }
      return;

    case "error":
      logEvent("error", `${event.message}${event.detail ? ` — ${event.detail}` : ""}`);
      setState({ uiState: "error" });
      setComposerState(ctx.composerInput, ctx.composerSend, true, "Ask AIJAH to organize files...");
      return;
  }
}

function fmtArgs(args) {
  if (!args || typeof args !== "object") return "";
  return Object.entries(args).map(([k, v]) => `${k}: ${JSON.stringify(v)}`).join(", ");
}

function summarize(r) {
  if (!r || typeof r !== "object") return "ok";
  const f = Array.isArray(r.files) ? r.files.length : null;
  const d = Array.isArray(r.folders) ? r.folders.length : null;
  if (f !== null || d !== null) return `${f ?? 0} files, ${d ?? 0} folders`;
  if (r.plan_id) return `plan ${r.plan_id.slice(0, 8)}`;
  return "done";
}
