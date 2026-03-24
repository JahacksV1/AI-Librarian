interface StatusBarProps {
  label: string
  tone: string
  onRetry: () => void
  /** Shown on the button; e.g. "Reconnect" vs "Clear error" */
  retryLabel?: string
}

export function StatusBar({ label, tone, onRetry, retryLabel = 'Retry' }: StatusBarProps) {
  return (
    <header className="status-bar">
      <div className="status-left">
        <span className="status-pill" data-tone={tone}>
          <span className="status-dot" />
          <span>{label}</span>
        </span>
      </div>
      <button className="btn subtle" type="button" onClick={onRetry}>
        {retryLabel}
      </button>
    </header>
  )
}
