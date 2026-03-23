import axios from 'axios'
import { useAuthStore } from '@/stores/authStore'

const instance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || '/api/v1',
  timeout: 30_000,
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true, // Important: send cookies with requests
})

// inject access token from store into Authorization header
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

    // Only attempt refresh for 401 on non-auth endpoints
    // Don't retry auth endpoints themselves (login, refresh, logout)
    const isAuthEndpoint = config?.url?.includes('/auth/')
    
    if (response?.status === 401 && config && !config._retry && !isAuthEndpoint) {
      config._retry = true

      if (!isRefreshing) {
        isRefreshing = true
        try {
          // Call refresh endpoint - refresh token is in HttpOnly cookie, sent automatically
          const result = await auth.refreshToken()
          if (result) {
            processQueue(null, auth.token)
            // Retry original request with new token
            return instance(config)
          } else {
            processQueue(new Error('Refresh failed'), null)
            // Don't navigate here - let the router handle it
            return Promise.reject(err)
          }
        } catch (refreshErr) {
          processQueue(refreshErr, null)
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

// ---------------------------------------------------------------------------
// Re-export helpers defined in streamChat.js so components can import from
// either '@/utils/api' or '@/utils/streamChat' interchangeably.
// ---------------------------------------------------------------------------
export { longApi, apiCall, pollJob } from '@/utils/streamChat'

// ---------------------------------------------------------------------------
// Streaming helpers (Fetch-based — Axios cannot stream SSE)
// ---------------------------------------------------------------------------

/**
 * Parse SSE frames from a ReadableStream reader.
 * Yields `{ event, data }` objects.
 */
async function* _parseSSE(reader) {
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { value, done } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const frames = buffer.split('\n\n')
    buffer = frames.pop() // keep incomplete tail

    for (const frame of frames) {
      if (!frame.trim()) continue

      let event = 'message'
      let dataStr = ''

      for (const line of frame.split('\n')) {
        if (line.startsWith('event: ')) event = line.slice(7).trim()
        else if (line.startsWith('data: ')) dataStr += line.slice(6)
      }

      if (!dataStr) continue

      let data
      try { data = JSON.parse(dataStr) } catch { data = dataStr }

      yield { event, data }
    }
  }
}

function _authHeaders() {
  const auth = useAuthStore()
  const headers = { 'Content-Type': 'application/json' }
  if (auth.token) headers.Authorization = `Bearer ${auth.token}`
  return headers
}

const _baseUrl = () => import.meta.env.VITE_API_BASE || '/api/v1'

/**
 * POST-based SSE stream for request/response patterns (e.g. chat).
 *
 * On 401, attempts a single token refresh and retries.
 *
 * @param {string}  path      - API path relative to base (e.g. '/v2/ai/chat/stream')
 * @param {Object}  body      - JSON request body
 * @param {Object}  handlers  - Map of event name → callback(data)
 * @param {Object}  [opts]    - { signal, headers }
 */
export async function fetchSSE(path, body, handlers = {}, opts = {}) {
  const { signal, headers: extraHeaders } = opts

  async function _attempt(retry = true) {
    const resp = await fetch(`${_baseUrl()}${path}`, {
      method: 'POST',
      credentials: 'include',
      signal,
      headers: { ..._authHeaders(), ...extraHeaders },
      body: JSON.stringify(body),
    })

    if (resp.status === 401 && retry) {
      const auth = useAuthStore()
      const refreshed = await auth.refreshToken()
      if (refreshed) return _attempt(false)
    }

    if (!resp.ok) {
      let detail = `HTTP ${resp.status}`
      try { const b = await resp.json(); detail = b.detail || detail } catch {}
      throw new Error(detail)
    }

    return resp
  }

  const resp = await _attempt()
  const reader = resp.body.getReader()

  for await (const { event, data } of _parseSSE(reader)) {
    const handler = handlers[event]
    if (handler) handler(data)
  }
}

/**
 * GET-based SSE stream for passive status updates (e.g. embed progress).
 *
 * Automatically reconnects up to `maxRetries` times on network errors.
 * Returns a cleanup function to close the connection.
 *
 * @param {string}  path       - API path relative to base
 * @param {Object}  handlers   - Map of event name → callback(data)
 * @param {Object}  [opts]     - { maxRetries, retryDelayMs, signal }
 * @returns {() => void}       - call to disconnect
 */
export function connectSSE(path, handlers = {}, opts = {}) {
  const { maxRetries = 5, retryDelayMs = 2000, signal } = opts
  let retries = 0
  let controller = new AbortController()
  let stopped = false

  if (signal) {
    signal.addEventListener('abort', () => { stopped = true; controller.abort() })
  }

  async function _connect() {
    if (stopped) return

    try {
      const resp = await fetch(`${_baseUrl()}${path}`, {
        method: 'GET',
        credentials: 'include',
        signal: controller.signal,
        headers: _authHeaders(),
      })

      if (resp.status === 401) {
        const auth = useAuthStore()
        const refreshed = await auth.refreshToken()
        if (refreshed && !stopped) {
          // retry immediately with new token
          return _connect()
        }
        throw new Error('Authentication failed')
      }

      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)

      const reader = resp.body.getReader()
      retries = 0 // reset on successful connection

      for await (const { event, data } of _parseSSE(reader)) {
        if (stopped) break
        const handler = handlers[event]
        if (handler) handler(data)
      }
    } catch (err) {
      if (stopped || err.name === 'AbortError') return
      if (retries < maxRetries) {
        retries++
        await new Promise(r => setTimeout(r, retryDelayMs * retries))
        if (!stopped) return _connect()
      }
      const errorHandler = handlers.error
      if (errorHandler) errorHandler(err)
    }
  }

  _connect()

  return () => {
    stopped = true
    controller.abort()
  }
}
