/**
 * One mermaid configuration for the whole app. mermaid.initialize() is global, so two
 * components configuring it separately overwrite each other; both call this instead.
 * securityLevel 'strict' stops diagram text from injecting HTML or click handlers.
 */
import mermaid from 'mermaid'

let appliedTheme: string | null = null

/** Applies the shared config for the current theme; cheap to call before every render. */
export function configureMermaid(dark: boolean): typeof mermaid {
  const theme = dark ? 'dark' : 'default'
  if (appliedTheme !== theme) {
    mermaid.initialize({
      startOnLoad: false,
      securityLevel: 'strict',
      theme,
      flowchart: { curve: 'basis', nodeSpacing: 32, rankSpacing: 48 },
    })
    appliedTheme = theme
  }
  return mermaid
}
