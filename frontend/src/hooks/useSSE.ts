import { useCallback, useRef, useState } from 'react'
import { executePlan, sendMessage } from '../lib/api'
import { DEMO_PLAN_ID } from '../demo/data'
import { readSSEStream } from '../lib/sse'
import type { SSEEvent, UIState } from '../types/sse'
import type { ConversationMessage } from '../types/ui'

interface UseSSEParams {
  demoMode?: boolean
  initialMessages?: ConversationMessage[]
  initialUiState?: UIState
  onEvent: (event: SSEEvent) => void
  onPlanCreated: (planId: string) => void
  onExecutionComplete: () => void
}

export function useSSE({
  demoMode = false,
  initialMessages = [],
  initialUiState = 'idle',
  onEvent,
  onPlanCreated,
  onExecutionComplete,
}: UseSSEParams) {
  const [messages, setMessages] = useState<ConversationMessage[]>(initialMessages)
  const [uiState, setUiState] = useState<UIState>(initialUiState)
  const [error, setError] = useState<string | null>(null)

  const activeAssistantId = useRef<string | null>(null)
  const uiStateRef = useRef<UIState>('idle')

  const setUiStateSafe = useCallback((next: UIState) => {
    uiStateRef.current = next
    setUiState(next)
  }, [])

  const appendAssistantToken = useCallback((token: string) => {
    const id = activeAssistantId.current
    if (!id) return

    setMessages((prev) =>
      prev.map((msg) => (msg.id === id ? { ...msg, content: msg.content + token } : msg)),
    )
  }, [])

  const routeEvent = useCallback(
    (event: SSEEvent) => {
      onEvent(event)

      switch (event.type) {
        case 'token':
          appendAssistantToken(event.token)
          break
        case 'tool_call':
          setUiStateSafe(event.tool === 'scan_folder' ? 'scanning' : uiStateRef.current)
          setMessages((prev) => [
            ...prev,
            {
              id: crypto.randomUUID(),
              role: 'tool',
              title: `Calling ${event.tool}`,
              content: JSON.stringify(event.args, null, 2),
              payload: event.args,
            },
          ])
          break
        case 'tool_result':
          setMessages((prev) => [
            ...prev,
            {
              id: crypto.randomUUID(),
              role: 'tool',
              title: `Result ${event.tool}`,
              content: JSON.stringify(event.result, null, 2),
              payload: event.result,
            },
          ])
          break
        case 'plan_created':
          setUiStateSafe('awaiting_approval')
          onPlanCreated(event.plan_id)
          break
        case 'action_executed':
          setUiStateSafe('executing')
          break
        case 'execution_complete':
          setUiStateSafe('complete')
          onExecutionComplete()
          break
        case 'message_complete':
          activeAssistantId.current = null
          break
        case 'error':
          setError(event.detail ?? event.message)
          setUiStateSafe('error')
          break
      }
    },
    [appendAssistantToken, onEvent, onExecutionComplete, onPlanCreated, setUiStateSafe],
  )

  const consume = useCallback(
    async (response: Response) => {
      await readSSEStream(response, routeEvent)
    },
    [routeEvent],
  )

  const send = useCallback(
    async (sessionId: string, content: string) => {
      if (!content.trim()) return

      setError(null)
      setUiStateSafe('streaming')

      const assistantId = crypto.randomUUID()
      activeAssistantId.current = assistantId
      setMessages((prev) => [
        ...prev,
        { id: crypto.randomUUID(), role: 'user', content },
        { id: assistantId, role: 'assistant', content: '' },
      ])

      if (demoMode) {
        const demoEvents: SSEEvent[] = [
          { type: 'tool_call', tool: 'scan_folder', args: { path: '/sandbox/invoices', recursive: true } },
          {
            type: 'tool_result',
            tool: 'scan_folder',
            result: { files: 12, folders: 3, summary: 'Scanned 12 files across 3 folders.' },
          },
          { type: 'plan_created', plan_id: DEMO_PLAN_ID, goal: 'Organize invoices by year and client', action_count: 4 },
        ]

        const text = 'I drafted an updated plan based on your request. Please review and approve what you want executed.'
        for (const token of text.split(' ')) {
          routeEvent({ type: 'token', token: `${token} ` })
        }
        for (const event of demoEvents) {
          routeEvent(event)
        }
        routeEvent({ type: 'message_complete', message_id: assistantId, content: text })
        if (uiStateRef.current === 'streaming' || uiStateRef.current === 'scanning') {
          setUiStateSafe('idle')
        }
        return
      }

      try {
        const response = await sendMessage(sessionId, content)
        await consume(response)

        if (uiStateRef.current === 'streaming' || uiStateRef.current === 'scanning') {
          setUiStateSafe('idle')
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to send message')
        setUiStateSafe('error')
      }
    },
    [consume, demoMode, routeEvent, setUiStateSafe],
  )

  const runExecution = useCallback(
    async (planId: string) => {
      setError(null)
      setUiStateSafe('executing')

      if (demoMode) {
        routeEvent({ type: 'action_executed', action_id: 'a1', action_type: 'CREATE_FOLDER', outcome: 'SUCCESS' })
        routeEvent({ type: 'action_executed', action_id: 'a2', action_type: 'MOVE', outcome: 'SUCCESS' })
        routeEvent({ type: 'execution_complete', plan_id: DEMO_PLAN_ID, succeeded: 2, failed: 0 })
        setUiStateSafe('complete')
        return
      }

      try {
        const response = await executePlan(planId)
        await consume(response)
        if (uiStateRef.current === 'executing') {
          setUiStateSafe('idle')
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Execution failed')
        setUiStateSafe('error')
      }
    },
    [consume, demoMode, routeEvent, setUiStateSafe],
  )

  const seedMessages = useCallback((seed: ConversationMessage[]) => {
    setMessages(seed)
  }, [])

  return {
    messages,
    uiState,
    error,
    sendMessage: send,
    runExecution,
    seedMessages,
    setUiState: setUiStateSafe,
  }
}
