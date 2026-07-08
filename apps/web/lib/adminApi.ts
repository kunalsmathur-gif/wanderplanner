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
  cost_usage: {
    gemini_requests_30d: number
    gemini_tokens_30d: number
    gemini_estimated_cost_inr_30d: number
    pexels_calls_30d: number
  }
}

export interface AdminTimeseries {
  range: string
  series: Record<string, Record<string, number>>
}

export async function getAdminSummary(): Promise<AdminSummary> {
  const { data } = await adminApi.get('/api/admin/metrics/summary')
  return data as AdminSummary
}

export async function getAdminTimeseries(range: '7d' | '30d' = '30d'): Promise<AdminTimeseries> {
  const { data } = await adminApi.get('/api/admin/metrics/timeseries', { params: { range } })
  return data as AdminTimeseries
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
