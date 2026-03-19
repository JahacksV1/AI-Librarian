import { useState } from 'react'

interface ComposerProps {
  disabled: boolean
  onSend: (content: string) => Promise<void>
}

export function Composer({ disabled, onSend }: ComposerProps) {
  const [value, setValue] = useState('')

  return (
    <div className="composer">
      <textarea
        rows={1}
        maxLength={2000}
        placeholder="Describe what you want to organize..."
        value={value}
        disabled={disabled}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault()
            const content = value.trim()
            if (!content || disabled) return
            setValue('')
            void onSend(content)
          }
        }}
      />
      <button
        type="button"
        className="btn"
        disabled={disabled || !value.trim()}
        onClick={() => {
          const content = value.trim()
          if (!content || disabled) return
          setValue('')
          void onSend(content)
        }}
      >
        Send
      </button>
    </div>
  )
}
