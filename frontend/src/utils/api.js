import axios from 'axios'
import { useAuthStore } from '@/stores/authStore'

const instance = axios.create({
  baseURL: '/api',
  timeout: 30_000,
  headers: { 'Content-Type': 'application/json' }
})

// inject token
instance.interceptors.request.use((config) => {
  const auth = useAuthStore()
  if (auth.token) {
    config.headers.Authorization = `Bearer ${auth.token}`
  }
  return config
}, (err) => Promise.reject(err))

// global response handler
instance.interceptors.response.use(
  res => res,
  err => {
    // handle unauthorized globally
    if (err.response?.status === 401) {
      const auth = useAuthStore()
      auth.logout()
      // optionally redirect handled by router
    }
    return Promise.reject(err)
  }
)

export default instance
