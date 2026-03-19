/**
 * REST surface that matches the backend router — one function per endpoint.
 * This is the primary file to rename to backendApi.ts during TS migration.
 * Do not mix DOM or React state here.
 */
import { apiFetch, apiJson } from "./http.js";

const JSON_HDR = { "Content-Type": "application/json" };

export function checkHealth() {
  return apiJson("/health");
}

export function createSession(userId = "00000000-0000-0000-0000-000000000001") {
  return apiJson("/sessions", {
    method: "POST",
    headers: JSON_HDR,
    body: JSON.stringify({ user_id: userId, mode: "CHAT" }),
  });
}

export function sendMessage(sessionId, content) {
  return apiFetch(`/sessions/${sessionId}/messages`, {
    method: "POST",
    headers: JSON_HDR,
    body: JSON.stringify({ content }),
  });
}

export function getPlan(planId) {
  return apiJson(`/plans/${planId}`);
}

export function patchAction(actionId, status) {
  return apiJson(`/actions/${actionId}`, {
    method: "PATCH",
    headers: JSON_HDR,
    body: JSON.stringify({ status }),
  });
}

export function approveAll(planId) {
  return apiJson(`/plans/${planId}/approve-all`, { method: "POST" });
}

export function executePlan(planId) {
  return apiFetch(`/plans/${planId}/execute`, { method: "POST" });
}
