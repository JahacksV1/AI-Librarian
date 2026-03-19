import type { ActivityEntry as ActivityEntryType } from '../../types/ui'
import { ActivityEntry } from './ActivityEntry'

interface ActivityPanelProps {
  entries: ActivityEntryType[]
}

export function ActivityPanel({ entries }: ActivityPanelProps) {
  return (
    <div className="panel-content activity-panel">
      <div className="panel-header">
        <h2>Agent Activity</h2>
      </div>

      {!entries.length ? (
        <div className="panel-empty">Events will appear here as the agent works.</div>
      ) : (
        <ul className="activity-list">
          {entries.map((entry) => (
            <ActivityEntry key={entry.id} entry={entry} />
          ))}
        </ul>
      )}
    </div>
  )
}
