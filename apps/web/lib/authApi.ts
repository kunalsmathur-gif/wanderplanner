import axios from 'axios'

const authApi = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000',
  timeout: 15_000,
  // Required so the httpOnly session cookies set by the FastAPI backend are
  // sent on/accepted from every request — the frontend and backend are on
  // different origins in most deployments (Vercel + Railway).
  withCredentials: true,
})

export interface AuthUser {
  id: string
  email: string | null
  display_name: string | null
  is_admin: boolean
  auth_provider: 'password' | 'google'
}

export async function signup(input: {
  email: string
  password: string
  display_name?: string
  consent_accepted: boolean
}): Promise<AuthUser> {
  const { data } = await authApi.post('/api/auth/signup', input)
  return data as AuthUser
}

export async function login(input: { email: string; password: string }): Promise<AuthUser> {
  const { data } = await authApi.post('/api/auth/login', input)
  return data as AuthUser
}

export async function logout(): Promise<void> {
  await authApi.post('/api/auth/logout')
}

export async function fetchCurrentUser(): Promise<AuthUser | null> {
  try {
    const { data } = await authApi.get('/api/auth/me')
    return data as AuthUser
  } catch {
    return null
  }
}

/** Silently exchanges the longer-lived refresh-token cookie for a fresh
 * access token when the 15-minute access token has expired but the user is
 * still genuinely signed in (refresh token lasts 30 days). Returns null on
 * any failure (no refresh cookie, revoked/expired session, network error) —
 * callers should treat that the same as "not signed in", never throw. */
export async function refreshSession(): Promise<AuthUser | null> {
  try {
    const { data } = await authApi.post('/api/auth/refresh')
    return data as AuthUser
  } catch {
    return null
  }
}

/** Public, non-secret capability flags for the auth UI (e.g. whether Google
 * OAuth is configured on the backend). Defaults to disabled on any failure
 * so the UI fails closed (hides the button) rather than showing a broken one. */
export async function fetchAuthConfig(): Promise<{ google_sso_enabled: boolean }> {
  try {
    const { data } = await authApi.get('/api/auth/config')
    return { google_sso_enabled: Boolean(data?.google_sso_enabled) }
  } catch {
    return { google_sso_enabled: false }
  }
}

export async function forgotPassword(email: string): Promise<void> {
  await authApi.post('/api/auth/password/forgot', { email })
}

export async function resetPassword(token: string, new_password: string): Promise<void> {
  await authApi.post('/api/auth/password/reset', { token, new_password })
}

export async function deleteMyAccount(): Promise<void> {
  await authApi.delete('/api/auth/me')
}

export function googleSignInUrl(returnTo: string = '/'): string {
  const base = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'
  return `${base}/api/auth/google/start?return_to=${encodeURIComponent(returnTo)}`
}

/** Extracts a friendly error message from an axios error for form display. */
export function authErrorMessage(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const detail = err.response?.data?.detail
    if (typeof detail === 'string') return detail
  }
  return 'Something went wrong. Please try again.'
}
