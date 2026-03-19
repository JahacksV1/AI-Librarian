import { useCallback, useState } from 'react'
import type { SSEEvent } from '../types/sse'
import type { ActivityEntry } from '../types/ui'

interface UseActivityOptions {
  initialEntries?: ActivityEntry[]
}

export function useActivity(options: UseActivityOptions = {}) {
  const { initialEntries = [] } = options
  const [entries, setEntries] = useState<ActivityEntry[]>(initialEntries)

  const push = useCallback((entry: Omit<ActivityEntry, 'id' | 'at'>) => {
    setEntries((prev) => [
      ...prev,
      {
        id: crypto.randomUUID(),
        at: Date.now(),
        ...entry,
      },
    ])
  }, [])

  const pushEvent = useCallback(
    (event: SSEEvent) => {
      if (event.type === 'token') return

      switch (event.type) {
        case 'tool_call':
          push({ kind: 'tool_call', text: `tool_call: ${event.tool}` })
          break
        case 'tool_result':
          push({ kind: 'tool_result', text: `tool_result: ${event.tool}` })
          break
        case 'plan_created':
          push({ kind: 'plan', text: `plan_created: ${event.plan_id} (${event.action_count} actions)` })
          break
        case 'action_executed':
          push({ kind: 'action', text: `action_executed: ${event.action_type} (${event.outcome})` })
          break
        case 'execution_complete':
          push({ kind: 'action', text: `execution_complete: success=${event.succeeded}, failed=${event.failed}` })
          break
        case 'message_complete':
          push({ kind: 'info', text: 'message_complete' })
          break
        case 'error':
          push({ kind: 'error', text: `${event.message}${event.detail ? ` — ${event.detail}` : ''}` })
          break
      }
    },
    [push],
  )

  const pushNote = useCallback(
    (text: string) => {
      push({ kind: 'info', text })
    },
    [push],
  )

  const seedEntries = useCallback((seed: ActivityEntry[]) => {
    setEntries(seed)
  }, [])

  return { entries, pushEvent, pushNote, seedEntries }
}
