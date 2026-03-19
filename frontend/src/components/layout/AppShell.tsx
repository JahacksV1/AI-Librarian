import { useRef, type ReactNode } from 'react'
import { StatusBar } from './StatusBar'

interface AppShellProps {
  statusLabel: string
  statusTone: string
  onRetry: () => void
  leftPanel: ReactNode
  rightPanel: ReactNode
  bottomPanel: ReactNode
}

export function AppShell({
  statusLabel,
  statusTone,
  onRetry,
  leftPanel,
  rightPanel,
  bottomPanel,
}: AppShellProps) {
  const rootRef = useRef<HTMLDivElement | null>(null)

  const onVerticalResize = (event: React.MouseEvent<HTMLDivElement>) => {
    const root = rootRef.current
    if (!root) return

    const bounds = root.getBoundingClientRect()
    const startX = event.clientX
    const current = parseFloat(getComputedStyle(root).getPropertyValue('--left-panel')) || 42

    const onMove = (moveEvent: MouseEvent) => {
      const delta = ((moveEvent.clientX - startX) / bounds.width) * 100
      const next = Math.min(70, Math.max(30, current + delta))
      root.style.setProperty('--left-panel', `${next}%`)
    }

    const onUp = () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }

    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }

  const onHorizontalResize = (event: React.MouseEvent<HTMLDivElement>) => {
    const root = rootRef.current
    if (!root) return

    const startY = event.clientY
    const current = parseFloat(getComputedStyle(root).getPropertyValue('--bottom-panel')) || 220

    const onMove = (moveEvent: MouseEvent) => {
      const delta = startY - moveEvent.clientY
      const next = Math.min(420, Math.max(120, current + delta))
      root.style.setProperty('--bottom-panel', `${next}px`)
    }

    const onUp = () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }

    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }

  return (
    <div className="app" ref={rootRef}>
      <StatusBar label={statusLabel} tone={statusTone} onRetry={onRetry} />

      <main className="workspace">
        <section className="top-grid">
          <div className="panel">{leftPanel}</div>
          <div className="divider vertical" onMouseDown={onVerticalResize} />
          <div className="panel">{rightPanel}</div>
        </section>

        <div className="divider horizontal" onMouseDown={onHorizontalResize} />

        <section className="panel bottom-panel">{bottomPanel}</section>
      </main>
    </div>
  )
}
