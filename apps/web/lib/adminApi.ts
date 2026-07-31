import axios from 'axios'

const adminApi = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000',
  timeout: 15_000,
  withCredentials: true,
})

export interface AdminSummary {
  total_users: number
  signups: { today: number; '7d': number; '30d': number }
  sessions: { today: number; '7d': number; '30d': number }
  logins: { success_30d: number; failed_30d: number; success_rate_30d: number | null }
  itineraries: { generated_30d: number; failed_30d: number }
  agent_leads: {
    created_total: number
    responded_total: number
    escalated_total: number
    reassurance_sent_total: number
    response_time_avg_hours: number | null
    response_time_p50_hours: number | null
    response_time_p90_hours: number | null
    sla_breach_rate: number | null
    marked_booked_total: number
    top_destinations: Array<{ destination: string; count: number }>
  }
  cost_usage: {
    gemini_requests_30d: number
    gemini_tokens_30d: number
    gemini_estimated_cost_inr_30d: number
    pexels_calls_30d: number
  }
  // Estimate of Qdrant Cloud free-tier RAM usage (1GiB cap) — null if the
  // estimate couldn't be computed (e.g. local :memory: mode, Qdrant outage).
  qdrant_storage: {
    estimated_used_mb: number
    limit_mb: number
    used_fraction: number | null
    collections: Record<string, { points_count: number; estimated_mb: number }>
  } | null
  // Redis cache memory usage (share links + travel tips) — null if running
  // the local in-process fallback (no REDIS_URL) or on a Redis error.
  redis_storage: {
    estimated_used_mb: number
    limit_mb: number
    used_fraction: number | null
    key_count: number | null
  } | null
}

export interface AdminTimeseries {
  range: string
  series: Record<string, Record<string, number>>
}

export interface AdminLead {
  id: string
  user_id: string | null
  email: string
  destination: string
  trip_config_summary: Record<string, unknown>
  custom_notes: string | null
  created_at: string
  responded_at: string | null
  escalated_at: string | null
  reassurance_sent_at: string | null
  marked_booked_at: string | null
  status: 'pending' | 'responded' | 'escalated' | 'reassured'
  response_time_hours: number | null
}

export async function getAdminSummary(): Promise<AdminSummary> {
  const { data } = await adminApi.get('/api/admin/metrics/summary')
  return data as AdminSummary
}

export async function getAdminTimeseries(range: '7d' | '30d' = '30d'): Promise<AdminTimeseries> {
  const { data } = await adminApi.get('/api/admin/metrics/timeseries', { params: { range } })
  return data as AdminTimeseries
}

export async function getAdminLeads(limit = 50): Promise<AdminLead[]> {
  const { data } = await adminApi.get('/api/admin/leads', { params: { limit } })
  return data as AdminLead[]
}

export async function markLeadBooked(id: string): Promise<AdminLead> {
  const { data } = await adminApi.post(`/api/admin/leads/${id}/mark-booked`)
  return data as AdminLead
}

export async function markLeadResponded(id: string): Promise<AdminLead> {
  const { data } = await adminApi.post(`/api/admin/leads/${id}/mark-responded`)
  return data as AdminLead
}

export async function deleteUser(userId: string): Promise<void> {
  await adminApi.delete(`/api/admin/users/${userId}`)
}

export async function purgeAllUsers(confirm: string): Promise<{ deleted_count: number }> {
  const { data } = await adminApi.post('/api/admin/users/purge-all', { confirm })
  return data as { deleted_count: number }
}

// ── Admin access requests ────────────────────────────────────────────────

export interface AdminRequest {
  id: string
  user_id: string
  user_email: string | null
  user_display_name: string | null
  status: 'pending' | 'approved' | 'rejected'
  message: string | null
  created_at: string
  reviewed_at: string | null
}

/** Any authenticated (non-admin) user can call this to ask for admin access.
 * Never grants access itself — creates a pending request that existing
 * admins see in the console and are emailed about. */
export async function requestAdminAccess(message?: string): Promise<AdminRequest> {
  const { data } = await adminApi.post('/api/admin/requests', { message: message || null })
  return data as AdminRequest
}

/** Read-only lookup of the current user's own most recent admin request
 * (used by the account page to show "pending" / "declined" state). */
export async function getMyAdminRequest(): Promise<AdminRequest | null> {
  const { data } = await adminApi.get('/api/admin/requests/me')
  return data as AdminRequest | null
}

export async function listAdminRequests(status: 'pending' | 'approved' | 'rejected' | 'all' = 'pending'): Promise<AdminRequest[]> {
  const { data } = await adminApi.get('/api/admin/requests', { params: { status } })
  return data as AdminRequest[]
}

export async function approveAdminRequest(requestId: string): Promise<AdminRequest> {
  const { data } = await adminApi.post(`/api/admin/requests/${requestId}/approve`)
  return data as AdminRequest
}

export async function rejectAdminRequest(requestId: string): Promise<AdminRequest> {
  const { data } = await adminApi.post(`/api/admin/requests/${requestId}/reject`)
  return data as AdminRequest
}
