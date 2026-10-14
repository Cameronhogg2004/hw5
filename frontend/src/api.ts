import type { AgentEvent, Cash, TicketDetail, TicketRow } from './types'

// The FastAPI backend on localhost (backend/main.py). CORS there allows this Vite origin.
export const API = 'http://localhost:8000'

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    headers: { 'content-type': 'application/json' },
    ...init,
  })
  const body = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(body.detail ?? `${res.status} ${res.statusText}`)
  return body as T
}

export const api = {
  tickets: () => req<{ date_today: string; tickets: TicketRow[] }>('/api/tickets'),
  ticket: (id: number) => req<TicketDetail>(`/api/tickets/${id}`),
  run: (id: number) => req<{ run_id: string }>(`/api/tickets/${id}/run`, { method: 'POST' }),
  events: (id: number) => req<{ events: AgentEvent[]; last_seq: number }>(`/api/events?ticket_id=${id}`),
  cash: () => req<Cash>('/api/cash'),
  approve: (approvalId: number, approvedBy: string) =>
    req<Record<string, unknown>>(`/api/approvals/${approvalId}/approve`, {
      method: 'POST', body: JSON.stringify({ approved_by: approvedBy }),
    }),
  decline: (approvalId: number, declinedBy: string) =>
    req<Record<string, unknown>>(`/api/approvals/${approvalId}/decline`, {
      method: 'POST', body: JSON.stringify({ declined_by: declinedBy, note: 'Declined on the board' }),
    }),
  reset: () => req<{ ok: boolean; checking: number }>('/api/reset', { method: 'POST' }),
}
