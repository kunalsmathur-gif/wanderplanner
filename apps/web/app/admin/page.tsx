'use client'

import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import {
  AlertTriangle,
  Check,
  Database,
  IndianRupee,
  Loader2,
  LogIn,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Users,
  X,
} from 'lucide-react'
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { WanderplannerLogo } from '@/components/common/WanderplannerLogo'
import {
  approveAdminRequest,
  getAdminLeads,
  getAdminSummary,
  getAdminTimeseries,
  listAdminRequests,
  markLeadBooked,
  purgeAllUsers,
  rejectAdminRequest,
  type AdminLead,
  type AdminRequest,
  type AdminSummary,
  type AdminTimeseries,
} from '@/lib/adminApi'
import { useAuthStore } from '@/store/authStore'

const ACTIVITY_SERIES = [
  { key: 'sessions', label: 'Sessions', stroke: '#3b82f6' },
  { key: 'signups', label: 'Sign-ups', stroke: '#22c55e' },
  { key: 'logins', label: 'Logins', stroke: '#f59e0b' },
  { key: 'itineraries', label: 'Itineraries', stroke: '#a855f7' },
] as const

const LEAD_RESPONSE_SERIES = [
  { key: 'avg_hours', label: 'Avg response (hrs)', stroke: '#0ea5e9' },
] as const

function StatCard({
  icon,
  label,
  value,
  sub,
  valueClassName,
  valueStyle,
}: {
  icon: React.ReactNode
  label: string
  value: string | number
  sub?: string
  valueClassName?: string
  valueStyle?: React.CSSProperties
}) {
  return (
    <div className="rounded-2xl border border-[var(--_border)] bg-[var(--_card)] p-5">
      <div className="flex items-center gap-2 text-[var(--_muted-fg)]">
        {icon}
        <span className="text-xs font-medium uppercase tracking-wide">{label}</span>
      </div>
      <p
        className={[
          'mt-2 text-2xl font-bold text-[var(--_fg)] [font-family:var(--font-display)]',
          valueClassName ?? '',
        ].join(' ')}
        style={valueStyle}
      >
        {value}
      </p>
      {sub && <p className="mt-1 text-xs text-[var(--_muted-fg)]">{sub}</p>}
    </div>
  )
}

function formatRelativeTime(input: string): string {
  const target = new Date(input)
  if (Number.isNaN(target.getTime())) return input
  const diffSeconds = Math.round((target.getTime() - Date.now()) / 1000)
  const rtf = new Intl.RelativeTimeFormat('en', { numeric: 'auto' })
  const units: Array<[Intl.RelativeTimeFormatUnit, number]> = [
    ['day', 86_400],
    ['hour', 3_600],
    ['minute', 60],
  ]

  for (const [unit, secondsPerUnit] of units) {
    if (Math.abs(diffSeconds) >= secondsPerUnit || unit === 'minute') {
      return rtf.format(Math.round(diffSeconds / secondsPerUnit), unit)
    }
  }

  return 'just now'
}

function leadStatusBadge(lead: AdminLead) {
  switch (lead.status) {
    case 'responded':
      return 'rounded-full bg-[var(--_success)]/15 px-2.5 py-1 text-xs font-semibold text-[var(--_success)]'
    case 'escalated':
      return 'rounded-full bg-[#D97706]/15 px-2.5 py-1 text-xs font-semibold text-[#D97706]'
    case 'reassured':
      return 'rounded-full bg-[var(--_destructive)]/15 px-2.5 py-1 text-xs font-semibold text-[var(--_destructive)]'
    default:
      return 'rounded-full bg-[var(--_muted)] px-2.5 py-1 text-xs font-semibold text-[var(--_muted-fg)]'
  }
}

function leadStatusLabel(status: AdminLead['status']): string {
  switch (status) {
    case 'responded':
      return 'Responded'
    case 'escalated':
      return 'Escalated (24h)'
    case 'reassured':
      return 'Reassured (48h)'
    default:
      return 'Pending'
  }
}

function slaBreachStyle(rate: number | null): React.CSSProperties | undefined {
  if (rate == null) return undefined
  if (rate > 0.25) return { color: 'var(--_destructive)' }
  if (rate >= 0.1) return { color: '#D97706' }
  return { color: 'var(--_success)' }
}

export default function AdminDashboardPage() {
  const purgeConfirmationInputId = 'purge-users-confirmation'
  const status = useAuthStore((s) => s.status)
  const user = useAuthStore((s) => s.user)

  const [summary, setSummary] = useState<AdminSummary | null>(null)
  const [timeseries, setTimeseries] = useState<AdminTimeseries | null>(null)
  const [leads, setLeads] = useState<AdminLead[]>([])
  const [range, setRange] = useState<'7d' | '30d'>('30d')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [leadsError, setLeadsError] = useState<string | null>(null)
  const [markingLeadId, setMarkingLeadId] = useState<string | null>(null)

  const [showPurgeConfirm, setShowPurgeConfirm] = useState(false)
  const [purgeText, setPurgeText] = useState('')
  const [purging, setPurging] = useState(false)
  const [purgeResult, setPurgeResult] = useState<string | null>(null)
  const [purgeError, setPurgeError] = useState<string | null>(null)

  const [adminRequests, setAdminRequests] = useState<AdminRequest[]>([])
  const [requestsLoading, setRequestsLoading] = useState(true)
  const [reviewingId, setReviewingId] = useState<string | null>(null)
  const [requestsError, setRequestsError] = useState<string | null>(null)

  const PURGE_PHRASE = 'DELETE ALL USERS'

  async function loadAdminRequests() {
    setRequestsLoading(true)
    setRequestsError(null)
    try {
      setAdminRequests(await listAdminRequests('pending'))
    } catch {
      setRequestsError('Failed to load admin access requests.')
    } finally {
      setRequestsLoading(false)
    }
  }

  async function loadDashboard(selectedRange: '7d' | '30d') {
    setLoading(true)
    setError(null)
    setLeadsError(null)
    try {
      const [nextSummary, nextTimeseries, nextLeads] = await Promise.all([
        getAdminSummary(),
        getAdminTimeseries(selectedRange),
        getAdminLeads(),
      ])
      setSummary(nextSummary)
      setTimeseries(nextTimeseries)
      setLeads(nextLeads)
    } catch {
      setError('Failed to load metrics.')
    } finally {
      setLoading(false)
    }
  }

  async function handleApprove(id: string) {
    setReviewingId(id)
    setRequestsError(null)
    try {
      await approveAdminRequest(id)
      setAdminRequests((prev) => prev.filter((r) => r.id !== id))
    } catch {
      setRequestsError('Failed to approve request — please try again.')
    } finally {
      setReviewingId(null)
    }
  }

  async function handleReject(id: string) {
    setReviewingId(id)
    setRequestsError(null)
    try {
      await rejectAdminRequest(id)
      setAdminRequests((prev) => prev.filter((r) => r.id !== id))
    } catch {
      setRequestsError('Failed to reject request — please try again.')
    } finally {
      setReviewingId(null)
    }
  }

  async function handlePurgeAll() {
    setPurging(true)
    setPurgeError(null)
    try {
      const res = await purgeAllUsers(purgeText)
      setPurgeResult(`Purged ${res.deleted_count} user account(s).`)
      setShowPurgeConfirm(false)
      setPurgeText('')
    } catch {
      setPurgeError('Failed to purge — check the confirmation phrase and try again.')
    } finally {
      setPurging(false)
    }
  }

  async function handleMarkBooked(leadId: string) {
    setMarkingLeadId(leadId)
    setLeadsError(null)
    try {
      const updatedLead = await markLeadBooked(leadId)
      setLeads((prev) => prev.map((lead) => (lead.id === leadId ? updatedLead : lead)))
      setSummary(await getAdminSummary())
    } catch {
      setLeadsError('Failed to mark lead as booked.')
    } finally {
      setMarkingLeadId(null)
    }
  }

  useEffect(() => {
    if (status !== 'authenticated' || !user?.is_admin) return
    void loadDashboard(range)
  }, [range, status, user])

  useEffect(() => {
    if (status !== 'authenticated' || !user?.is_admin) return
    void loadAdminRequests()
  }, [status, user])

  const chartData = useMemo(() => {
    if (!timeseries) return []
    return Object.entries(timeseries.series)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([day, counts]) => ({
        day: day.slice(5),
        sessions: counts.session_start ?? 0,
        signups: counts.signup ?? 0,
        logins: counts.login_success ?? 0,
        itineraries: counts.itinerary_generated ?? 0,
      }))
  }, [timeseries])

  const leadResponseData = useMemo(() => {
    if (!timeseries) return []
    return Object.entries(timeseries.series)
      .sort(([a], [b]) => a.localeCompare(b))
      .filter(([, counts]) => typeof counts.agent_lead_response_avg_hours === 'number')
      .map(([day, counts]) => ({
        day: day.slice(5),
        avg_hours: counts.agent_lead_response_avg_hours ?? 0,
      }))
  }, [timeseries])

  if (status === 'loading' || status === 'idle') {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[var(--_bg)]">
        <Loader2 className="animate-spin text-[var(--_muted-fg)]" size={24} />
      </div>
    )
  }

  if (status === 'unauthenticated') {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-[var(--_bg)] px-4 text-center">
        <p className="text-[var(--_fg)]">You need to be signed in to view this page.</p>
        <Link href="/login?returnTo=/admin" className="btn btn-accent rounded-xl px-5 py-2.5 text-sm font-semibold">
          Log in
        </Link>
      </div>
    )
  }

  if (!user?.is_admin) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-3 bg-[var(--_bg)] px-4 text-center">
        <ShieldAlert className="text-[var(--_destructive)]" size={32} />
        <p className="text-[var(--_fg)]">You're signed in, but this account doesn't have admin access.</p>
        <Link href="/" className="text-sm font-medium text-[var(--_primary)] hover:underline">Back home</Link>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-[var(--_bg)] px-4 py-10">
      <div className="mx-auto max-w-6xl">
        <div className="mb-8 flex items-center justify-between">
          <Link href="/"><WanderplannerLogo size="sm" /></Link>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setRange('7d')}
              className={`rounded-lg px-3 py-1.5 text-xs font-semibold ${range === '7d' ? 'bg-[var(--_primary)] text-white' : 'text-[var(--_muted-fg)]'}`}
            >
              7 days
            </button>
            <button
              type="button"
              onClick={() => setRange('30d')}
              className={`rounded-lg px-3 py-1.5 text-xs font-semibold ${range === '30d' ? 'bg-[var(--_primary)] text-white' : 'text-[var(--_muted-fg)]'}`}
            >
              30 days
            </button>
          </div>
        </div>

        <h1 className="font-display text-2xl font-bold text-[var(--_fg)]">Admin analytics</h1>
        <p className="mt-1 text-sm text-[var(--_muted-fg)]">System health, adoption, usage, and local-expert lead SLA tracking.</p>

        <div className="mt-8 rounded-2xl border border-[var(--_border)] bg-[var(--_card)] p-5">
          <h2 className="flex items-center gap-2 text-base font-semibold text-[var(--_fg)]">
            <ShieldCheck size={18} />
            Admin access requests
            {adminRequests.length > 0 && (
              <span className="rounded-full bg-[var(--_primary)] px-2 py-0.5 text-xs font-bold text-white">{adminRequests.length}</span>
            )}
          </h2>
          <p className="mt-1 text-sm text-[var(--_muted-fg)]">
            Nobody gets admin access automatically — review and approve/reject requests here. Requesters (and all
            existing admins, on new requests) are notified by email.
          </p>

          {requestsLoading && <Loader2 className="mt-4 animate-spin text-[var(--_muted-fg)]" size={20} />}
          {requestsError && <p className="mt-3 text-sm text-[var(--_destructive)]">{requestsError}</p>}

          {!requestsLoading && adminRequests.length === 0 && !requestsError && (
            <p className="mt-4 text-sm text-[var(--_muted-fg)]">No pending requests.</p>
          )}

          {!requestsLoading && adminRequests.length > 0 && (
            <ul className="mt-4 divide-y divide-[var(--_border)]">
              {adminRequests.map((req) => (
                <li key={req.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                  <div>
                    <p className="text-sm font-medium text-[var(--_fg)]">{req.user_display_name || req.user_email}</p>
                    {req.user_email && <p className="text-xs text-[var(--_muted-fg)]">{req.user_email}</p>}
                    {req.message && <p className="mt-1 text-xs italic text-[var(--_muted-fg)]">"{req.message}"</p>}
                  </div>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      disabled={reviewingId === req.id}
                      onClick={() => handleApprove(req.id)}
                      className="btn flex items-center gap-1 rounded-lg bg-green-600 px-3 py-1.5 text-xs font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <Check size={13} /> Approve
                    </button>
                    <button
                      type="button"
                      disabled={reviewingId === req.id}
                      onClick={() => handleReject(req.id)}
                      className="btn btn-outline flex items-center gap-1 rounded-lg border-[var(--_destructive)] px-3 py-1.5 text-xs font-semibold text-[var(--_destructive)] disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <X size={13} /> Reject
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        {loading && (
          <div className="mt-10 flex justify-center"><Loader2 className="animate-spin text-[var(--_muted-fg)]" size={24} /></div>
        )}
        {error && <p className="mt-6 text-sm text-[var(--_destructive)]">{error}</p>}

        {summary && (
          <>
            <section className="mt-10">
              <h2 className="font-display text-xl font-bold text-[var(--_fg)]">System</h2>
              <p className="mt-1 text-sm text-[var(--_muted-fg)]">Storage headroom and cache safety checks.</p>
              <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
                {summary.qdrant_storage ? (
                  <StatCard
                    icon={<Database size={16} className={summary.qdrant_storage.used_fraction != null && summary.qdrant_storage.used_fraction >= 0.7 ? 'text-[var(--_destructive)]' : undefined} />}
                    label="Qdrant storage"
                    value={`${summary.qdrant_storage.estimated_used_mb.toLocaleString()} MB`}
                    sub={
                      summary.qdrant_storage.used_fraction != null
                        ? `${Math.round(summary.qdrant_storage.used_fraction * 100)}% of ${summary.qdrant_storage.limit_mb.toLocaleString()}MB free-tier cap`
                        : 'Estimate unavailable'
                    }
                  />
                ) : (
                  <StatCard icon={<Database size={16} />} label="Qdrant storage" value="—" sub="Unavailable in local/:memory: mode" />
                )}
                {summary.redis_storage ? (
                  <StatCard
                    icon={<Database size={16} className={summary.redis_storage.used_fraction != null && summary.redis_storage.used_fraction >= 0.7 ? 'text-[var(--_destructive)]' : undefined} />}
                    label="Redis cache"
                    value={`${summary.redis_storage.estimated_used_mb.toLocaleString()} MB`}
                    sub={
                      summary.redis_storage.used_fraction != null
                        ? `${Math.round(summary.redis_storage.used_fraction * 100)}% of ${summary.redis_storage.limit_mb.toLocaleString()}MB cap · ${summary.redis_storage.key_count ?? 0} keys`
                        : 'Unavailable'
                    }
                  />
                ) : (
                  <StatCard icon={<Database size={16} />} label="Redis cache" value="—" sub="Unavailable in local fallback mode" />
                )}
              </div>
            </section>

            <section className="mt-10">
              <h2 className="font-display text-xl font-bold text-[var(--_fg)]">Adoption</h2>
              <p className="mt-1 text-sm text-[var(--_muted-fg)]">Sign-ups, sessions, itinerary generation, and the expert-handoff funnel.</p>

              <div className="mt-4 grid grid-cols-2 gap-4 md:grid-cols-4">
                <StatCard icon={<Users size={16} />} label="Total users" value={summary.total_users} />
                <StatCard icon={<Sparkles size={16} />} label="Sign-ups (30d)" value={summary.signups['30d']} sub={`${summary.signups.today} today`} />
                <StatCard icon={<LogIn size={16} />} label="Login success rate" value={summary.logins.success_rate_30d != null ? `${Math.round(summary.logins.success_rate_30d * 100)}%` : '—'} sub={`${summary.logins.success_30d} ok · ${summary.logins.failed_30d} failed`} />
                <StatCard icon={<Sparkles size={16} />} label="Itineraries (30d)" value={summary.itineraries.generated_30d} sub={`${summary.itineraries.failed_30d} failed`} />
              </div>

              <h3 className="mt-8 text-base font-semibold text-[var(--_fg)]">Agent Leads</h3>
              <div className="mt-3 grid grid-cols-2 gap-4 md:grid-cols-4">
                <StatCard
                  icon={<LogIn size={16} />}
                  label="Avg response time"
                  value={summary.agent_leads.response_time_avg_hours != null ? `${summary.agent_leads.response_time_avg_hours.toFixed(1)}h` : '—'}
                  valueClassName="font-mono"
                  sub={
                    summary.agent_leads.response_time_p50_hours != null && summary.agent_leads.response_time_p90_hours != null
                      ? `p50 ${summary.agent_leads.response_time_p50_hours.toFixed(1)}h · p90 ${summary.agent_leads.response_time_p90_hours.toFixed(1)}h`
                      : 'No responded leads yet'
                  }
                />
                <StatCard
                  icon={<AlertTriangle size={16} />}
                  label="SLA breach rate"
                  value={summary.agent_leads.sla_breach_rate != null ? `${Math.round(summary.agent_leads.sla_breach_rate * 100)}%` : '—'}
                  valueStyle={slaBreachStyle(summary.agent_leads.sla_breach_rate)}
                  sub="Escalated leads / created leads (30d)"
                />
                <StatCard
                  icon={<Users size={16} />}
                  label="Leads created"
                  value={summary.agent_leads.created_total}
                  sub={
                    summary.agent_leads.top_destinations.length > 0
                      ? `Top: ${summary.agent_leads.top_destinations.map((row) => `${row.destination} (${row.count})`).join(', ')}`
                      : 'No destinations yet'
                  }
                />
                <StatCard icon={<Check size={16} />} label="Marked booked" value={summary.agent_leads.marked_booked_total} sub={`${summary.agent_leads.responded_total} responded · ${summary.agent_leads.reassurance_sent_total} reassured`} />
              </div>

              <h3 className="mt-8 text-base font-semibold text-[var(--_fg)]">Activity over time</h3>
              <div className="mt-3 rounded-2xl border border-[var(--_border)] bg-[var(--_card)] p-4">
                <div className="overflow-x-auto">
                  <div className="h-72 min-w-[520px]">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={chartData}>
                        <CartesianGrid strokeDasharray="3 3" stroke="var(--_border)" />
                        <XAxis dataKey="day" fontSize={12} />
                        <YAxis fontSize={12} allowDecimals={false} />
                        <Tooltip />
                        <Legend />
                        {ACTIVITY_SERIES.map((series) => (
                          <Line key={series.key} type="monotone" dataKey={series.key} stroke={series.stroke} strokeWidth={2} dot={false} />
                        ))}
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                </div>
                <ul className="mt-3 grid gap-2 text-sm text-[var(--_fg)] sm:grid-cols-2">
                  {ACTIVITY_SERIES.map((series) => (
                    <li key={series.key} className="flex items-center gap-2 rounded-lg border border-[var(--_border)] px-3 py-2">
                      <span aria-hidden="true" className="h-0.5 w-6 shrink-0 rounded-full" style={{ backgroundColor: series.stroke }} />
                      <span className="font-medium">{series.label}</span>
                    </li>
                  ))}
                </ul>
              </div>

              <h3 className="mt-8 text-base font-semibold text-[var(--_fg)]">Response-time trend</h3>
              <div className="mt-3 rounded-2xl border border-[var(--_border)] bg-[var(--_card)] p-4">
                {leadResponseData.length > 0 ? (
                  <div className="overflow-x-auto">
                    <div className="h-72 min-w-[520px]">
                      <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={leadResponseData}>
                          <CartesianGrid strokeDasharray="3 3" stroke="var(--_border)" />
                          <XAxis dataKey="day" fontSize={12} />
                          <YAxis fontSize={12} />
                          <Tooltip />
                          <Legend />
                          {LEAD_RESPONSE_SERIES.map((series) => (
                            <Line key={series.key} type="monotone" dataKey={series.key} stroke={series.stroke} strokeWidth={2} dot={false} />
                          ))}
                        </LineChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                ) : (
                  <p className="text-sm text-[var(--_muted-fg)]">No responded leads yet, so there’s no response-time trend to plot.</p>
                )}
              </div>

              <h3 className="mt-8 text-base font-semibold text-[var(--_fg)]">Latest lead queue</h3>
              {leadsError && <p className="mt-2 text-sm text-[var(--_destructive)]">{leadsError}</p>}
              <div className="mt-3 overflow-x-auto rounded-2xl border border-[var(--_border)] bg-[var(--_card)]">
                <table className="min-w-full text-left text-sm">
                  <thead className="text-[var(--_muted-fg)]">
                    <tr className="border-b border-[var(--_border)]">
                      <th scope="col" className="px-4 py-3 font-medium">Destination</th>
                      <th scope="col" className="px-4 py-3 font-medium">Created</th>
                      <th scope="col" className="px-4 py-3 font-medium">Status</th>
                      <th scope="col" className="px-4 py-3 font-medium">Response time</th>
                      <th scope="col" className="px-4 py-3 font-medium">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {leads.length === 0 ? (
                      <tr>
                        <td colSpan={5} className="px-4 py-6 text-center text-[var(--_muted-fg)]">
                          No leads yet.
                        </td>
                      </tr>
                    ) : (
                      leads.map((lead) => (
                        <tr key={lead.id} className="border-b border-[var(--_border)] last:border-0">
                          <td className="px-4 py-3">
                            <div>
                              <p className="font-medium text-[var(--_fg)]">{lead.destination}</p>
                              <p className="text-xs text-[var(--_muted-fg)]">{lead.email}</p>
                            </div>
                          </td>
                          <td className="px-4 py-3 text-[var(--_muted-fg)]" title={lead.created_at}>
                            {formatRelativeTime(lead.created_at)}
                          </td>
                          <td className="px-4 py-3">
                            <span className={leadStatusBadge(lead)}>{leadStatusLabel(lead.status)}</span>
                          </td>
                          <td className="px-4 py-3 text-[var(--_muted-fg)]">
                            {lead.response_time_hours != null ? `${lead.response_time_hours.toFixed(1)}h` : '—'}
                          </td>
                          <td className="px-4 py-3">
                            <button
                              type="button"
                              disabled={Boolean(lead.marked_booked_at) || markingLeadId === lead.id}
                              onClick={() => handleMarkBooked(lead.id)}
                              className="btn btn-outline rounded-xl px-3 py-1.5 text-xs disabled:opacity-50"
                            >
                              {markingLeadId === lead.id ? (
                                <><Loader2 size={13} className="animate-spin" /> Marking…</>
                              ) : lead.marked_booked_at ? 'Booked' : 'Mark booked'}
                            </button>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </section>

            <section className="mt-10">
              <h2 className="font-display text-xl font-bold text-[var(--_fg)]">Usage &amp; Cost</h2>
              <p className="mt-1 text-sm text-[var(--_muted-fg)]">External API demand and spend approximations.</p>
              <div className="mt-4 grid grid-cols-2 gap-4 md:grid-cols-4">
                <StatCard icon={<IndianRupee size={16} />} label="Gemini requests (30d)" value={summary.cost_usage.gemini_requests_30d} />
                <StatCard icon={<IndianRupee size={16} />} label="Gemini tokens (30d)" value={summary.cost_usage.gemini_tokens_30d.toLocaleString()} />
                <StatCard icon={<IndianRupee size={16} />} label="Est. Gemini cost (30d)" value={`₹${summary.cost_usage.gemini_estimated_cost_inr_30d.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`} sub="Approximate — monitoring only" />
                <StatCard icon={<IndianRupee size={16} />} label="Pexels calls (30d)" value={summary.cost_usage.pexels_calls_30d} sub="Free tier: 200 req/hour" />
              </div>
            </section>

            <div className="mt-10 border-t border-[var(--_border)] pt-6">
              <h2 className="flex items-center gap-2 text-base font-semibold text-[var(--_destructive)]">
                <AlertTriangle size={18} />
                Danger zone — bulk data purge
              </h2>
              <p className="mt-2 text-sm text-[var(--_muted-fg)]">
                Permanently delete every non-admin user account and their personal data in one go (e.g. to fulfil an
                org-wide data-deletion request). Admin accounts are never deleted by this action. This cannot be undone.
              </p>

              {purgeResult && <p className="mt-3 text-sm font-medium text-[var(--_fg)]">{purgeResult}</p>}

              {!showPurgeConfirm ? (
                <button
                  type="button"
                  onClick={() => setShowPurgeConfirm(true)}
                  className="btn btn-outline mt-4 rounded-xl border-[var(--_destructive)] px-4 py-2 text-sm font-semibold text-[var(--_destructive)] hover:bg-[var(--_destructive)] hover:text-white"
                >
                  Purge all user data
                </button>
              ) : (
                <div className="mt-4 space-y-3 rounded-xl border border-[var(--_destructive)] bg-[var(--_destructive)]/5 p-4">
                  <p className="text-sm font-medium text-[var(--_fg)]">
                    Type <span className="font-mono">{PURGE_PHRASE}</span> to confirm.
                  </p>
                  <label htmlFor={purgeConfirmationInputId} className="block text-sm font-medium text-[var(--_fg)]">
                    Confirmation phrase
                  </label>
                  <input
                    id={purgeConfirmationInputId}
                    type="text"
                    value={purgeText}
                    onChange={(e) => setPurgeText(e.target.value)}
                    placeholder={PURGE_PHRASE}
                    maxLength={PURGE_PHRASE.length}
                    className="input w-full rounded-xl border border-[var(--_border)] bg-[var(--_card)] px-3.5 py-2.5 text-sm text-[var(--_fg)] focus:border-[var(--_primary)] focus:outline-none"
                  />
                  {purgeError && <p className="text-sm text-[var(--_destructive)]">{purgeError}</p>}
                  <div className="flex gap-2">
                    <button
                      type="button"
                      disabled={purgeText !== PURGE_PHRASE || purging}
                      onClick={handlePurgeAll}
                      className="btn rounded-xl bg-[var(--_destructive)] px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {purging && <Loader2 size={14} className="mr-1.5 inline animate-spin" />}
                      {purging ? 'Purging…' : 'Permanently purge all users'}
                    </button>
                    <button
                      type="button"
                      onClick={() => { setShowPurgeConfirm(false); setPurgeText('') }}
                      className="btn btn-outline rounded-xl px-4 py-2 text-sm font-semibold"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
