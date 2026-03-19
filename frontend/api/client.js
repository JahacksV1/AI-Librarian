const BASE = window.API_BASE || "http://localhost:8000";

async function req(path, opts = {}) {
  const res = await fetch(`${BASE}${path}`, { credentials: "same-origin", ...opts });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try { const b = await res.json(); if (b?.detail) detail = b.detail; } catch (_) {}
    throw new Error(detail);
  }
  return res;
}

const json = (path, opts) => req(path, opts).then((r) => r.json());

export const checkHealth = () => json("/health");

export const createSession = (uid = "00000000-0000-0000-0000-000000000001") =>
  json("/sessions", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ user_id: uid, mode: "CHAT" }) });

export const sendMessage = (sid, content) =>
  req(`/sessions/${sid}/messages`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ content }) });

export const getPlan = (id) => json(`/plans/${id}`);

export const patchAction = (id, status) =>
  json(`/actions/${id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status }) });

export const approveAll = (id) => json(`/plans/${id}/approve-all`, { method: "POST" });

export const executePlan = (id) => req(`/plans/${id}/execute`, { method: "POST" });
