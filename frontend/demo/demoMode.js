/**
 * Offline demo UI — no backend. Keeps main.js focused on real session flow.
 */

/**
 * @param {object} deps
 * @param {(text: string) => void} deps.addUserMessage
 * @param {() => void} deps.startAssistantMessage
 * @param {(text: string) => void} deps.finalizeAssistantMessage
 * @param {(label: string, data: unknown) => void} deps.addToolMessage
 * @param {(kind: string, line: string) => void} deps.logEvent
 * @param {(plan: object) => void} deps.setPlan
 * @param {(patch: object) => void} deps.setState
 * @param {(input: HTMLTextAreaElement, send: HTMLButtonElement, enabled: boolean, placeholder: string) => void} deps.setComposerState
 * @param {HTMLTextAreaElement} deps.composerInput
 * @param {HTMLButtonElement} deps.composerSend
 */
export function loadDemo(deps) {
  const {
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
  } = deps;

  addUserMessage("Can you organize my invoices folder?");

  startAssistantMessage();
  finalizeAssistantMessage(
    "I'll scan your invoices folder and propose a reorganization plan. Let me take a look..."
  );

  addToolMessage("Using scan_folder", { path: "/sandbox/invoices", recursive: true });
  addToolMessage("Result: scan_folder", {
    files: 12,
    folders: 3,
    summary: "Scanned 12 files across 3 folders.",
  });

  logEvent("tool_call", 'scan_folder(path: "/sandbox/invoices", recursive: true)');
  logEvent("tool_result", "scan_folder — 12 files, 3 folders");
  logEvent("tool_call", 'propose_plan(goal: "Organize invoices by year and client")');
  logEvent("tool_result", "propose_plan — plan created");
  logEvent("plan", "Plan created: demo-plan — 4 actions");

  setPlan({
    id: "demo-plan",
    goal: "Organize invoices by year and client",
    rationale_summary:
      "Files are currently flat in /invoices. Restructuring by year/client folders improves findability.",
    status: "PENDING",
    actions: [
      {
        id: "a1",
        action_type: "CREATE_FOLDER",
        status: "PENDING",
        action_payload_json: { from_path: "(new)", to_path: "/sandbox/invoices/2024/ClientA" },
      },
      {
        id: "a2",
        action_type: "MOVE",
        status: "PENDING",
        action_payload_json: {
          from_path: "/sandbox/invoices/inv-001.pdf",
          to_path: "/sandbox/invoices/2024/ClientA/inv-001.pdf",
        },
      },
      {
        id: "a3",
        action_type: "MOVE",
        status: "APPROVED",
        action_payload_json: {
          from_path: "/sandbox/invoices/inv-002.pdf",
          to_path: "/sandbox/invoices/2024/ClientA/inv-002.pdf",
        },
      },
      {
        id: "a4",
        action_type: "RENAME",
        status: "EXECUTED",
        action_payload_json: {
          from_path: "/sandbox/invoices/receipt.pdf",
          to_path: "/sandbox/invoices/2024/ClientB/2024-03_receipt_ClientB.pdf",
        },
      },
    ],
  });

  setState({ uiState: "awaiting_approval", activePlanId: "demo-plan" });
  setComposerState(composerInput, composerSend, false, "Review the plan above.");
}
