/**
 * api.ts — the single HTTP layer for RET v4.
 *
 *  - `api` (default export): 30 s timeout for normal requests
 *  - `longApi`: long timeout for conversions, scans, comparisons and downloads
 *  - Bearer token injected from the auth store on every request
 *  - On 401: one single-flight refresh through the HttpOnly refresh cookie, then the
 *    original request is retried once. Auth routes, network errors and timeouts are
 *    never refreshed.
 *  - `apiCall` picks the client by URL, with optional dedupe, retries and cancellation
 *  - `pollJob` / `startJobAndPoll` for async jobs
 *
 * This replaces two parallel axios stacks (utils/api.js and utils/streamChat.js) that
 * each had their own, slightly different refresh logic.
 */

import axios, {
  type AxiosError,
  type AxiosInstance,
  type AxiosRequestConfig,
  type InternalAxiosRequestConfig,
  type Method,
} from 'axios'
import { useAuthStore } from '@/stores/authStore'

declare module 'axios' {
  interface AxiosRequestConfig {
    /** Set by the 401 handler so a request is retried at most once. */
    _retry?: boolean
    /** Callers set this to opt out of the refresh-and-retry behavior. */
    _skipAuthRefresh?: boolean
  }
}

const BASE_URL: string = import.meta.env.VITE_API_BASE || '/api/v1'
const DEFAULT_TIMEOUT_MS = Number(import.meta.env.VITE_DEFAULT_TIMEOUT_MS || 30_000)
const LONG_TIMEOUT_MS = Number(import.meta.env.VITE_LONG_TIMEOUT_MS || 1_800_000) // 30 min
const JOB_POLL_INTERVAL_MS = Number(import.meta.env.VITE_JOB_POLL_INTERVAL_MS || 1500)
const JOB_POLL_TIMEOUT_MS = Number(import.meta.env.VITE_JOB_POLL_TIMEOUT_MS || 30 * 60 * 1000)
const MAX_RETRY_DELAY_MS = 10_000

function createClient(timeout: number): AxiosInstance {
  // withCredentials is required for the refresh-cookie flow.
  return axios.create({ baseURL: BASE_URL, timeout, withCredentials: true })
}

const api = createClient(DEFAULT_TIMEOUT_MS)
const longApi = createClient(LONG_TIMEOUT_MS)

let refreshPromise: Promise<boolean> | null = null

/** Pinia may not be installed yet when this module is first evaluated. */
function safeAuthStore(): ReturnType<typeof useAuthStore> | null {
  try {
    return useAuthStore()
  } catch {
    return null
  }
}

const AUTH_ROUTES = ['/auth/login', '/auth/logout', '/auth/refresh', '/auth/me']

export function isAuthRoute(url = ''): boolean {
  return AUTH_ROUTES.some((route) => url.includes(route))
}

function isTimeoutError(err: AxiosError): boolean {
  return err.code === 'ECONNABORTED' || /timeout/i.test(err.message || '')
}

function isNetworkError(err: AxiosError): boolean {
  return !err.response && !isTimeoutError(err)
}

/** Long-running endpoints use the long-timeout client; job polling stays fast. */
export function shouldUseLongClient(url = ''): boolean {
  if (url.includes('/jobs/') || url.includes('/job/')) return false
  if (url.includes('/conversion/') || url.includes('/scan/') || url.includes('/download')) return true
  return (
    url.includes('/comparison/run') ||
    url.includes('/comparison/run-async') ||
    url.includes('/comparison/compare-zip')
  )
}

function attachAuthInterceptors(client: AxiosInstance): void {
  client.interceptors.request.use((config: InternalAxiosRequestConfig) => {
    const token = safeAuthStore()?.token
    if (token) config.headers.set('Authorization', `Bearer ${token}`)
    else config.headers.delete('Authorization')
    return config
  })

  client.interceptors.response.use(
    (res) => res,
    async (err: AxiosError) => {
      const config = err.config
      const auth = safeAuthStore()
      if (
        !config ||
        !auth ||
        config._skipAuthRefresh ||
        config._retry ||
        err.response?.status !== 401 ||
        isAuthRoute(config.url) ||
        isNetworkError(err) ||
        isTimeoutError(err)
      ) {
        throw err
      }
      config._retry = true
      // Shared across both clients so a burst of 401s triggers one refresh.
      refreshPromise ??= auth.refreshToken().finally(() => {
        refreshPromise = null
      })
      const ok = await refreshPromise
      if (!ok || !auth.token) throw err
      config.headers.set('Authorization', `Bearer ${auth.token}`)
      return client.request(config)
    },
  )
}

attachAuthInterceptors(api)
attachAuthInterceptors(longApi)

export function getApiClient({ long = false } = {}): AxiosInstance {
  return long ? longApi : api
}

export { longApi }
export default api

export interface ApiCallOptions extends Omit<AxiosRequestConfig, 'method' | 'url'> {
  method?: Method
  url: string
  /** Force the long (true) or default (false) client; otherwise chosen by URL. */
  long?: boolean
  /** Reuse the promise of an identical in-flight request. */
  dedupe?: boolean
  /** Retry transient failures (5xx and network errors) with exponential backoff. */
  retries?: number
  skipAuthRefresh?: boolean
}

const inflight = new Map<string, Promise<unknown>>()

/**
 * Sends a request through the right client and resolves with the response body.
 *
 *   await apiCall({ method: 'post', url: '/comparison/run', data: formData })
 */
export function apiCall<T = unknown>({
  method = 'get',
  url,
  long,
  dedupe = false,
  retries = 0,
  skipAuthRefresh = false,
  ...config
}: ApiCallOptions): Promise<T> {
  if (!url) throw new Error('apiCall: url is required')
  const key = dedupe ? `${method}:${url}:${JSON.stringify(config.params ?? '')}` : null
  const existing = key ? inflight.get(key) : undefined
  if (existing) return existing as Promise<T>

  const client = (long ?? shouldUseLongClient(url)) ? longApi : api
  const request: AxiosRequestConfig = { ...config, method, url, _skipAuthRefresh: skipAuthRefresh }

  const attempt = async (n: number): Promise<T> => {
    try {
      return (await client.request<T>(request)).data
    } catch (err) {
      const status = (err as AxiosError).response?.status
      const transient = status === undefined || status >= 500
      if (transient && !axios.isCancel(err) && n < retries) {
        await new Promise((r) => setTimeout(r, Math.min(1000 * 2 ** n, MAX_RETRY_DELAY_MS)))
        return attempt(n + 1)
      }
      throw err
    }
  }

  const promise = attempt(0)
  if (key) {
    inflight.set(key, promise)
    void promise.finally(() => inflight.delete(key)).catch(() => undefined)
  }
  return promise
}

/** AbortController wrapper for components: call abort() on unmount. */
export function createRequestController(): { signal: AbortSignal; abort: () => void } {
  const controller = new AbortController()
  return { signal: controller.signal, abort: () => controller.abort() }
}

interface JobStatus {
  status?: string
  state?: string
  result?: unknown
  error?: string
  message?: string
}

/** Polls GET /jobs/{id} until it succeeds (returns its result), fails, or times out. */
export async function pollJob<T = unknown>(
  jobId: string | number,
  { intervalMs = JOB_POLL_INTERVAL_MS, timeoutMs = JOB_POLL_TIMEOUT_MS } = {},
): Promise<T> {
  if (!jobId) throw new Error('pollJob: jobId is required')
  const start = Date.now()
  for (;;) {
    const job = await apiCall<JobStatus>({ url: `/jobs/${jobId}`, long: false })
    const status = String(job?.status || job?.state || '').toUpperCase()
    if (status === 'SUCCEEDED' || status === 'SUCCESS') return (job?.result ?? job) as T
    if (status === 'FAILED' || status === 'FAILURE') {
      throw new Error(job?.error || job?.message || 'Job failed')
    }
    if (Date.now() - start > timeoutMs) {
      throw new Error(`Job polling timeout exceeded (${timeoutMs} ms)`)
    }
    await new Promise((r) => setTimeout(r, intervalMs))
  }
}

/** Calls an endpoint that returns {job_id}, then polls the job to completion. */
export async function startJobAndPoll<T = unknown>({
  startUrl,
  method = 'post',
  data,
  params,
  headers,
  long = false,
  poll = { intervalMs: JOB_POLL_INTERVAL_MS, timeoutMs: JOB_POLL_TIMEOUT_MS },
}: {
  startUrl: string
  method?: Method
  data?: unknown
  params?: unknown
  headers?: AxiosRequestConfig['headers']
  long?: boolean
  poll?: { intervalMs?: number; timeoutMs?: number }
}): Promise<T> {
  if (!startUrl) throw new Error('startJobAndPoll: startUrl is required')
  const started = await apiCall<{ job_id?: string; jobId?: string; id?: string }>({
    method, url: startUrl, data, params, headers, long,
  })
  const jobId = started?.job_id || started?.jobId || started?.id
  if (!jobId) throw new Error('startJobAndPoll: start endpoint did not return job_id')
  return pollJob<T>(jobId, poll)
}
