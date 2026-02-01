import { defineStore } from 'pinia'
import api from '@/utils/api'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: null,
    token: null,
    isLoading: false
  }),
  getters: {
    isAuthenticated: state => !!state.token,
    isAdmin: state => state.user?.role === 'admin'
  },
  actions: {
    async login(username, password, remember = false) {
      this.isLoading = true
      try {
        const resp = await api.post('/auth/login', { username, password })
        // Response: { access_token, refresh_token, token_type, user }
        this.token = resp.data.access_token
        this.user = resp.data.user
        // Refresh token is stored in HttpOnly cookie (set by server)
        return resp.data
      } catch (err) {
        this.token = null
        this.user = null
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
      } catch (e) {
        console.error('Failed to fetch user:', e)
        // If 401, token is invalid
        if (e.response?.status === 401) {
          this.logout()
        }
      }
    },
    async logout() {
      try {
        // Only call backend logout if we have a token (session exists)
        if (this.token) {
          // Call clear memory endpoint first if session_id is available
          if (this.user?.session_id) {
            try {
              await api.post(`/ai/clear-memory/${this.user.session_id}`)
            } catch (e) {
              console.error('Failed to clear AI memory:', e)
            }
          }
          
          await api.post('/auth/logout')
        }
      } catch (e) {
        // Silent fail - logout should always succeed locally even if backend fails
        console.error('Logout error (non-fatal):', e)
      } finally {
        // Always clear local state
        this.token = null
        this.user = null
      }
    },
    // Called when 401 to refresh token
    async refreshToken() {
      try {
        // Backend reads refresh_token from HttpOnly cookie automatically
        // withCredentials: true ensures cookies are sent
        const resp = await api.post('/auth/refresh', {})
        this.token = resp.data.access_token
        return true
      } catch (e) {
        // Don't log errors for expected "no cookie" case (401 on fresh session)
        if (e.response?.status !== 401) {
          console.error('Refresh failed:', e)
        }
        // Don't call logout - just clear local state silently
        this.token = null
        this.user = null
        return false
      }
    }
  }
})

