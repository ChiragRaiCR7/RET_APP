import type { AxiosAdapter, InternalAxiosRequestConfig } from 'axios'
import { describe, expect, it, vi } from 'vitest'

const auth = { token: 'expired' as string | null, refreshToken: vi.fn() }
vi.mock('@/stores/authStore', () => ({ useAuthStore: () => auth }))

const { default: api, longApi, apiCall, shouldUseLongClient } = await import('./api')

type Reply = { status: number; data?: unknown }

/** Routes each request to a reply and records the Authorization header it carried. */
function fakeServer(reply: (config: InternalAxiosRequestConfig) => Reply) {
  const seen: { url?: string; auth?: string }[] = []
  const adapter: AxiosAdapter = async (config) => {
    seen.push({ url: config.url, auth: String(config.headers.get('Authorization') ?? '') })
    const { status, data } = reply(config)
    const response = { data, status, statusText: '', headers: {}, config }
    if (status >= 400) {
      throw Object.assign(new Error(`HTTP ${status}`), { config, response, isAxiosError: true })
    }
    return response
  }
  api.defaults.adapter = adapter
  longApi.defaults.adapter = adapter
  return seen
}

describe('api client', () => {
  it('refreshes once on 401 and retries with the new token', async () => {
    auth.token = 'expired'
    auth.refreshToken.mockImplementation(async () => {
      auth.token = 'fresh'
      return true
    })
    const seen = fakeServer((c) =>
      c.headers.get('Authorization') === 'Bearer fresh' ? { status: 200, data: { ok: 1 } } : { status: 401 },
    )
    await expect(apiCall({ url: '/files/list' })).resolves.toEqual({ ok: 1 })
    expect(seen.map((s) => s.auth)).toEqual(['Bearer expired', 'Bearer fresh'])
    expect(auth.refreshToken).toHaveBeenCalledTimes(1)
  })

  it('never refreshes for auth routes', async () => {
    auth.refreshToken.mockClear()
    fakeServer(() => ({ status: 401 }))
    await expect(api.post('/auth/login', {})).rejects.toThrow('HTTP 401')
    expect(auth.refreshToken).not.toHaveBeenCalled()
  })

  it('gives up when the refresh fails', async () => {
    auth.token = 'expired'
    auth.refreshToken.mockResolvedValue(false)
    fakeServer(() => ({ status: 401 }))
    await expect(apiCall({ url: '/files/list' })).rejects.toThrow('HTTP 401')
  })

  it('sends FormData without forcing a JSON content type', async () => {
    auth.token = 't'
    let contentType = ''
    fakeServer((c) => {
      contentType = String(c.headers.get('Content-Type') ?? '')
      return { status: 200, data: {} }
    })
    const form = new FormData()
    form.append('file', new Blob(['x']), 'a.xml')
    await longApi.post('/conversion/scan', form)
    expect(contentType).not.toContain('application/json')
  })

  it('routes heavy endpoints to the long client and polling to the fast one', () => {
    expect(shouldUseLongClient('/conversion/convert-async')).toBe(true)
    expect(shouldUseLongClient('/comparison/run')).toBe(true)
    expect(shouldUseLongClient('/jobs/42')).toBe(false)
    expect(shouldUseLongClient('/auth/me')).toBe(false)
  })
})
