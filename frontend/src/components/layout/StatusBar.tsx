interface StatusBarProps {
  label: string
  tone: string
  onRetry: () => void
}

export function StatusBar({ label, tone, onRetry }: StatusBarProps) {
  return (
    <header className="status-bar">
      <div className="status-left">
        <span className="status-pill" data-tone={tone}>
          <span className="status-dot" />
          <span>{label}</span>
        </span>
      </div>
      <button className="btn subtle" type="button" onClick={onRetry}>
        Retry
      </button>
    </header>
  )
}
