/**
 * useTheme — dark/light theme for RET v4.
 *
 * The page follows the OS setting until the user toggles. A toggle stores the chosen
 * scheme only when it differs from the OS setting; toggling back to match the OS
 * removes the stored value, so the page follows the OS again. A stored choice is kept
 * even if the OS later changes to match it.
 *
 * Mechanism: `data-theme="dark"` on <html>; tokens.css keys its dark values off it.
 * All instances share one state, one OS listener and one cross-tab listener.
 */
import { onScopeDispose, ref, type Ref } from 'vue'

export type Theme = 'light' | 'dark'

const STORAGE_KEY = 'retv4_theme'
const darkQuery = window.matchMedia?.('(prefers-color-scheme: dark)')

function systemTheme(): Theme {
  return darkQuery?.matches ? 'dark' : 'light'
}

function readStored(): Theme | null {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY)
    return value === 'dark' || value === 'light' ? value : null
  } catch {
    return null
  }
}

function writeStored(value: Theme | null): void {
  try {
    if (value) window.localStorage.setItem(STORAGE_KEY, value)
    else window.localStorage.removeItem(STORAGE_KEY)
  } catch {
    // Storage blocked: the choice still applies for this page view.
  }
}

const theme: Ref<Theme> = ref(readStored() ?? systemTheme())
let users = 0

function apply(): void {
  if (theme.value === 'dark') document.documentElement.setAttribute('data-theme', 'dark')
  else document.documentElement.removeAttribute('data-theme')
}

function onSystemChange(): void {
  if (!readStored()) {
    theme.value = systemTheme()
    apply()
  }
}

function onStorage(event: StorageEvent): void {
  if (event.key === STORAGE_KEY) {
    theme.value = readStored() ?? systemTheme()
    apply()
  }
}

function toggleTheme(): void {
  const target: Theme = theme.value === 'dark' ? 'light' : 'dark'
  writeStored(target === systemTheme() ? null : target)
  theme.value = target
  apply()
}

export function useTheme(): { theme: Readonly<Ref<Theme>>; toggleTheme: () => void } {
  if (users++ === 0) {
    apply()
    darkQuery?.addEventListener('change', onSystemChange)
    window.addEventListener('storage', onStorage)
  }
  onScopeDispose(() => {
    if (--users === 0) {
      darkQuery?.removeEventListener('change', onSystemChange)
      window.removeEventListener('storage', onStorage)
    }
  })
  return { theme, toggleTheme }
}
