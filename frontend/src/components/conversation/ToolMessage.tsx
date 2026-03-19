interface ToolMessageProps {
  title: string
  payload: unknown
}

export function ToolMessage({ title, payload }: ToolMessageProps) {
  return (
    <details className="msg msg-tool">
      <summary>{title}</summary>
      <pre>{JSON.stringify(payload, null, 2)}</pre>
    </details>
  )
}
