/**
 * POST SSE: parse fetch Response streams (not EventSource).
 * Contract: frames are "data: {json}\\n\\n" — see docs/FE_BE_INTEGRATION.md
 *
 * @param {Response} response
 * @param {(data: Record<string, unknown>) => void} onEvent
 */
export async function readSSEStream(response, onEvent) {
  if (!response.body) throw new Error("No stream body.");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() || "";
    for (const part of parts) {
      const line = part.split("\n").find((l) => l.startsWith("data: "));
      if (!line) continue;
      try {
        const data = JSON.parse(line.slice(6));
        onEvent(data);
      } catch (_) {}
    }
  }
}
