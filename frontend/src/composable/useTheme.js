
/**
 * useTheme — Composable for dark/light mode toggle in RET v4
 *
 * Priority:
 *   1. Saved preference in localStorage ('retv4_theme')
 *   2. System preference via prefers-color-scheme media query
 *
 * Mechanism: sets `data-theme="dark"` on <html>; removing the
 * attribute reverts to light mode. All CSS variables in tokens.css
 * respond to `[data-theme="dark"]` selectors.
 *
 * Also listens for system theme changes and follows them if
 * the user hasn't explicitly chosen a theme yet.
 *
 * @returns {{ theme: Ref<string>, toggleTheme: () => void }}
 */
import { ref, onMounted } from 'vue'

export function useTheme() {
  const systemPrefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches
  const saved = localStorage.getItem('retv4_theme') // 'dark'|'light'|null
  const theme = ref(saved || (systemPrefersDark ? 'dark' : 'light'))

  function apply() {
    if (theme.value === 'dark') document.documentElement.setAttribute('data-theme', 'dark')
    else document.documentElement.removeAttribute('data-theme')
    localStorage.setItem('retv4_theme', theme.value)
  }

  function toggleTheme() {
    theme.value = theme.value === 'dark' ? 'light' : 'dark'
    apply()
  }

  onMounted(() => {
    apply()
    // respond to system changes
    if (window.matchMedia) {
      window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', e => {
        const savedLocal = localStorage.getItem('retv4_theme')
        if (!savedLocal) {
          theme.value = e.matches ? 'dark' : 'light'
          apply()
        }
      })
    }
  })

  return { theme, toggleTheme }
}