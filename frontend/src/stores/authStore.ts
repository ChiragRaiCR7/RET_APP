/**
 * Auth Store — JWT authentication state for RET v4
 *
 * State:
 *   user   — the logged-in user as returned by /auth/login and /auth/me
 *   token  — JWT access token (short-lived)
 *
 * The refresh token is an HttpOnly cookie set by the server and is never visible to JS.
 * On 401 the api.ts interceptor calls refreshToken() -> POST /auth/refresh, and on a
 * page load the router guard restores the session the same way. The access token
 * therefore lives in memory only and is never written to Web Storage, where any
 * injected script could read it.
 */

import { defineStore } from 'pinia'
import api from '@/utils/api'

export interface AuthUser {
  id: number
  username: string
  role: string | { value: string }
  is_active?: boolean
  is_locked?: boolean
  created_at?: string
  session_id?: string
  [key: string]: unknown
}

interface LoginResponse {
  access_token: string
  token_type: string
  user: AuthUser
}

// Earlier builds wrote the access token here but never read it back; purge those copies.
const LEGACY_STORAGE_KEY = 'ret_auth_v4'
try {
  window.localStorage.removeItem(LEGACY_STORAGE_KEY)
  window.sessionStorage.removeItem(LEGACY_STORAGE_KEY)
} catch {
  // Storage can be unavailable (privacy mode); nothing to purge then.
}

interface HttpErrorLike {
  message?: string
  response?: { status?: number; data?: { detail?: unknown; message?: unknown; error?: unknown } }
}

export function extractError(err: unknown): string {
  const e = err as HttpErrorLike | undefined
  const data = e?.response?.data
  const detail = data?.detail ?? data?.message ?? data?.error
  return (typeof detail === 'string' && detail) || e?.message || 'Request failed'
}

export function normalizeRole(role: AuthUser['role'] | null | undefined): string {
  if (!role) return ''
  return String(typeof role === 'object' ? role.value : role).toLowerCase()
}

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: null as AuthUser | null,
    token: null as string | null,
    isLoading: false,
    // Single-flight refresh: concurrent callers await the same promise.
    _refreshPromise: null as Promise<boolean> | null,
    lastAuthError: null as string | null,
    remember: false,
  }),

  getters: {
    isAuthenticated: (state): boolean => !!state.token,
    isAdmin: (state): boolean => {
      const role = normalizeRole(state.user?.role)
      return role === 'admin' || role === 'super_admin'
    },
  },

  actions: {
    _setAuth(token: string | null, user: AuthUser | null, remember = false): void {
      this.token = token
      this.user = user
      this.remember = remember
    },

    _clearAuthState(): void {
      this._setAuth(null, null, false)
      this._refreshPromise = null
      this.lastAuthError = null
    },

    async login(username: string, password: string, remember = false): Promise<LoginResponse> {
      this.isLoading = true
      this.lastAuthError = null
      try {
        const resp = await api.post<LoginResponse>('/auth/login', { username, password })
        if (!resp.data?.access_token) throw new Error('Login response missing access_token')
        this._setAuth(resp.data.access_token, resp.data.user ?? null, remember)
        return resp.data
      } catch (err) {
        this._clearAuthState()
        this.lastAuthError = extractError(err)
        throw err
      } finally {
        this.isLoading = false
      }
    },

    async fetchMe(): Promise<void> {
      if (!this.token) return
      try {
        const resp = await api.get<AuthUser>('/auth/me')
        this.user = resp.data
      } catch (err) {
        console.error('Failed to fetch user:', err)
        if ((err as HttpErrorLike).response?.status === 401) this._clearAuthState()
      }
    },

    async logout(): Promise<void> {
      try {
        if (this.token) {
          if (this.user?.session_id) {
            try {
              await api.post(`/ai/clear-memory/${this.user.session_id}`)
            } catch (err) {
              console.error('Failed to clear AI memory:', err)
            }
          }
          try {
            await api.post('/auth/logout')
          } catch (err) {
            console.error('Logout error (non-fatal):', err)
          }
        }
      } finally {
        this._clearAuthState()
      }
    },

    /**
     * Refreshes the access token through the HttpOnly cookie. Runs once even when many
     * requests fail together; resolves true on success and false when the cookie is
     * missing or expired or the server is down.
     */
    async refreshToken(): Promise<boolean> {
      if (this._refreshPromise) {
        try {
          return await this._refreshPromise
        } catch {
          return false
        }
      }
      this.lastAuthError = null
      this._refreshPromise = (async () => {
        try {
          const resp = await api.post<{ access_token?: string }>('/auth/refresh', {})
          const accessToken = resp.data?.access_token
          if (!accessToken) throw new Error('Refresh response missing access_token')
          // The server does not resend the user on refresh.
          this._setAuth(accessToken, this.user, this.remember)
          return true
        } catch (err) {
          const status = (err as HttpErrorLike).response?.status
          if (status === 401 || status === 403) {
            this._clearAuthState()
            return false
          }
          // Server failure: drop the token so requests stop retrying, keep the user.
          this._setAuth(null, this.user, this.remember)
          this.lastAuthError = extractError(err)
          console.error('Refresh failed (server error):', err)
          return false
        } finally {
          this._refreshPromise = null
        }
      })()
      return await this._refreshPromise
    },
  },
})
