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
