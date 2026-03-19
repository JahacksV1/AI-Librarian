import type { SSEEvent } from '../types/sse'

export async function readSSEStream(
  response: Response,
  onEvent: (event: SSEEvent) => void,
): Promise<void> {
  if (!response.body) {
    throw new Error('Missing response body for SSE stream.')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const chunks = buffer.split('\n\n')
    buffer = chunks.pop() ?? ''

    for (const chunk of chunks) {
      const dataLines = chunk
        .split('\n')
        .filter((line) => line.startsWith('data:'))
        .map((line) => line.slice(5).trim())

      if (!dataLines.length) continue

      const raw = dataLines.join('\n')
      if (!raw || raw === '[DONE]') continue

      try {
        onEvent(JSON.parse(raw) as SSEEvent)
      } catch {
        // Ignore malformed chunk and continue stream.
      }
    }
  }
}
