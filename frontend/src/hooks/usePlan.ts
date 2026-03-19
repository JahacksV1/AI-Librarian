import { useCallback, useEffect, useState } from 'react'
import { approveAll, getPlan, patchAction } from '../lib/api'
import type { PlanResponse } from '../types/api'

type PlanStatus = 'idle' | 'loading' | 'ready' | 'error'

interface UsePlanOptions {
  disableFetch?: boolean
  initialPlan?: PlanResponse | null
  initialStatus?: PlanStatus
}

export function usePlan(planId: string | null, options: UsePlanOptions = {}) {
  const { disableFetch = false, initialPlan = null, initialStatus = 'idle' } = options

  const [plan, setPlan] = useState<PlanResponse | null>(initialPlan)
  const [status, setStatus] = useState<PlanStatus>(initialStatus)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(
    async (id: string) => {
      if (disableFetch) return

      setStatus('loading')
      setError(null)

      try {
        const next = await getPlan(id)
        setPlan(next)
        setStatus('ready')
      } catch (err) {
        setStatus('error')
        setError(err instanceof Error ? err.message : 'Failed to load plan')
      }
    },
    [disableFetch],
  )

  useEffect(() => {
    if (disableFetch) return
    if (!planId) return
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refresh(planId)
  }, [disableFetch, planId, refresh])

  const approveAction = useCallback(
    async (actionId: string) => {
      if (!planId && !disableFetch) return

      if (disableFetch) {
        setPlan((prev) => {
          if (!prev) return prev
          return {
            ...prev,
            actions: prev.actions.map((action) =>
              action.id === actionId ? { ...action, status: 'APPROVED' } : action,
            ),
          }
        })
        return
      }

      await patchAction(actionId, 'APPROVED')
      await refresh(planId as string)
    },
    [disableFetch, planId, refresh],
  )

  const rejectAction = useCallback(
    async (actionId: string) => {
      if (!planId && !disableFetch) return

      if (disableFetch) {
        setPlan((prev) => {
          if (!prev) return prev
          return {
            ...prev,
            actions: prev.actions.map((action) =>
              action.id === actionId ? { ...action, status: 'REJECTED' } : action,
            ),
          }
        })
        return
      }

      await patchAction(actionId, 'REJECTED')
      await refresh(planId as string)
    },
    [disableFetch, planId, refresh],
  )

  const approveAllActions = useCallback(async () => {
    if (!planId && !disableFetch) return

    if (disableFetch) {
      setPlan((prev) => {
        if (!prev) return prev
        return {
          ...prev,
          actions: prev.actions.map((action) =>
            action.status === 'PENDING' ? { ...action, status: 'APPROVED' } : action,
          ),
          status: 'APPROVED',
        }
      })
      return
    }

    await approveAll(planId as string)
    await refresh(planId as string)
  }, [disableFetch, planId, refresh])

  const executeApprovedLocally = useCallback(async () => {
    setPlan((prev) => {
      if (!prev) return prev

      const nextActions = prev.actions.map((action) =>
        action.status === 'APPROVED' ? { ...action, status: 'EXECUTED' } : action,
      )
      return {
        ...prev,
        status: 'EXECUTED',
        actions: nextActions,
      }
    })
  }, [])

  const setDemoPlan = useCallback((seedPlan: PlanResponse) => {
    setPlan(seedPlan)
    setStatus('ready')
    setError(null)
  }, [])

  return {
    plan,
    status,
    error,
    refresh,
    approveAction,
    rejectAction,
    approveAll: approveAllActions,
    executeApprovedLocally,
    setDemoPlan,
  }
}
