import axios from 'axios'
import { useAuthStore } from '@/stores/authStore'

const instance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || '/api',
  timeout: 30_000,
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true, // Important: send cookies with requests
})

// inject access token from store
instance.interceptors.request.use((config) => {
  const auth = useAuthStore()
  if (auth.token) {
    config.headers.Authorization = `Bearer ${auth.token}`
  }
  return config
}, (err) => Promise.reject(err))

// response interceptor: handle 401 and retry once with refresh
let isRefreshing = false
let failedQueue = []

function processQueue(err, token = null) {
  failedQueue.forEach(prom => {
    if (err) prom.reject(err)
    else prom.resolve(token)
  })
  failedQueue = []
}

instance.interceptors.response.use(
  res => res,
  async err => {
    const { config, response } = err
    const auth = useAuthStore()

    if (response?.status === 401 && config && !config._retry) {
      config._retry = true

      if (!isRefreshing) {
        isRefreshing = true
        try {
          await auth.refreshToken()
          processQueue(null, auth.token)
          // Retry original request with new token
          return instance(config)
        } catch (refreshErr) {
          processQueue(refreshErr, null)
          auth.logout()
          return Promise.reject(refreshErr)
        } finally {
          isRefreshing = false
        }
      } else {
        // Queue request while refresh is in progress
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject })
        }).then(() => instance(config))
      }
    }

    return Promise.reject(err)
  }
)

export default instance
