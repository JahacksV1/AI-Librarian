import type { SessionResponse } from '../../types/api'

interface SessionListProps {
  sessions: SessionResponse[]
  activeSessionId: string | null
  onSelect: (sessionId: string) => Promise<void>
  onNew: () => Promise<void>
}

function formatTime(iso: string | null): string {
  if (!iso) return ''
  const date = new Date(iso)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMins = Math.floor(diffMs / 60_000)

  if (diffMins < 1) return 'just now'
  if (diffMins < 60) return `${diffMins}m ago`
  const diffHours = Math.floor(diffMins / 60)
  if (diffHours < 24) return `${diffHours}h ago`
  const diffDays = Math.floor(diffHours / 24)
  if (diffDays < 7) return `${diffDays}d ago`
  return date.toLocaleDateString()
}

export function SessionList({ sessions, activeSessionId, onSelect, onNew }: SessionListProps) {
  return (
    <div className="session-list">
      <div className="session-list-header">
        <h3>Sessions</h3>
        <button type="button" className="btn session-new-btn" onClick={() => void onNew()}>
          + New
        </button>
      </div>

      <ul className="session-items">
        {sessions.map((session) => {
          const isActive = session.id === activeSessionId
          return (
            <li key={session.id}>
              <button
                type="button"
                className={`session-item${isActive ? ' active' : ''}`}
                disabled={isActive}
                onClick={() => void onSelect(session.id)}
              >
                <span className="session-title">
                  {session.title || 'Untitled session'}
                </span>
                <span className="session-meta">
                  <span className="badge" data-status={session.status}>
                    {session.status}
                  </span>
                  <span className="session-time">{formatTime(session.updated_at)}</span>
                </span>
              </button>
            </li>
          )
        })}

        {sessions.length === 0 && (
          <li className="session-empty">No previous sessions</li>
        )}
      </ul>
    </div>
  )
}
