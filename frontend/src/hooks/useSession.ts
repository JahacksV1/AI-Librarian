import { useCallback, useEffect, useState } from 'react'
import { checkHealth, createSession } from '../lib/api'

type SessionStatus = 'connecting' | 'ready' | 'error'

interface UseSessionOptions {
  demoMode?: boolean
}

export function useSession(options: UseSessionOptions = {}) {
  const { demoMode = false } = options

  const [sessionId, setSessionId] = useState<string | null>(null)
  const [status, setStatus] = useState<SessionStatus>('connecting')

  const initialize = useCallback(async () => {
    setStatus('connecting')
    setSessionId(null)

    if (demoMode) {
      setSessionId('demo-session')
      setStatus('ready')
      return
    }

    try {
      const health = await checkHealth()
      if (health.status !== 'ok') {
        throw new Error('Backend health is degraded.')
      }

      const session = await createSession()
      setSessionId(session.id)
      setStatus('ready')
    } catch {
      setStatus('error')
    }
  }, [demoMode])

  useEffect(() => {
    void initialize()
  }, [initialize])

  return {
    sessionId,
    status,
    retry: initialize,
  }
}
