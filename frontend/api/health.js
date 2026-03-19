/**
 * Pure helpers for GET /health — safe to unit test, easy to port to TypeScript.
 */

/** @param {Record<string, unknown> | null | undefined} h */
export function isHealthOk(h) {
  return h?.status === "ok";
}

/** @param {Record<string, unknown> | null | undefined} h */
export function describeHealthFailure(h) {
  const parts = [];
  if (h?.db && h.db !== "connected") parts.push(`DB: ${h.db}`);

  const provider = String(h?.model_provider || "").toLowerCase();
  const ms = String(h?.model_status || "");

  if (provider === "ollama" && h?.ollama && h.ollama !== "reachable") {
    parts.push(`Ollama: ${h.ollama}`);
  } else if (provider === "anthropic" || provider === "openai") {
    if (ms && ms !== "configured") parts.push(`Model: ${ms}`);
  } else if (ms && ms !== "reachable" && ms !== "configured") {
    parts.push(`Model: ${ms}`);
  }

  return parts.length ? `System unhealthy — ${parts.join(", ")}` : "System health degraded.";
}
