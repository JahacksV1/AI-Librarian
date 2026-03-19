import type { PlanResponse } from '../../types/api'
import { ActionRow } from './ActionRow'

interface PlanCardProps {
  plan: PlanResponse
  disabled: boolean
  onApproveAction: (actionId: string) => Promise<void>
  onRejectAction: (actionId: string) => Promise<void>
  onApproveAll: () => Promise<void>
  onExecute: () => Promise<void>
}

export function PlanCard({
  plan,
  disabled,
  onApproveAction,
  onRejectAction,
  onApproveAll,
  onExecute,
}: PlanCardProps) {
  return (
    <div className="panel-content plan-card">
      <div className="panel-header">
        <h2>Current Plan</h2>
        <span className="badge" data-status={plan.status}>{plan.status}</span>
      </div>

      <p className="goal">{plan.goal}</p>
      <p className="rationale">{plan.rationale_summary}</p>

      <ul className="action-list">
        {plan.actions.map((action) => (
          <ActionRow
            key={action.id}
            action={action}
            disabled={disabled}
            onApprove={onApproveAction}
            onReject={onRejectAction}
          />
        ))}
      </ul>

      <div className="panel-actions">
        <button type="button" className="btn" disabled={disabled} onClick={() => void onApproveAll()}>
          Approve All
        </button>
        <button type="button" className="btn" disabled={disabled} onClick={() => void onExecute()}>
          Execute
        </button>
      </div>
    </div>
  )
}
