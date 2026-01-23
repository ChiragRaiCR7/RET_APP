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
