export interface ConversationMessage {
  id: string
  role: 'user' | 'assistant' | 'tool'
  content: string
  title?: string
  payload?: unknown
}

export interface ActivityEntry {
  id: string
  kind: 'info' | 'tool_call' | 'tool_result' | 'plan' | 'action' | 'error'
  text: string
  at: number
}
