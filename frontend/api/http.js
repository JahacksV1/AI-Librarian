/**
 * Low-level HTTP for the AIJAH API. Uses same-origin credentials (works with Vite /api proxy).
 * Streaming responses: use apiFetch and pass the Response to readSSEStream (sse.js).
 */
import { getApiBase } from "./config.js";

/**
 * @param {string} path Absolute path on the API, e.g. "/health"
 * @param {RequestInit} [init]
 * @returns {Promise<Response>}
 */
export async function apiFetch(path, init = {}) {
  const base = getApiBase();
  const res = await fetch(`${base}${path}`, {
    credentials: "same-origin",
    ...init,
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const b = await res.json();
      if (b?.detail) detail = b.detail;
    } catch (_) {}
    throw new Error(detail);
  }
  return res;
}

/**
 * @param {string} path
 * @param {RequestInit} [init]
 * @returns {Promise<unknown>}
 */
export async function apiJson(path, init) {
  const res = await apiFetch(path, init);
  return res.json();
}
