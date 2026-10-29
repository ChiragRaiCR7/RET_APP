/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE?: string
  readonly VITE_BACKEND_URL?: string
  readonly VITE_DEFAULT_TIMEOUT_MS?: string
  readonly VITE_LONG_TIMEOUT_MS?: string
  readonly VITE_JOB_POLL_INTERVAL_MS?: string
  readonly VITE_JOB_POLL_TIMEOUT_MS?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<object, object, unknown>
  export default component
}
