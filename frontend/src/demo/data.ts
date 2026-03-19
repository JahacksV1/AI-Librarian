import type { PlanResponse } from '../types/api'
import type { ActivityEntry, ConversationMessage } from '../types/ui'

export const DEMO_PLAN_ID = 'demo-plan-001'

export const demoPlan: PlanResponse = {
  id: DEMO_PLAN_ID,
  session_id: 'demo-session',
  goal: 'Organize invoices by year and client',
  rationale_summary:
    'Current files are flat and inconsistent. Grouping by year and client improves retrieval and reduces naming collisions.',
  status: 'PENDING',
  actions: [
    {
      id: 'a1',
      plan_id: DEMO_PLAN_ID,
      action_type: 'CREATE_FOLDER',
      status: 'PENDING',
      action_payload_json: {
        from_path: '(new)',
        to_path: '/sandbox/invoices/2024/ClientA',
      },
    },
    {
      id: 'a2',
      plan_id: DEMO_PLAN_ID,
      action_type: 'MOVE',
      status: 'PENDING',
      action_payload_json: {
        from_path: '/sandbox/invoices/inv-001.pdf',
        to_path: '/sandbox/invoices/2024/ClientA/inv-001.pdf',
      },
    },
    {
      id: 'a3',
      plan_id: DEMO_PLAN_ID,
      action_type: 'MOVE',
      status: 'APPROVED',
      action_payload_json: {
        from_path: '/sandbox/invoices/inv-002.pdf',
        to_path: '/sandbox/invoices/2024/ClientA/inv-002.pdf',
      },
    },
    {
      id: 'a4',
      plan_id: DEMO_PLAN_ID,
      action_type: 'RENAME',
      status: 'EXECUTED',
      action_payload_json: {
        from_path: '/sandbox/invoices/receipt.pdf',
        to_path: '/sandbox/invoices/2024/ClientB/2024-03_receipt_ClientB.pdf',
      },
    },
  ],
}

export const demoMessages: ConversationMessage[] = [
  {
    id: 'm1',
    role: 'user',
    content: 'Can you organize my invoices folder?',
  },
  {
    id: 'm2',
    role: 'assistant',
    content:
      'I scanned the folder and drafted a safe plan. Please review each action and approve the ones you want me to execute.',
  },
  {
    id: 'm3',
    role: 'tool',
    title: 'Calling scan_folder',
    content: JSON.stringify({ path: '/sandbox/invoices', recursive: true }, null, 2),
  },
  {
    id: 'm4',
    role: 'tool',
    title: 'Result scan_folder',
    content: JSON.stringify({ files: 12, folders: 3, summary: 'Scanned 12 files across 3 folders.' }, null, 2),
  },
]

export function createDemoActivity(now = Date.now()): ActivityEntry[] {
  return [
    { id: 'e1', kind: 'tool_call', text: 'tool_call: scan_folder', at: now - 90_000 },
    { id: 'e2', kind: 'tool_result', text: 'tool_result: scan_folder', at: now - 88_000 },
    { id: 'e3', kind: 'tool_call', text: 'tool_call: propose_plan', at: now - 86_000 },
    { id: 'e4', kind: 'tool_result', text: 'tool_result: propose_plan', at: now - 84_000 },
    { id: 'e5', kind: 'plan', text: 'plan_created: demo-plan-001 (4 actions)', at: now - 82_000 },
    { id: 'e6', kind: 'info', text: 'Waiting for approval.', at: now - 80_000 },
  ]
}

export function isDemoModeEnabled(): boolean {
  const envEnabled = String(import.meta.env.VITE_DEMO_MODE ?? '').toLowerCase() === 'true'
  const queryEnabled = new URLSearchParams(window.location.search).get('demo') === '1'
  return envEnabled || queryEnabled
}
