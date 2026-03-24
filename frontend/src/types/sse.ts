export type SSEEvent =
  | { type: 'token'; token: string }
  | { type: 'message_complete'; message_id: string; content: string }
  | { type: 'tool_call'; tool: string; args: Record<string, unknown> }
  | { type: 'tool_result'; tool: string; result: Record<string, unknown> }
  | { type: 'plan_created'; plan_id: string; goal: string; action_count: number }
  | { type: 'action_executed'; action_id: string; outcome: string; action_type: string }
  | { type: 'execution_complete'; plan_id: string; succeeded: number; failed: number }
  | { type: 'scan_started'; scan_id: string; root_path: string; scan_depth: string }
  | { type: 'scan_complete'; scan_id: string; file_count: number; folder_count: number; new_files: number; deleted_files: number; categories: Record<string, number>; root_path: string; scan_depth: string; top_folders: string[] }
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
