import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const post = vi.fn()
vi.mock('@/utils/api', () => ({ default: { post: (...args: unknown[]) => post(...args), get: vi.fn() } }))

const { useAuthStore } = await import('./authStore')

describe('authStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    post.mockReset()
    localStorage.clear()
    sessionStorage.clear()
  })

  it('keeps the access token in memory only', async () => {
    post.mockResolvedValue({ data: { access_token: 'tok', token_type: 'bearer', user: { id: 1, username: 'demo', role: 'user' } } })
    const auth = useAuthStore()
    await auth.login('demo', 'pw', true)
    expect(auth.token).toBe('tok')
    expect(JSON.stringify({ ...localStorage })).not.toContain('tok')
    expect(JSON.stringify({ ...sessionStorage })).not.toContain('tok')
  })

  it('runs one refresh for concurrent callers', async () => {
    let resolve!: (v: unknown) => void
    post.mockReturnValue(new Promise((r) => (resolve = r)))
    const auth = useAuthStore()
    const results = Promise.all([auth.refreshToken(), auth.refreshToken(), auth.refreshToken()])
    resolve({ data: { access_token: 'new' } })
    expect(await results).toEqual([true, true, true])
    expect(post).toHaveBeenCalledTimes(1)
    expect(auth.token).toBe('new')
  })

  it('clears the session when the refresh cookie is rejected', async () => {
    post.mockRejectedValue({ response: { status: 401 } })
    const auth = useAuthStore()
    auth.token = 'old'
    expect(await auth.refreshToken()).toBe(false)
    expect(auth.token).toBeNull()
  })

  it('treats admin roles in either shape as admin', () => {
    const auth = useAuthStore()
    auth.user = { id: 1, username: 'a', role: { value: 'SUPER_ADMIN' } }
    expect(auth.isAdmin).toBe(true)
    auth.user = { id: 1, username: 'a', role: 'user' }
    expect(auth.isAdmin).toBe(false)
  })
})
