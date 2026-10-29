import { describe, expect, it, vi } from 'vitest'
import { effectScope } from 'vue'

function mockSystem(dark: boolean) {
  window.matchMedia = vi.fn().mockReturnValue({
    matches: dark,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }) as unknown as typeof window.matchMedia
}

async function freshTheme() {
  vi.resetModules()
  const { useTheme } = await import('./useTheme')
  return effectScope().run(() => useTheme())!
}

describe('useTheme', () => {
  it('follows the system theme and stores nothing until the user toggles', async () => {
    localStorage.clear()
    mockSystem(true)
    const { theme } = await freshTheme()
    expect(theme.value).toBe('dark')
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
    expect(localStorage.getItem('retv4_theme')).toBeNull()
  })

  it('stores an override only while it differs from the system theme', async () => {
    localStorage.clear()
    mockSystem(false)
    const { theme, toggleTheme } = await freshTheme()
    toggleTheme()
    expect(theme.value).toBe('dark')
    expect(localStorage.getItem('retv4_theme')).toBe('dark')
    toggleTheme()
    expect(theme.value).toBe('light')
    expect(localStorage.getItem('retv4_theme')).toBeNull()
  })
})
