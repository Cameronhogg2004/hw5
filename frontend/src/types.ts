export type AgentName = 'boss' | 'inventory' | 'accounting' | 'facilities' | 'customer_service'
export type TicketStatus = 'open' | 'in_progress' | 'awaiting_approval' | 'resolved' | 'needs_owner'

export interface TicketRow {
  id: number
  type: string
  requester: string
  subject: string
  status: TicketStatus
  created_at: string
  pending_approvals: number
  running: boolean
  latest_run_id: string | null
}

export interface Approval {
  id: number
  ticket_id: number
  kind: 'invoice' | 'rent' | 'purchase'
  ref_id: number
  amount: number
  description: string
  status: 'pending' | 'paid' | 'refused' | 'declined'
  requested_by: string
  decided_by: string | null
  decision_note: string | null
}

export interface Draft {
  id: number
  recipient: string
  subject: string
  body: string
  author_agent: string
  status: string
}

export interface Contribution { agent: AgentName; contribution: string }

export interface BossReport {
  ticket_id: number
  called_first: AgentName
  why_first: string
  delegations: string[]
  outcome: string
  contributions: Contribution[]
  approvals_waiting: number[]
}

export interface TicketDetail {
  ticket: {
    id: number; type: string; requester: string; subject: string; sku: string | null; size: string | null
    qty: number | null; lease_id: number | null; invoice_id: number | null; status: TicketStatus; notes: string
    created_at: string
  }
  product_name?: string | null
  date_today: string
  linked_invoice?: { id: number; amount: number; due_date: string; status: string; vendor_name: string; description: string } | null
  linked_lease?: { id: number; space_name: string; landlord: string; monthly_rent: number; next_due: string } | null
  approvals: Approval[]
  drafts: Draft[]
  resolutions: { status: string; summary: string; recorded_by: string; recorded_at: string }[]
  latest_run: { run_id: string; state: 'running' | 'finished' | 'error'; report: BossReport | null; error: string | null } | null
}

export interface AgentEvent {
  seq: number
  ts: string
  run_id?: string
  ticket_id?: number
  agent: AgentName | 'board' | 'human'
  kind: string
  step?: number
  depth?: number
  tool?: string
  args?: Record<string, unknown>
  result?: unknown
  text?: string
  task?: string
  asked_by?: string
  to_agent?: AgentName
  report?: { summary?: string; outcome?: string; actions?: string[]; needs_human?: string | null }
  error?: string
  approved_by?: string
  approval_id?: number
}

export interface Cash {
  account: string
  balance: number
  as_of: string
  pending_approvals_total: number
  balance_if_all_pending_paid: number
  payments: { id: number; kind: string; ref_id: number; amount: number; paid_at: string; approved_by: string }[]
}
