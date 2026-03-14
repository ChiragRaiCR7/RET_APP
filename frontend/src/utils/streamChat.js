/**
 * api.js — Axios clients for RET v4 API calls (Refactored)
 *
 * Goals (preserved):
 *  - Default client (api): 30s timeout for normal requests
 *  - Long-running client (longApi): higher timeout for conversions/scans/comparisons
 *  - Automatic JWT Bearer injection from authStore
 *  - 401 response interceptor:
 *      - silently refresh via HttpOnly refresh cookie
 *      - retry original request once
 *      - never refresh for auth endpoints or network/timeouts
 *
 * Extra Improvements (preserved):
 *  - Smart client selection: auto-use longApi for heavy endpoints
 *  - Per-request timeout override supported
 *  - Optional job polling helpers
 *
 * Non-breaking improvements added:
 *  - Safe Pinia store access (prevents “no active pinia” runtime crash)
 *  - Uses authStore's single-flight refresh (and keeps global lock as extra safety)
 *  - More robust network/timeout detection
 *  - More robust job status normalization
 */

import axios from 'axios'
import { useAuthStore } from '@/stores/authStore'

// ----------------------------------------------------------------------------
// Config
// ----------------------------------------------------------------------------
const BASE_URL = import.meta.env.VITE_API_BASE || '/api/v1'

const DEFAULT_TIMEOUT_MS = Number(import.meta.env.VITE_DEFAULT_TIMEOUT_MS || 30_000)
const LONG_TIMEOUT_MS = Number(import.meta.env.VITE_LONG_TIMEOUT_MS || 1_800_000) // 30 min

// Optional job polling defaults
const JOB_POLL_INTERVAL_MS = Number(import.meta.env.VITE_JOB_POLL_INTERVAL_MS || 1500)
const JOB_POLL_TIMEOUT_MS = Number(import.meta.env.VITE_JOB_POLL_TIMEOUT_MS || 30 * 60 * 1000) // 30 min

function createClient({ timeout }) {
  return axios.create({
    baseURL: BASE_URL,
    timeout,
    // crucial for refresh-cookie flow
    withCredentials: true
  })
}

const api = createClient({ timeout: DEFAULT_TIMEOUT_MS })
const longApi = createClient({ timeout: LONG_TIMEOUT_MS })

// ----------------------------------------------------------------------------
// Refresh coordination (extra safety)
// ----------------------------------------------------------------------------
let refreshPromise = null

// ----------------------------------------------------------------------------
// Helpers
// ----------------------------------------------------------------------------

/**
 * Safe access to Pinia store.
 * Prevents "no active pinia" crash if api.js is imported before Pinia is installed.
 */
function safeAuthStore() {
  try {
    return useAuthStore()
  } catch {
    return null
  }
}

/**
 * Determine whether a given request URL is an auth route.
 * We must skip refresh logic for these endpoints.
 */
function isAuthRoute(url = '') {
  const u = String(url)
  return (
    u.includes('/auth/login') ||
    u.includes('/auth/logout') ||
    u.includes('/auth/refresh') ||
    u.includes('/auth/me')
  )
}

function isTimeoutError(err) {
  // Axios timeout usually uses code ECONNABORTED + message contains "timeout"
  return err?.code === 'ECONNABORTED' || /timeout/i.test(err?.message || '')
}

function isNetworkError(err) {
  // Axios sets err.response undefined for true network failures
  return !err?.response && !isTimeoutError(err)
}

/**
 * Mark endpoints that are typically long-running and should use longApi.
 * You can tune this list anytime without changing UI call sites.
 */
function shouldUseLongClient(url = '') {
  const u = String(url)

  // conversions, scans, large downloads
  if (u.includes('/conversion/') || u.includes('/scan/') || u.includes('/download')) return true

  // comparisons: run can be heavy (ZIP scan + XML->CSV conversion)
  if (
    u.includes('/comparison/run') ||
    u.includes('/comparison/run-async') ||
    u.includes('/comparison/compare-zip')
  ) return true

  // polling should stay fast
  if (u.includes('/jobs/') || u.includes('/job/')) return false

  return false
}

/**
 * Attach auth interceptors to an axios client.
 */
function attachAuthInterceptors(client) {
  // -----------------------------
  // Request interceptor: inject Bearer token
  // -----------------------------
  client.interceptors.request.use(
    (config) => {
      const auth = safeAuthStore()

      // Ensure headers exists
      config.headers = config.headers || {}

      // Attach token if present
      if (auth?.token) {
        config.headers.Authorization = `Bearer ${auth.token}`
      } else {
        delete config.headers.Authorization
      }

      return config
    },
    (err) => Promise.reject(err)
  )

  // -----------------------------
  // Response interceptor: refresh on 401 and retry once
  // -----------------------------
  client.interceptors.response.use(
    (res) => res,
    async (err) => {
      const auth = safeAuthStore()
      const config = err?.config
      const response = err?.response

      if (!config) return Promise.reject(err)

      const url = config?.url || ''
      const status = response?.status

      // Allow callers to skip refresh logic explicitly
      if (config._skipAuthRefresh) {
        return Promise.reject(err)
      }

      // Do not refresh on:
      // - auth endpoints
      // - network errors / timeouts
      // - if already retried once
      if (isAuthRoute(url) || isNetworkError(err) || isTimeoutError(err) || config._retry) {
        return Promise.reject(err)
      }

      // Only handle 401 here
      if (status !== 401) {
        return Promise.reject(err)
      }

      // If auth store isn't available yet, don't attempt refresh
      if (!auth) {
        return Promise.reject(err)
      }

      // Mark as retried so we don't loop
      config._retry = true

      try {
        // Single-flight refresh (global lock).
        // auth.refreshToken() already implements its own single-flight lock too;
        // this global lock is extra protection across axios clients.
        if (!refreshPromise) {
          refreshPromise = (async () => {
            const ok = await auth.refreshToken()
            return ok
          })().finally(() => {
            refreshPromise = null
          })
        }

        const ok = await refreshPromise
        if (!ok || !auth.token) {
          return Promise.reject(err)
        }

        // Retry original request with updated token
        config.headers = config.headers || {}
        config.headers.Authorization = `Bearer ${auth.token}`

        return client.request(config)
      } catch (refreshErr) {
        return Promise.reject(refreshErr)
      }
    }
  )
}

attachAuthInterceptors(api)
attachAuthInterceptors(longApi)

// ----------------------------------------------------------------------------
// Public client getters
// ----------------------------------------------------------------------------
export function getApiClient({ long = false } = {}) {
  return long ? longApi : api
}

export { longApi }
export default api

// ----------------------------------------------------------------------------
// Request deduplication — prevent identical concurrent requests
// ----------------------------------------------------------------------------
const _inflightRequests = new Map()

function _dedupKey(method, url, params) {
  return `${method}:${url}:${JSON.stringify(params || '')}`
}

// ----------------------------------------------------------------------------
// High-level call helper (recommended)
// ----------------------------------------------------------------------------
/**
 * apiCall() automatically chooses api vs longApi based on URL,
 * unless you override with { long: true/false }.
 *
 * Options:
 *   dedupe: true  — if an identical request is in-flight, return its promise
 *   signal: AbortSignal — for cancellation (e.g., on component unmount)
 *   retries: number — retry transient failures (default 0)
 *
 * Usage:
 *   await apiCall({ method:'post', url:'/comparison/run', data: formData, params })
 */
export async function apiCall({
  method = 'get',
  url,
  params,
  data,
  headers,
  long,
  timeout,
  signal,
  dedupe = false,
  retries = 0,
  // Allow caller to skip refresh behavior for this request
  skipAuthRefresh = false,
  ...rest
}) {
  if (!url) throw new Error('apiCall: url is required')

  // Deduplication: if an identical GET is in-flight, reuse its promise
  const key = dedupe ? _dedupKey(method, url, params) : null
  if (key && _inflightRequests.has(key)) {
    return _inflightRequests.get(key)
  }

  const useLong = typeof long === 'boolean' ? long : shouldUseLongClient(url)
  const client = useLong ? longApi : api

  const config = {
    method,
    url,
    params,
    data,
    headers,
    ...rest
  }

  if (typeof timeout === 'number') {
    config.timeout = timeout
  }

  if (signal) {
    config.signal = signal
  }

  if (skipAuthRefresh) {
    config._skipAuthRefresh = true
  }

  const doRequest = async (attempt = 0) => {
    try {
      const res = await client.request(config)
      return res.data
    } catch (err) {
      // Only retry on transient errors (5xx, network), not on 4xx
      const status = err?.response?.status
      const isTransient = !status || status >= 500 || isNetworkError(err)

      if (isTransient && attempt < retries) {
        const delay = Math.min(1000 * Math.pow(2, attempt), 10000)
        await new Promise((r) => setTimeout(r, delay))
        return doRequest(attempt + 1)
      }
      throw err
    }
  }

  const promise = doRequest()

  if (key) {
    _inflightRequests.set(key, promise)
    promise.finally(() => _inflightRequests.delete(key))
  }

  return promise
}

/**
 * Create an AbortController for use in Vue components.
 * Call abort() on unmount to cancel in-flight requests.
 *
 * Usage in setup():
 *   const { signal, abort } = createRequestController()
 *   onUnmounted(abort)
 *   const data = await apiCall({ url: '/...', signal })
 */
export function createRequestController() {
  const controller = new AbortController()
  return {
    signal: controller.signal,
    abort: () => controller.abort(),
  }
}

// ----------------------------------------------------------------------------
// Optional: Job polling helper (perfect for "always async comparison")
// ----------------------------------------------------------------------------
/**
 * Polls job endpoint until SUCCESS/FAILED or timeout.
 * Assumes you have jobs API: GET /jobs/{jobId}
 */
export async function pollJob(
  jobId,
  { intervalMs = JOB_POLL_INTERVAL_MS, timeoutMs = JOB_POLL_TIMEOUT_MS } = {}
) {
  if (!jobId) throw new Error('pollJob: jobId is required')

  const start = Date.now()

  while (true) {
    const job = await apiCall({
      method: 'get',
      url: `/jobs/${jobId}`,
      long: false // polling should stay fast
    })

    const rawStatus = job?.status || job?.state
    const status = String(rawStatus || '').toUpperCase()

    if (status === 'SUCCEEDED' || status === 'SUCCESS') {
      return job?.result ?? job
    }

    if (status === 'FAILED' || status === 'FAILURE') {
      const msg = job?.error || job?.message || 'Job failed'
      throw new Error(msg)
    }

    if (Date.now() - start > timeoutMs) {
      throw new Error(`Job polling timeout exceeded (${timeoutMs} ms)`)
    }

    await new Promise((r) => setTimeout(r, intervalMs))
  }
}

/**
 * Convenience helper:
 * 1) calls a start-job endpoint that returns {job_id}
 * 2) polls until completion
 */
export async function startJobAndPoll({
  startUrl,
  method = 'post',
  data,
  params,
  headers,
  // start endpoints should be fast; keep long false by default
  long = false,
  poll = { intervalMs: JOB_POLL_INTERVAL_MS, timeoutMs: JOB_POLL_TIMEOUT_MS }
} = {}) {
  if (!startUrl) throw new Error('startJobAndPoll: startUrl is required')

  const started = await apiCall({ method, url: startUrl, data, params, headers, long })
  const jobId = started?.job_id || started?.jobId || started?.id

  if (!jobId) {
    throw new Error('startJobAndPoll: start endpoint did not return job_id')
  }

  return pollJob(jobId, poll)
}