import type { PlanAction } from '../../types/api'

interface ActionRowProps {
  action: PlanAction
  disabled: boolean
  onApprove: (actionId: string) => Promise<void>
  onReject: (actionId: string) => Promise<void>
}

export function ActionRow({ action, disabled, onApprove, onReject }: ActionRowProps) {
  const fromPath = action.action_payload_json.from_path ?? action.action_payload_json.path ?? '(unknown)'
  const toPath = action.action_payload_json.to_path

  return (
    <li className="action-row">
      <div className="action-main">
        <span className="badge" data-status={action.status}>
          {action.status}
        </span>
        <span className="action-type">{action.action_type}</span>
      </div>
      <div className="action-path">{fromPath}{toPath ? ` → ${toPath}` : ''}</div>
      <div className="action-controls">
        <button
          type="button"
          className="btn"
          disabled={disabled}
          onClick={() => void onApprove(action.id)}
        >
          Approve
        </button>
        <button
          type="button"
          className="btn subtle"
          disabled={disabled}
          onClick={() => void onReject(action.id)}
        >
          Reject
        </button>
      </div>
    </li>
  )
}
