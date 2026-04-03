import type { ConversationMessage } from '../../types/ui'
import { MarkdownMessage } from './MarkdownMessage'
import { ScanResultCard } from './ScanResultCard'
import { RetrievalResultCard } from './RetrievalResultCard'

interface MessageBubbleProps {
  message: ConversationMessage
  onSuggest?: (text: string) => void
}

export function MessageBubble({ message, onSuggest }: MessageBubbleProps) {
  if (message.role !== 'tool') {
    const content = message.content || (message.role === 'assistant' ? '...' : '')
    return (
      <div className={`msg msg-${message.role}`}>
        {message.role === 'assistant'
          ? <MarkdownMessage content={content} />
          : <p>{content}</p>
        }
      </div>
    )
  }

  const { toolName, isResult, payload } = message

  // ── Structured scan result card ──────────────────────────────────────────
  if (toolName === 'scan_folder' && isResult && payload && typeof payload === 'object') {
    return (
      <ScanResultCard
        payload={payload as Parameters<typeof ScanResultCard>[0]['payload']}
        onSuggest={onSuggest}
      />
    )
  }

  // ── Structured retrieval result card ─────────────────────────────────────
  if (toolName === 'query_indexed_files' && isResult && payload && typeof payload === 'object') {
    return (
      <RetrievalResultCard
        payload={payload as Parameters<typeof RetrievalResultCard>[0]['payload']}
        args={message.toolArgs as Parameters<typeof RetrievalResultCard>[0]['args']}
        onSuggest={onSuggest}
      />
    )
  }

  // ── Tool calls (not results) — show a compact one-liner ──────────────────
  if (!isResult) {
    const callLabel = toolName === 'scan_folder'
      ? `Scanning ${(payload as Record<string, string>)?.path ?? '…'}`
      : toolName === 'query_indexed_files'
        ? `Querying index for ${(payload as Record<string, string>)?.entity_type ?? 'files'}`
        : message.title ?? `Calling ${toolName ?? 'tool'}`

    return (
      <details className="msg msg-tool msg-tool-call">
        <summary className="tool-call-label">{callLabel}</summary>
        <pre className="tool-card-raw">{JSON.stringify(payload, null, 2)}</pre>
      </details>
    )
  }

  // ── Default: generic collapsible for other tools ─────────────────────────
  return (
    <details className="msg msg-tool">
      <summary>{message.title ?? 'Tool message'}</summary>
      <pre>{message.content}</pre>
    </details>
  )
}
