import type { ActivityEntry as ActivityEntryType } from '../../types/ui'

interface ActivityEntryProps {
  entry: ActivityEntryType
}

const SYMBOL_BY_KIND: Record<ActivityEntryType['kind'], string> = {
  info: '•',
  tool_call: '→',
  tool_result: '←',
  plan: 'P',
  action: '✓',
  error: '✗',
}

export function ActivityEntry({ entry }: ActivityEntryProps) {
  const time = new Date(entry.at).toLocaleTimeString()
  return (
    <li className={`activity-entry kind-${entry.kind}`}>
      <span className="activity-symbol">{SYMBOL_BY_KIND[entry.kind]}</span>
      <span className="activity-text">{entry.text}</span>
      <span className="activity-time">{time}</span>
    </li>
  )
}
