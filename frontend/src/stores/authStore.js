/**
 * Auth Store — JWT authentication state for RET v4
 *
 * State:
 *   user   — { id, username, role, ... } of the logged-in user
 *   token  — JWT access token (short-lived)
 *
 * Refresh token is an HttpOnly cookie set by the server;
 * it’s never accessible to JS. On 401, api.js interceptor
 * calls refreshToken() -> POST /auth/refresh (cookie sent by browser).
 *
 * Non-breaking improvements:
 * - Optional persistence controlled by env (defaults to true to preserve your current behavior)
 * - Safer storage parsing/writing + cleanup
 * - isAdmin supports 'admin' and 'super_admin'
 * - Consistent error extraction across endpoints
 * - Keeps axios Authorization header in sync
 */

import { defineStore } from 'pinia'
import api from '@/utils/api'

const STORAGE_KEY = 'ret_auth_v4'

// ✅ Preserve existing default behavior (true), but allow env override:
// Set VITE_PERSIST_AUTH=false to disable persistence (memory-only)
const PERSIST_AUTH = String(import.meta?.env?.VITE_PERSIST_AUTH ?? 'true') === 'true'

function getStorage(remember) {
  return remember ? window.localStorage : window.sessionStorage
}

function safeJsonParse(raw) {
  if (!raw) return null
  try {
    return JSON.parse(raw)
  } catch {
    return null
  }
}

function readPersisted() {
  if (!PERSIST_AUTH) return null

  // Prefer localStorage, fallback to sessionStorage
  const raw =
    window.localStorage.getItem(STORAGE_KEY) ||
    window.sessionStorage.getItem(STORAGE_KEY)

  const saved = safeJsonParse(raw)
  if (!saved || typeof saved !== 'object') return null

  // Minimal shape validation
  if (!saved.token) return null
  return saved
}

function persistAuth({ token, user, remember }) {
  if (!PERSIST_AUTH) return
  const storage = getStorage(remember)
  storage.setItem(STORAGE_KEY, JSON.stringify({ token, user, remember: !!remember }))

  // Ensure the other storage doesn't hold stale data
  const other = remember ? window.sessionStorage : window.localStorage
  other.removeItem(STORAGE_KEY)
}

function clearPersisted() {
  if (!PERSIST_AUTH) return
  window.localStorage.removeItem(STORAGE_KEY)
  window.sessionStorage.removeItem(STORAGE_KEY)
}

function setAxiosToken(token) {
  // Keep axios Authorization header in sync
  if (token) {
    api.defaults.headers.common.Authorization = `Bearer ${token}`
  } else {
    delete api.defaults.headers.common.Authorization
  }
}

function extractError(err) {
  return (
    err?.response?.data?.detail ||
    err?.response?.data?.message ||
    err?.response?.data?.error ||
    err?.message ||
    'Request failed'
  )
}

function normalizeRole(role) {
  if (!role) return ''
  return String(role?.value ?? role).toLowerCase()
}

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: null,
    token: null,
    isLoading: false,

    // ✅ Single-flight refresh control
    _refreshPromise: null,

    // Optional: surface refresh failures to UI
    lastAuthError: null,

    // track whether storage is "remember" or session
    remember: false
  }),

  getters: {
    isAuthenticated: (state) => !!state.token,

    // ✅ Support both admin and super_admin
    isAdmin: (state) => {
      const role = normalizeRole(state.user?.role)
      return role === 'admin' || role === 'super_admin'
    }
  },

  actions: {
    /**
     * Call once on app start (e.g., in main.js) to restore auth.
     * Optional but recommended if persistence is enabled.
     */
    initFromStorage() {
      const saved = readPersisted()
      if (!saved?.token) return

      this.token = saved.token
      this.user = saved.user || null
      this.remember = !!saved.remember
      setAxiosToken(this.token)
    },

    /**
     * Internal helper: set auth state consistently
     */
    _setAuth(token, user, remember = false) {
      this.token = token || null
      this.user = user || null
      this.remember = !!remember
      setAxiosToken(this.token)

      if (this.token) {
        persistAuth({ token: this.token, user: this.user, remember: this.remember })
      } else {
        clearPersisted()
      }
    },

    /**
     * Optional internal helper: clears everything and resets refresh lock
     */
    _clearAuthState() {
      this._setAuth(null, null, false)
      this._refreshPromise = null
      this.lastAuthError = null
    },

    async login(username, password, remember = false) {
      this.isLoading = true
      this.lastAuthError = null

      try {
        const resp = await api.post('/auth/login', { username, password })

        // Expected: { access_token, token_type, user }
        const accessToken = resp?.data?.access_token
        const user = resp?.data?.user

        if (!accessToken) {
          throw new Error('Login response missing access_token')
        }

        this._setAuth(accessToken, user, remember)
        return resp.data
      } catch (err) {
        this._clearAuthState()
        this.lastAuthError = extractError(err)
        throw err
      } finally {
        this.isLoading = false
      }
    },

    async fetchMe() {
      if (!this.token) return

      try {
        const resp = await api.get('/auth/me')
        this.user = resp.data

        // Keep persisted state updated
        persistAuth({ token: this.token, user: this.user, remember: this.remember })
      } catch (e) {
        console.error('Failed to fetch user:', e)

        if (e?.response?.status === 401) {
          // Token invalid => clear local state
          this._clearAuthState()
        }
      }
    },

    async logout() {
      try {
        // Only call backend logout if we have a token
        if (this.token) {
          // Optional: clear AI memory (non-fatal if fails)
          if (this.user?.session_id) {
            try {
              await api.post(`/ai/clear-memory/${this.user.session_id}`)
            } catch (e) {
              console.error('Failed to clear AI memory:', e)
            }
          }

          try {
            await api.post('/auth/logout')
          } catch (e) {
            console.error('Logout error (non-fatal):', e)
          }
        }
      } finally {
        // Always clear local state
        this._clearAuthState()
      }
    },

    /**
     * Called by interceptor when a request returns 401.
     * Must:
     * - run only once even if many requests fail together
     * - return true if refreshed successfully
     * - return false if refresh cookie is missing/expired or server is down
     */
    async refreshToken() {
      // ✅ If a refresh is already running, await the same promise
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
          // Refresh token is HttpOnly cookie; browser sends it automatically
          const resp = await api.post('/auth/refresh', {})

          const accessToken = resp?.data?.access_token
          if (!accessToken) {
            throw new Error('Refresh response missing access_token')
          }

          // keep existing user (server usually doesn't resend user on refresh)
          this._setAuth(accessToken, this.user, this.remember)
          return true
        } catch (e) {
          const status = e?.response?.status

          // ✅ Expected: refresh cookie missing/expired
          if (status === 401 || status === 403) {
            this._clearAuthState()
            return false
          }

          // ✅ Server failed (500 etc.): avoid infinite retry loops
          // Clear token so requests stop failing repeatedly, but keep user (optional)
          this._setAuth(null, this.user, this.remember)
          this.lastAuthError = extractError(e)

          console.error('Refresh failed (server error):', e)
          return false
        } finally {
          // ✅ release single-flight lock
          this._refreshPromise = null
        }
      })()

      return await this._refreshPromise
    }
  }
})