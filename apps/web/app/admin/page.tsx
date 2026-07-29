'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { Loader2, ShieldAlert, Users, LogIn, Sparkles, IndianRupee, AlertTriangle, ShieldCheck, Check, X } from 'lucide-react'
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from 'recharts'
import { useAuthStore } from '@/store/authStore'
import {
  getAdminSummary,
  getAdminTimeseries,
  purgeAllUsers,
  listAdminRequests,
  approveAdminRequest,
  rejectAdminRequest,
  type AdminSummary,
  type AdminTimeseries,
  type AdminRequest,
} from '@/lib/adminApi'
import { WanderplannerLogo } from '@/components/common/WanderplannerLogo'

const ACTIVITY_SERIES = [
  { key: 'sessions', label: 'Sessions', stroke: '#3b82f6' },
  { key: 'signups', label: 'Sign-ups', stroke: '#22c55e' },
  { key: 'logins', label: 'Logins', stroke: '#f59e0b' },
  { key: 'itineraries', label: 'Itineraries', stroke: '#a855f7' },
] as const

function StatCard({ icon, label, value, sub }: { icon: React.ReactNode; label: string; value: string | number; sub?: string }) {
  return (
    <div className="rounded-2xl border border-[var(--_border)] bg-[var(--_card)] p-5">
      <div className="flex items-center gap-2 text-[var(--_muted-fg)]">
        {icon}
        <span className="text-xs font-medium uppercase tracking-wide">{label}</span>
      </div>
      <p className="mt-2 text-2xl font-bold text-[var(--_fg)] [font-family:var(--font-display)]">{value}</p>
      {sub && <p className="mt-1 text-xs text-[var(--_muted-fg)]">{sub}</p>}
    </div>
  )
}

export default function AdminDashboardPage() {
  const purgeConfirmationInputId = 'purge-users-confirmation'
  const status = useAuthStore((s) => s.status)
  const user = useAuthStore((s) => s.user)

  const [summary, setSummary] = useState<AdminSummary | null>(null)
  const [timeseries, setTimeseries] = useState<AdminTimeseries | null>(null)
  const [range, setRange] = useState<'7d' | '30d'>('30d')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

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
    try {
      setAdminRequests(await listAdminRequests('pending'))
    } catch {
      setRequestsError('Failed to load admin access requests.')
    } finally {
      setRequestsLoading(false)
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

  useEffect(() => {
    if (status !== 'authenticated' || !user?.is_admin) return
    let cancelled = false
    setLoading(true)
    Promise.all([getAdminSummary(), getAdminTimeseries(range)])
      .then(([s, t]) => { if (!cancelled) { setSummary(s); setTimeseries(t) } })
      .catch(() => { if (!cancelled) setError('Failed to load metrics.') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [status, user, range])

  useEffect(() => {
    if (status !== 'authenticated' || !user?.is_admin) return
    loadAdminRequests()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, user])

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

  // Merge the day-keyed series map into rows recharts can plot.
  const chartData = timeseries
    ? Object.entries(timeseries.series)
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([day, counts]) => ({
          day: day.slice(5), // MM-DD
          sessions: counts.session_start ?? 0,
          signups: counts.signup ?? 0,
          logins: counts.login_success ?? 0,
          itineraries: counts.itinerary_generated ?? 0,
        }))
    : []

  return (
    <div className="min-h-screen bg-[var(--_bg)] px-4 py-10">
      <div className="mx-auto max-w-5xl">
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

        <h1 className="text-2xl font-bold text-[var(--_fg)] [font-family:var(--font-display)]">Admin analytics</h1>
        <p className="mt-1 text-sm text-[var(--_muted-fg)]">Sessions, sign-ups, generations, and API cost tracking.</p>

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
            <div className="mt-6 grid grid-cols-2 gap-4 md:grid-cols-4">
              <StatCard icon={<Users size={16} />} label="Total users" value={summary.total_users} />
              <StatCard icon={<Sparkles size={16} />} label="Sign-ups (30d)" value={summary.signups['30d']} sub={`${summary.signups.today} today`} />
              <StatCard icon={<LogIn size={16} />} label="Login success rate" value={summary.logins.success_rate_30d != null ? `${Math.round(summary.logins.success_rate_30d * 100)}%` : '—'} sub={`${summary.logins.success_30d} ok · ${summary.logins.failed_30d} failed`} />
              <StatCard icon={<Sparkles size={16} />} label="Itineraries (30d)" value={summary.itineraries.generated_30d} sub={`${summary.itineraries.failed_30d} failed`} />
            </div>

            <h2 className="mt-8 text-base font-semibold text-[var(--_fg)]">Cost & usage metrics</h2>
            <div className="mt-3 grid grid-cols-2 gap-4 md:grid-cols-4">
              <StatCard icon={<IndianRupee size={16} />} label="Gemini requests (30d)" value={summary.cost_usage.gemini_requests_30d} />
              <StatCard icon={<IndianRupee size={16} />} label="Gemini tokens (30d)" value={summary.cost_usage.gemini_tokens_30d.toLocaleString()} />
              <StatCard icon={<IndianRupee size={16} />} label="Est. Gemini cost (30d)" value={`₹${summary.cost_usage.gemini_estimated_cost_inr_30d.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`} sub="Approximate — for monitoring only" />
              <StatCard icon={<IndianRupee size={16} />} label="Pexels calls (30d)" value={summary.cost_usage.pexels_calls_30d} sub="Free tier: 200 req/hour" />
            </div>

            <h2 className="mt-8 text-base font-semibold text-[var(--_fg)]">Activity over time</h2>
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
                        <Line
                          key={series.key}
                          type="monotone"
                          dataKey={series.key}
                          stroke={series.stroke}
                          strokeWidth={2}
                          dot={false}
                        />
                      ))}
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>
              <p className="mt-3 text-xs text-[var(--_muted-fg)]">
                On small screens, scroll horizontally for the full chart. The data table below lists the same values as
                text.
              </p>
              <ul className="mt-3 grid gap-2 text-sm text-[var(--_fg)] sm:grid-cols-2">
                {ACTIVITY_SERIES.map((series) => (
                  <li key={series.key} className="flex items-center gap-2 rounded-lg border border-[var(--_border)] px-3 py-2">
                    <span
                      aria-hidden="true"
                      className="h-0.5 w-6 shrink-0 rounded-full"
                      style={{ backgroundColor: series.stroke }}
                    />
                    <span className="font-medium">{series.label}</span>
                  </li>
                ))}
              </ul>
              <div className="mt-4 overflow-x-auto">
                <table className="min-w-full text-left text-sm">
                  <thead className="text-[var(--_muted-fg)]">
                    <tr className="border-b border-[var(--_border)]">
                      <th scope="col" className="px-3 py-2 font-medium">Day</th>
                      {ACTIVITY_SERIES.map((series) => (
                        <th key={series.key} scope="col" className="px-3 py-2 font-medium">
                          {series.label}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {chartData.map((row) => (
                      <tr key={row.day} className="border-b border-[var(--_border)] last:border-0">
                        <th scope="row" className="px-3 py-2 font-medium text-[var(--_fg)]">
                          {row.day}
                        </th>
                        {ACTIVITY_SERIES.map((series) => (
                          <td key={series.key} className="px-3 py-2 text-[var(--_muted-fg)]">
                            {row[series.key]}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

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
                    className="input w-full rounded-xl border border-[var(--_border)] bg-[var(--_card)] py-2.5 px-3.5 text-sm text-[var(--_fg)] focus:border-[var(--_primary)] focus:outline-none"
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
