import type { ConversationMessage } from '../../types/ui'

interface MessageBubbleProps {
  message: ConversationMessage
}

export function MessageBubble({ message }: MessageBubbleProps) {
  if (message.role === 'tool') {
    return (
      <details className="msg msg-tool">
        <summary>{message.title ?? 'Tool message'}</summary>
        <pre>{message.content}</pre>
      </details>
    )
  }

  return (
    <div className={`msg msg-${message.role}`}>
      <p>{message.content || (message.role === 'assistant' ? '...' : '')}</p>
    </div>
  )
}
