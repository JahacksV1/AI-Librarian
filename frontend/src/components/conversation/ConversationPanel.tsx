import type { ConversationMessage } from '../../types/ui'
import { Composer } from './Composer'
import { MessageBubble } from './MessageBubble'

interface ConversationPanelProps {
  messages: ConversationMessage[]
  disabled: boolean
  error: string | null
  onSend: (content: string) => Promise<void>
}

export function ConversationPanel({ messages, disabled, error, onSend }: ConversationPanelProps) {
  return (
    <div className="panel-content conversation-panel">
      <div className="panel-header">
        <h2>Conversation</h2>
      </div>

      <div className="messages">
        {!messages.length && <div className="panel-empty">Type a message to start.</div>}
        {messages.map((message) => (
          <MessageBubble
            key={message.id}
            message={message}
            onSuggest={disabled ? undefined : (text) => void onSend(text)}
          />
        ))}
      </div>

      {error ? <div className="panel-error">{error}</div> : null}

      <Composer disabled={disabled} onSend={onSend} />
    </div>
  )
}
