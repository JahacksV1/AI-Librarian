import type { PlanResponse } from '../../types/api'
import { PlanCard } from './PlanCard'

interface PlanPanelProps {
  plan: PlanResponse | null
  status: string
  error: string | null
  disabled: boolean
  onApproveAction: (actionId: string) => Promise<void>
  onRejectAction: (actionId: string) => Promise<void>
  onApproveAll: () => Promise<void>
  onExecute: () => Promise<void>
}

export function PlanPanel({
  plan,
  status,
  error,
  disabled,
  onApproveAction,
  onRejectAction,
  onApproveAll,
  onExecute,
}: PlanPanelProps) {
  if (error) {
    return (
      <div className="plan-panel-root">
        <div className="panel-empty">Plan error: {error}</div>
      </div>
    )
  }

  if (!plan) {
    return (
      <div className="plan-panel-root plan-panel-root--empty">
        <div className="panel-empty">{status === 'loading' ? 'Loading plan...' : 'No plan yet.'}</div>
      </div>
    )
  }

  return (
    <div className="plan-panel-root">
      <PlanCard
        plan={plan}
        disabled={disabled}
        onApproveAction={onApproveAction}
        onRejectAction={onRejectAction}
        onApproveAll={onApproveAll}
        onExecute={onExecute}
      />
    </div>
  )
}
