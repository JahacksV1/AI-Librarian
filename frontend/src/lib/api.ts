import type { FileResponse, FolderResponse, HealthResponse, PlanResponse, ScanResponse, SessionResponse } from '../types/api'

const BASE = import.meta.env.VITE_API_BASE ?? '/api'

async function request(path: string, opts: RequestInit = {}): Promise<Response> {
  const response = await fetch(`${BASE}${path}`, {
    credentials: 'same-origin',
    ...opts,
  })

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`
    try {
      const body = (await response.json()) as { detail?: string }
      if (body.detail) detail = body.detail
    } catch {
      // Keep default detail.
    }
    throw new Error(detail)
  }

  return response
}

async function requestJson<T>(path: string, opts?: RequestInit): Promise<T> {
  const response = await request(path, opts)
  return response.json() as Promise<T>
}

export function checkHealth(): Promise<HealthResponse> {
  return requestJson<HealthResponse>('/health')
}

export function createSession(
  userId = '00000000-0000-0000-0000-000000000001',
): Promise<SessionResponse> {
  return requestJson<SessionResponse>('/sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: userId, mode: 'CHAT' }),
  })
}

export function sendMessage(sessionId: string, content: string): Promise<Response> {
  return request(`/sessions/${sessionId}/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
  })
}

export function getPlan(planId: string): Promise<PlanResponse> {
  return requestJson<PlanResponse>(`/plans/${planId}`)
}

export function patchAction(actionId: string, status: 'APPROVED' | 'REJECTED'): Promise<void> {
  return requestJson<void>(`/actions/${actionId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status }),
  })
}

export function approveAll(planId: string): Promise<void> {
  return requestJson<void>(`/plans/${planId}/approve-all`, { method: 'POST' })
}

export function executePlan(planId: string): Promise<Response> {
  return request(`/plans/${planId}/execute`, { method: 'POST' })
}

export function getScans(sessionId: string): Promise<{ scans: ScanResponse[] }> {
  return requestJson<{ scans: ScanResponse[] }>(`/scans?session_id=${sessionId}`)
}

export function getScan(scanId: string): Promise<ScanResponse> {
  return requestJson<ScanResponse>(`/scans/${scanId}`)
}

export function getFolders(deviceId?: string, pathPrefix?: string): Promise<{ folders: FolderResponse[] }> {
  const params = new URLSearchParams()
  if (deviceId) params.set('device_id', deviceId)
  if (pathPrefix) params.set('path_prefix', pathPrefix)
  return requestJson<{ folders: FolderResponse[] }>(`/folders?${params}`)
}

export function getFiles(deviceId?: string, pathPrefix?: string): Promise<{ files: FileResponse[] }> {
  const params = new URLSearchParams()
  if (deviceId) params.set('device_id', deviceId)
  if (pathPrefix) params.set('path_prefix', pathPrefix)
  return requestJson<{ files: FileResponse[] }>(`/files?${params}`)
}
