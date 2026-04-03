export interface ConversationMessage {
  id: string
  role: 'user' | 'assistant' | 'tool'
  content: string
  title?: string
  payload?: unknown
  toolName?: string
  isResult?: boolean
}

export interface ActivityEntry {
  id: string
  kind: 'info' | 'tool_call' | 'tool_result' | 'plan' | 'action' | 'error'
  text: string
  at: number
}
