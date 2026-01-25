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
        // Store refresh token is handled by cookies (HttpOnly)
        // Store token in memory (do not persist)
        return resp.data
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
        await api.post('/auth/logout')
      } catch (e) {
        // ignore errors
      } finally {
        this.token = null
        this.user = null
      }
    },
    // Called when 401 to refresh token
    async refreshToken() {
      try {
        // Backend reads refresh_token from HttpOnly cookie
        const resp = await api.post('/auth/refresh', {})
        this.token = resp.data.access_token
        return true
      } catch (e) {
        console.error('Refresh failed:', e)
        this.logout()
        return false
      }
    }
  }
})

