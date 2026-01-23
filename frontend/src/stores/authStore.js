import { defineStore } from 'pinia'
import api from '@/utils/api'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: null,
    token: localStorage.getItem('retv4_token') || null,
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
        // expected { token, user }
        this.token = resp.data.token
        this.user = resp.data.user
        if (remember) localStorage.setItem('retv4_token', this.token)
        else localStorage.removeItem('retv4_token')
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
        // swallow
      }
    },
    logout() {
      this.token = null
      this.user = null
      localStorage.removeItem('retv4_token')
    }
  }
})
