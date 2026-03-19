import { useMemo, useState } from 'react'
import { AppShell } from './components/layout/AppShell'
import { PlanPanel } from './components/plan/PlanPanel'
import { ConversationPanel } from './components/conversation/ConversationPanel'
import { ActivityPanel } from './components/activity/ActivityPanel'
import { createDemoActivity, demoMessages, demoPlan, isDemoModeEnabled } from './demo/data'
import { useActivity } from './hooks/useActivity'
import { usePlan } from './hooks/usePlan'
import { useSession } from './hooks/useSession'
import { useSSE } from './hooks/useSSE'

function App() {
  const demoMode = isDemoModeEnabled()

  const [activePlanId, setActivePlanId] = useState<string | null>(demoMode ? demoPlan.id : null)
  const { entries, pushEvent, pushNote } = useActivity({
    initialEntries: demoMode ? createDemoActivity() : [],
  })
  const { sessionId, status: sessionStatus, retry } = useSession({ demoMode })
  const {
    plan,
    status: planStatus,
    error: planError,
    approveAll,
    approveAction,
    rejectAction,
    refresh,
    executeApprovedLocally,
  } = usePlan(activePlanId, {
    disableFetch: demoMode,
    initialPlan: demoMode ? demoPlan : null,
    initialStatus: demoMode ? 'ready' : 'idle',
  })

  const {
    messages,
    uiState,
    error: streamError,
    sendMessage,
    runExecution,
  } = useSSE({
    demoMode,
    initialMessages: demoMode ? demoMessages : [],
    initialUiState: demoMode ? 'awaiting_approval' : 'idle',
    onEvent: pushEvent,
    onPlanCreated: (planId) => {
      setActivePlanId(planId)
      void refresh(planId)
    },
    onExecutionComplete: () => {
      if (activePlanId) {
        void refresh(activePlanId)
      }
    },
  })

  const statusLabel = useMemo(() => {
    if (demoMode) return 'Demo Mode'
    if (sessionStatus === 'connecting') return 'Connecting...'
    if (sessionStatus === 'error') return 'Offline'

    const map = {
      idle: 'Ready',
      streaming: 'Thinking...',
      scanning: 'Scanning files...',
      awaiting_approval: 'Awaiting approval',
      executing: 'Executing...',
      complete: 'Done',
      error: 'Error',
      connecting: 'Connecting...',
    } as const

    return map[uiState]
  }, [demoMode, sessionStatus, uiState])

  const disabled = !sessionId || uiState === 'streaming' || uiState === 'executing'

  return (
    <AppShell
      statusLabel={statusLabel}
      statusTone={sessionStatus === 'error' || uiState === 'error' ? 'error' : uiState}
      onRetry={retry}
      leftPanel={
        <PlanPanel
          plan={plan}
          status={planStatus}
          error={planError}
          disabled={disabled}
          onApproveAction={approveAction}
          onRejectAction={rejectAction}
          onApproveAll={approveAll}
          onExecute={async () => {
            if (!activePlanId) return
            pushNote('Execution started.')
            if (demoMode) {
              await executeApprovedLocally()
            }
            await runExecution(activePlanId)
            await refresh(activePlanId)
          }}
        />
      }
      rightPanel={
        <ConversationPanel
          messages={messages}
          disabled={disabled}
          onSend={async (content) => {
            if (!sessionId) {
              pushNote('No session available. Retry connection first.')
              return
            }
            await sendMessage(sessionId, content)
          }}
          error={streamError}
        />
      }
      bottomPanel={<ActivityPanel entries={entries} />}
    />
  )
}

export default App
