import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from './api'
import { AGENT_META, Avatar } from './components/Avatar'
import type { AgentEvent, AgentName, Approval, Cash, TicketDetail, TicketRow, TicketStatus } from './types'

const AGENTS: AgentName[] = ['boss', 'inventory', 'accounting', 'facilities', 'customer_service']

const RARITY: Record<string, { tier: string; cls: string }> = {
  customer_order: { tier: 'Rare', cls: 'rare' },
  rent_notice: { tier: 'Epic', cls: 'epic' },
  price_override: { tier: 'Legendary', cls: 'legendary' },
}

const STATUS: Record<TicketStatus, { label: string; flavor: string }> = {
  open: { label: 'Open', flavor: 'Waiting in the lobby' },
  in_progress: { label: 'Agents working', flavor: 'Squad has dropped in' },
  awaiting_approval: { label: 'Needs your approval', flavor: 'Supply drop incoming' },
  resolved: { label: 'Resolved', flavor: 'Victory Royale' },
  needs_owner: { label: 'Owner must pay', flavor: 'Out of mats — pay tool refused' },
}

const money = (n: number | undefined) =>
  n === undefined ? '—' : n.toLocaleString('en-US', { style: 'currency', currency: 'USD' })

function plainArgs(args?: Record<string, unknown>) {
  if (!args) return ''
  return Object.entries(args)
    .filter(([k]) => !['requested_by', 'author_agent', 'body'].includes(k))
    .map(([k, v]) => `${k}=${typeof v === 'string' && v.length > 28 ? v.slice(0, 28) + '…' : v}`)
    .join(', ')
}

export default function App() {
  const initial = Number(new URLSearchParams(location.search).get('ticket')) || 101
  const [tickets, setTickets] = useState<TicketRow[]>([])
  const [deskDate, setDeskDate] = useState('')
  const [selected, setSelected] = useState<number>(initial)
  const [detail, setDetail] = useState<TicketDetail | null>(null)
  const [events, setEvents] = useState<AgentEvent[]>([])
  const [cash, setCash] = useState<Cash | null>(null)
  const [approver, setApprover] = useState('Cameron Hogg')
  const [toast, setToast] = useState<{ tone: 'good' | 'bad'; text: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const [offline, setOffline] = useState(false)
  const [ledgerOpen, setLedgerOpen] = useState(false)

  const refresh = useCallback(async () => {
    try {
      const [t, c, d, e] = await Promise.all([api.tickets(), api.cash(), api.ticket(selected), api.events(selected)])
      setTickets(t.tickets)
      setDeskDate(t.date_today)
      setCash(c)
      if (d.ticket.id === selected) {
        setDetail(d)
        setEvents(e.events)
      }
      setOffline(false)
    } catch {
      setOffline(true)
    }
  }, [selected])

  useEffect(() => {
    setDetail(null) // don't show the previous ticket's state while the new one loads
    setEvents([])
    refresh()
    const id = setInterval(refresh, 1800)
    return () => clearInterval(id)
  }, [refresh])

  useEffect(() => {
    if (!toast) return
    const id = setTimeout(() => setToast(null), 6000)
    return () => clearTimeout(id)
  }, [toast])

  const current = tickets.find((t) => t.id === selected)
  const status: TicketStatus = detail?.ticket.status ?? current?.status ?? 'open'
  const running = !!current?.running || detail?.latest_run?.state === 'running'
  const runEvents = useMemo(() => {
    const runId = detail?.latest_run?.run_id
    return events.filter((e) => !e.run_id || e.run_id === runId)
  }, [events, detail])

  const agentState = useMemo(() => {
    const last = runEvents.filter((e) => AGENTS.includes(e.agent as AgentName)).at(-1)
    return Object.fromEntries(
      AGENTS.map((a) => {
        const mine = runEvents.filter((e) => e.agent === a)
        const report = [...mine].reverse().find((e) => e.kind === 'report')
        const said = [...mine].reverse().find((e) => e.kind === 'said' || e.kind === 'task')
        const tools = [...new Set(mine.filter((e) => e.kind === 'tool_call').map((e) => e.tool!))]
        const calls = mine.filter((e) => e.kind === 'delegation').map((e) => e.to_agent!)
        const lastMine = mine.at(-1)
        let doing = 'Not on this ticket'
        if (lastMine) {
          doing = {
            task: 'Got the task', tool_call: `Using ${lastMine.tool}`, tool_result: 'Reading tool result',
            said: 'Talking it through', delegation: `Waiting on ${AGENT_META[lastMine.to_agent!]?.label}`,
            delegation_result: 'Got a teammate report', report: 'Reported back', retry: 'Retrying a tool',
          }[lastMine.kind] ?? lastMine.kind
        }
        const bubble = report?.report?.summary ?? report?.report?.outcome ?? said?.text ?? said?.task ?? ''
        return [a, { active: running && last?.agent === a, joined: mine.length > 0, done: !!report, doing, bubble, tools, calls }]
      }),
    ) as Record<AgentName, { active: boolean; joined: boolean; done: boolean; doing: string; bubble: string; tools: string[]; calls: AgentName[] }>
  }, [runEvents, running])

  const chain = useMemo(() => {
    const links = runEvents.filter((e) => e.kind === 'delegation').map((e) => `${AGENT_META[e.agent as AgentName].label} ➜ ${AGENT_META[e.to_agent!].label}`)
    return links
  }, [runEvents])

  async function startRun() {
    setBusy(true)
    try {
      await api.run(selected)
      setToast({ tone: 'good', text: `Squad dropped in on ticket ${selected}.` })
      refresh()
    } catch (err) {
      setToast({ tone: 'bad', text: (err as Error).message })
    } finally {
      setBusy(false)
    }
  }

  async function decide(a: Approval, approve: boolean) {
    if (!approver.trim()) {
      setToast({ tone: 'bad', text: 'Type your name in the approver box first.' })
      return
    }
    setBusy(true)
    try {
      const r = approve ? await api.approve(a.id, approver.trim()) : await api.decline(a.id, approver.trim())
      if (r.refused) setToast({ tone: 'bad', text: `Pay tool refused: ${r.reason}` })
      else if (approve) setToast({ tone: 'good', text: `Paid ${money(r.amount as number)} — checking now ${money(r.checking_after as number)}.` })
      else setToast({ tone: 'good', text: `Declined approval #${a.id}. No money moved.` })
      refresh()
    } catch (err) {
      setToast({ tone: 'bad', text: (err as Error).message })
    } finally {
      setBusy(false)
    }
  }

  async function reset() {
    if (!confirm('Reset campus_customs_new.db back to the original shop data? The audit trail is kept.')) return
    setBusy(true)
    try {
      const r = await api.reset()
      setToast({ tone: 'good', text: `Back to the lobby. Checking reset to ${money(r.checking)}.` })
      refresh()
    } catch (err) {
      setToast({ tone: 'bad', text: (err as Error).message })
    } finally {
      setBusy(false)
    }
  }

  const report = detail?.latest_run?.report
  const rarity = RARITY[detail?.ticket.type ?? 'customer_order'] ?? RARITY.customer_order
  const storm = stormInfo(detail)

  return (
    <div className="world">
      <div className="sky" aria-hidden="true">
        <span className="cloud c1" /><span className="cloud c2" /><span className="cloud c3" />
        <div className="battle-bus"><span className="balloon" /><span className="bus"><i className="win w1" /><i className="win w2" /><i className="win w3" /><i className="wheel f" /><i className="wheel b" /></span></div>
      </div>

      <header className="hud">
        <div className="brand">
          <div className="logo">CAMPUS CUSTOMS</div>
          <div className="sub">BATTLE DESK · back office</div>
        </div>
        <div className="hud-mid">
          <div className="chip date">DESK DAY <b>{deskDate || '…'}</b></div>
          <div className="chip squad">MODEL <b>gpt-5.6-luna</b> · 5-agent squad</div>
        </div>
        <div className="hud-right">
          <button className="bank" onClick={() => setLedgerOpen((o) => !o)} title="Checking balance from cash_accounts">
            <span className="coin">$</span>
            <span className="bank-text">
              <small>CHECKING</small>
              <b data-testid="checking">{money(cash?.balance)}</b>
              {cash && cash.pending_approvals_total > 0 && <em>{money(cash.pending_approvals_total)} waiting on approval</em>}
            </span>
          </button>
          <label className="approver">
            <small>APPROVER</small>
            <input value={approver} onChange={(e) => setApprover(e.target.value)} placeholder="Your name" />
          </label>
          <button className="btn ghost" onClick={reset} disabled={busy || running}>⟲ Back to lobby</button>
        </div>
      </header>

      {ledgerOpen && cash && (
        <div className="ledger">
          <div className="ledger-head">Ledger · cash only goes out</div>
          {cash.payments.length === 0 && <div className="muted">No payments yet. Starting balance {money(cash.balance)}.</div>}
          {cash.payments.map((p) => (
            <div className="ledger-row" key={p.id}>
              <span>#{p.id} {p.kind} {p.ref_id}</span><span>−{money(p.amount)}</span><small>{p.paid_at} · approved by {p.approved_by}</small>
            </div>
          ))}
        </div>
      )}

      {offline && <div className="offline">Can't reach the backend on localhost:8000. Start it with <code>uvicorn main:app --reload --port 8000</code> in backend/.</div>}

      <main className="desk">
        <section className="loot">
          <h2 className="panel-title">TICKETS <span>loot pool</span></h2>
          {tickets.map((t) => {
            const r = RARITY[t.type] ?? RARITY.customer_order
            return (
              <button key={t.id} className={`loot-card ${r.cls} ${t.id === selected ? 'picked' : ''} st-${t.status}`} onClick={() => setSelected(t.id)}>
                <div className="loot-top"><span className="tier">{r.tier}</span><span className="tid">#{t.id}</span></div>
                <div className="loot-subject">{t.subject}</div>
                <div className="loot-meta">{t.type.replace('_', ' ')} · {t.requester}</div>
                <div className={`badge b-${t.status}`}>{t.running ? 'Agents working' : STATUS[t.status].label}</div>
                {t.pending_approvals > 0 && <div className="drop-flag">🪂 {t.pending_approvals} approval{t.pending_approvals > 1 ? 's' : ''}</div>}
              </button>
            )
          })}
          <div className="desk-mug" aria-hidden="true"><span className="steam s1" /><span className="steam s2" /><span className="mug"><i>CC</i></span></div>
        </section>

        <section className="arena">
          <div className={`ticket-hero ${rarity.cls}`}>
            <div>
              <div className="hero-kicker">TICKET #{selected} · {rarity.tier.toUpperCase()} · {detail?.ticket.type.replace('_', ' ')}</div>
              <h1>{detail?.ticket.subject ?? '…'}</h1>
              <p className="hero-notes">“{detail?.ticket.notes}” — {detail?.ticket.requester}</p>
              <div className="hero-facts">
                {detail?.ticket.sku && <span>{detail.product_name ?? detail.ticket.sku} · size {detail.ticket.size} · qty {detail.ticket.qty}</span>}
                {detail?.linked_invoice && <span>Invoice {detail.linked_invoice.id} · {detail.linked_invoice.vendor_name} · {money(detail.linked_invoice.amount)} · {detail.linked_invoice.status}</span>}
                {detail?.linked_lease && <span>Lease {detail.linked_lease.id} · {detail.linked_lease.landlord} · {money(detail.linked_lease.monthly_rent)} due {detail.linked_lease.next_due}</span>}
              </div>
              {storm && <div className={`storm ${storm.tone}`}>🌀 {storm.text}</div>}
            </div>
            <div className="hero-actions">
              <div className={`status-pill b-${status}`}>{running ? 'Agents working' : STATUS[status].label}<small>{running ? 'Squad has dropped in' : STATUS[status].flavor}</small></div>
              <button className="btn drop" onClick={startRun} disabled={busy || running || status === 'resolved' || status === 'awaiting_approval'}>
                {running ? 'Squad in the match…' : status === 'open' ? '🪂 Drop in · run agent team' : status === 'resolved' ? 'Resolved' : 'Waiting on you'}
              </button>
            </div>
          </div>

          {status === 'resolved' && !running && (
            <div className="victory"><span className="num">#1</span><span className="vr">VICTORY ROYALE</span><small>Ticket {selected} resolved</small></div>
          )}

          <div className="chain">
            <span className="chain-label">Delegation path</span>
            {chain.length === 0 ? <span className="muted">No delegations yet — drop in to start.</span> : chain.map((c, i) => <span className="link" key={i}>{c}</span>)}
          </div>

          <div className="squad">
            {AGENTS.map((a) => {
              const s = agentState[a]
              const m = AGENT_META[a]
              return (
                <article key={a} className={`agent-card r-${m.rarity} ${s.active ? 'active' : ''} ${s.joined ? 'joined' : 'benched'}`}>
                  <div className="agent-top">
                    <Avatar agent={a} active={s.active} />
                    <div>
                      <div className="agent-name">{m.label}</div>
                      <div className="agent-skin">{m.skin} · {m.role}</div>
                      <div className="agent-doing">{s.active ? '● ' : ''}{s.doing}</div>
                    </div>
                  </div>
                  <div className={`bubble ${s.bubble ? '' : 'empty'}`}>{s.bubble || (s.joined ? '…' : 'Benched for this ticket.')}</div>
                  <div className="hotbar">
                    {s.tools.map((t) => <span className="slot" key={t} title={t}>{t}</span>)}
                    {s.calls.map((c, i) => <span className="slot call" key={`${c}${i}`}>➜ {AGENT_META[c].label}</span>)}
                    {!s.tools.length && !s.calls.length && <span className="slot empty">empty slot</span>}
                  </div>
                </article>
              )
            })}
          </div>

          <div className="lower">
            <div className="drops">
              <h3 className="panel-title small">SUPPLY DROPS <span>human approval</span></h3>
              {(detail?.approvals ?? []).length === 0 && <div className="muted">No payments or purchases on this ticket. Agents can only prepare them — you click to pay.</div>}
              {(detail?.approvals ?? []).map((a) => (
                <div key={a.id} className={`drop-card d-${a.status}`}>
                  <div className="crate" aria-hidden="true"><span className="chute" /><span className="box" /></div>
                  <div className="drop-body">
                    <div className="drop-title">#{a.id} · {a.kind} · <b>{money(a.amount)}</b></div>
                    <div className="drop-desc">{a.description}</div>
                    <div className="drop-meta">prepared by {a.requested_by} · {a.status}{a.decided_by ? ` by ${a.decided_by}` : ''}</div>
                    {a.decision_note && <div className="drop-note">{a.decision_note}</div>}
                    {a.status === 'pending' && (
                      <div className="drop-actions">
                        <button className="btn approve" disabled={busy} onClick={() => decide(a, true)}>✔ Approve & pay</button>
                        <button className="btn ghost" disabled={busy} onClick={() => decide(a, false)}>Decline</button>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>

            <div className="notes">
              <h3 className="panel-title small">DRAFTS <span>stay on the board</span></h3>
              {(detail?.drafts ?? []).length === 0 && <div className="muted">No draft on this ticket.</div>}
              {(detail?.drafts ?? []).map((d) => (
                <div className="sticky" key={d.id}>
                  <div className="stamp">NOT SENT</div>
                  <div className="sticky-to">To: {d.recipient}</div>
                  <div className="sticky-subj">{d.subject}</div>
                  <pre className="sticky-body">{d.body}</pre>
                  <div className="sticky-by">draft #{d.id} · by {AGENT_META[d.author_agent as AgentName]?.label ?? d.author_agent}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="summary">
            <h3 className="panel-title small">MATCH SUMMARY <span>what each agent did</span></h3>
            {!report && <div className="muted">{running ? 'Squad is still playing this one…' : 'Run the team to see the summary.'}</div>}
            {report && (
              <>
                <p className="outcome">{report.outcome}</p>
                <p className="first">Boss called <b>{AGENT_META[report.called_first].label}</b> first — {report.why_first}</p>
                <div className="contribs">
                  {report.contributions.map((c, i) => (
                    <div className="contrib" key={i}><Avatar agent={c.agent} /><div><b>{AGENT_META[c.agent].label}</b><span>{c.contribution}</span></div></div>
                  ))}
                </div>
              </>
            )}
          </div>
        </section>

        <aside className="feed">
          <h2 className="panel-title">LIVE FEED <span>agent events</span></h2>
          <div className="feed-list">
            {runEvents.length === 0 && <div className="muted">Quiet lobby. Events stream here as agents talk and use tools.</div>}
            {[...runEvents].reverse().map((e) => <FeedLine key={e.seq} e={e} />)}
          </div>
        </aside>
      </main>

      {toast && <div className={`toast ${toast.tone}`}>{toast.text}</div>}
    </div>
  )
}

function FeedLine({ e }: { e: AgentEvent }) {
  const who = (a?: string) => (a && a in AGENT_META ? AGENT_META[a as AgentName].label : a ?? '')
  let icon = '•'
  let text = ''
  switch (e.kind) {
    case 'run_start': icon = '🚌'; text = 'Battle bus launched — run started'; break
    case 'run_end': icon = '🏆'; text = 'Run finished'; break
    case 'run_error': icon = '⚠️'; text = `Run error: ${e.error}`; break
    case 'task': icon = '🎯'; text = `${who(e.agent)} got a task from ${who(e.asked_by)}`; break
    case 'delegation': icon = '➜'; text = `${who(e.agent)} ➜ ${who(e.to_agent)}: ${e.task}`; break
    case 'delegation_result': icon = '↩'; text = `${who(e.agent)} got the report back`; break
    case 'tool_call': icon = '⛏'; text = `${who(e.agent)} used ${e.tool}(${plainArgs(e.args)})`; break
    case 'tool_result': icon = '✓'; text = `${e.tool} answered ${who(e.agent)}`; break
    case 'said': icon = '💬'; text = `${who(e.agent)}: ${e.text}`; break
    case 'report': icon = '📋'; text = `${who(e.agent)} reported: ${e.report?.summary ?? e.report?.outcome ?? ''}`; break
    case 'retry': icon = '↻'; text = `${who(e.agent)} retried ${e.tool ?? ''}`; break
    case 'human_approval': icon = '🪂'; text = `${e.approved_by} clicked approve on #${e.approval_id}`; break
    case 'human_decline': icon = '✋'; text = `Approval #${e.approval_id} declined`; break
    default: text = e.kind
  }
  return (
    <div className={`feed-line k-${e.kind} a-${e.agent}`}>
      <span className="feed-icon">{icon}</span>
      <span className="feed-text">{text}</span>
      <span className="feed-time">{e.ts?.slice(11, 19)}</span>
    </div>
  )
}

function stormInfo(d: TicketDetail | null): { tone: string; text: string } | null {
  if (!d) return null
  const today = new Date(d.date_today)
  const days = (iso: string) => Math.round((new Date(iso).getTime() - today.getTime()) / 86400000)
  if (d.linked_invoice) {
    const n = days(d.linked_invoice.due_date)
    if (d.linked_invoice.status === 'open' && n < 0) return { tone: 'in', text: `In the storm: invoice ${d.linked_invoice.id} is ${-n} days overdue — the vendor won't ship until it's paid` }
    if (d.linked_invoice.status !== 'open') return { tone: 'safe', text: `Safe zone: invoice ${d.linked_invoice.id} is ${d.linked_invoice.status}` }
  }
  if (d.linked_lease) {
    const n = days(d.linked_lease.next_due)
    return n <= 7 ? { tone: n < 0 ? 'in' : 'closing', text: `Storm closing: rent due in ${n} day${n === 1 ? '' : 's'} (${d.linked_lease.next_due})` } : { tone: 'safe', text: `Safe zone: next rent due ${d.linked_lease.next_due}` }
  }
  return null
}
