export type SSEEvent =
  | { type: 'token'; token: string }
  | { type: 'message_complete'; message_id: string; content: string }
  | { type: 'tool_call'; tool: string; args: Record<string, unknown> }
  | { type: 'tool_result'; tool: string; result: Record<string, unknown> }
  | { type: 'plan_created'; plan_id: string; goal: string; action_count: number }
  | { type: 'action_executed'; action_id: string; outcome: string; action_type: string }
  | { type: 'execution_complete'; plan_id: string; succeeded: number; failed: number }
  | { type: 'error'; message: string; detail?: string }

export type UIState =
  | 'connecting'
  | 'idle'
  | 'streaming'
  | 'scanning'
  | 'awaiting_approval'
  | 'executing'
  | 'complete'
  | 'error'
