
<template>
  <div v-if="hasError" class="eb-shell" role="alert" aria-live="assertive">
    <div class="eb-card enterprise-card">
      <!-- Header -->
      <div class="eb-head">
        <div class="eb-icon" aria-hidden="true">
          <!-- Simple warning icon (inline SVG for enterprise feel) -->
          <svg viewBox="0 0 24 24" width="22" height="22" fill="none">
            <path
              d="M12 3.4 2.7 20a1.2 1.2 0 0 0 1 1.8h16.6a1.2 1.2 0 0 0 1-1.8L12 3.4Z"
              stroke="currentColor"
              stroke-width="1.6"
              stroke-linejoin="round"
            />
            <path
              d="M12 9v5"
              stroke="currentColor"
              stroke-width="1.6"
              stroke-linecap="round"
            />
            <path
              d="M12 17.6h.01"
              stroke="currentColor"
              stroke-width="2.6"
              stroke-linecap="round"
            />
          </svg>
        </div>

        <div class="eb-title">
          <h2 ref="titleRef" class="eb-heading" tabindex="-1">
            Something went wrong
          </h2>
          <p class="eb-subtitle">
            We couldn’t load this section. You can retry, refresh, or return home.
          </p>
        </div>

        <div v-if="incidentId" class="eb-incident" aria-label="Incident ID">
          <span class="status-badge badge-info">
            Incident: <code class="eb-code">{{ incidentId }}</code>
          </span>
        </div>
      </div>

      <!-- Message -->
      <div class="eb-body">
        <p class="eb-message">
          {{ userMessage }}
        </p>

        <!-- Optional: compact guidance -->
        <ul class="eb-guidance" v-if="showGuidance">
          <li>Try again to reload this area.</li>
          <li>If it keeps failing, refresh the page.</li>
          <li>For persistent issues, share the incident ID with support.</li>
        </ul>

        <!-- Actions -->
        <div class="eb-actions">
          <button class="btn btn-primary" type="button" @click="retry" :disabled="busy">
            <span v-if="busy" class="spinner" aria-hidden="true"></span>
            {{ busy ? 'Retrying…' : primaryActionLabel }}
          </button>

          <button class="btn btn-secondary" type="button" @click="refreshPage" :disabled="busy">
            Refresh
          </button>

          <button class="btn btn-secondary" type="button" @click="goHome" :disabled="busy">
            Go home
          </button>

          <button
            v-if="showCopy"
            class="btn btn-secondary"
            type="button"
            @click="copyDetails"
            :disabled="!detailsText"
            title="Copy technical details"
          >
            Copy details
          </button>

          <button
            v-if="showReport"
            class="btn btn-secondary"
            type="button"
            @click="report"
            :disabled="busy"
            title="Report this issue"
          >
            Report
          </button>
        </div>

        <!-- Technical details -->
        <details v-if="showDetails && detailsText" class="eb-details">
          <summary class="eb-summary">Technical details</summary>
          <pre class="eb-pre">{{ detailsText }}</pre>
        </details>

        <!-- Optional slot for custom support content -->
        <div v-if="$slots.support" class="eb-support">
          <slot name="support" />
        </div>
      </div>
    </div>
  </div>

  <!-- IMPORTANT: When no error, render children with a key so retry can re-mount -->
  <div v-else :key="renderKey">
    <slot />
  </div>
</template>

<script setup>
import { ref, computed, onErrorCaptured, nextTick } from 'vue'
import { useRouter } from 'vue-router'

/**
 * ErrorBoundary.vue — Enterprise Edition
 * Improvements:
 * - Better UX + accessibility + focus management
 * - True retry via subtree re-mount (renderKey)
 * - Optional incident ID and copy/report affordances
 */

const props = defineProps({
  showDetails: { type: Boolean, default: false },
  showCopy: { type: Boolean, default: true },
  showReport: { type: Boolean, default: false },
  showGuidance: { type: Boolean, default: true },

  fallbackMessage: {
    type: String,
    default: 'An unexpected error occurred. Please try again.'
  },

  /** Where "Go home" should route */
  homeRoute: {
    type: [String, Object],
    default: () => ({ path: '/' })
  },

  /** Label for the primary retry action */
  primaryActionLabel: {
    type: String,
    default: 'Try again'
  },

  /**
   * If true, stops propagation so parent boundaries/global handler won’t also render.
   * Set false if you want global logging to still handle it.
   */
  stopPropagation: { type: Boolean, default: true }
})

const emit = defineEmits([
  'error',        // payload: { error, instance, info, incidentId }
  'reset',        // emitted when user retries
  'report'        // payload: { detailsText, incidentId, error }
])

const router = useRouter()

const hasError = ref(false)
const busy = ref(false)

const errorObj = ref(null)
const errorMessage = ref('')
const detailsText = ref('')

const incidentId = ref('')
const renderKey = ref(0)

const titleRef = ref(null)

const userMessage = computed(() => {
  // Prefer explicit error message only if it looks safe/user-friendly; otherwise fallback.
  const msg = errorMessage.value || ''
  if (!msg) return props.fallbackMessage

  // Simple heuristic: if message is too technical, show fallback.
  const tooTechnical =
    msg.length > 180 ||
    msg.toLowerCase().includes('stack') ||
    msg.toLowerCase().includes('undefined') ||
    msg.toLowerCase().includes('null') ||
    msg.toLowerCase().includes('typeerror')

  return tooTechnical ? props.fallbackMessage : msg
})

function makeIncidentId() {
  // Short, support-friendly id (no PII)
  const t = Date.now().toString(36)
  const r = Math.random().toString(36).slice(2, 8)
  return `${t}-${r}`.toUpperCase()
}

onErrorCaptured((err, instance, info) => {
  hasError.value = true
  errorObj.value = err
  errorMessage.value = err?.message || props.fallbackMessage
  incidentId.value = makeIncidentId()

  const compName =
    instance?.$options?.name ||
    instance?.type?.name ||
    'Unknown'

  detailsText.value =
`Incident: ${incidentId.value}
Error: ${err?.message || 'Unknown error'}
Component: ${compName}
Info: ${info || '—'}
Route: ${router.currentRoute.value?.fullPath || '—'}
Time: ${new Date().toISOString()}

Stack:
${err?.stack || 'No stack trace'}`

  emit('error', { error: err, instance, info, incidentId: incidentId.value })

  // Focus the title for screen readers & keyboard users
  nextTick(() => titleRef.value?.focus?.())

  // Returning false stops further propagation (Vue 3 behavior)
  return props.stopPropagation ? false : true
})

async function retry() {
  if (busy.value) return
  busy.value = true

  // Clear error state and re-mount children
  resetState()
  renderKey.value += 1
  emit('reset')

  await nextTick()
  busy.value = false
}

function resetState() {
  hasError.value = false
  errorObj.value = null
  errorMessage.value = ''
  detailsText.value = ''
  incidentId.value = ''
}

function goHome() {
  resetState()
  router.push(props.homeRoute)
}

function refreshPage() {
  // Best recovery for unknown state
  window.location.reload()
}

async function copyDetails() {
  if (!detailsText.value) return
  try {
    await navigator.clipboard.writeText(detailsText.value)
    // If you have a toast store, hook it here.
  } catch {
    // Ignore (user can manually select from details)
  }
}

function report() {
  emit('report', {
    detailsText: detailsText.value,
    incidentId: incidentId.value,
    error: errorObj.value
  })
}
</script>

<style scoped>
/* =========================================================
   ErrorBoundary — Enterprise styling
   Uses your tokens + existing component classes
   ========================================================= */

.eb-shell {
  display: grid;
  place-items: center;
  min-height: 320px;
  padding: var(--space-xl);
}

.eb-card {
  width: min(720px, 100%);
  padding: var(--space-xl);
}

/* Header layout */
.eb-head {
  display: grid;
  grid-template-columns: auto 1fr auto;
  gap: var(--space-md);
  align-items: start;
  margin-bottom: var(--space-md);
}

@media (max-width: 680px) {
  .eb-head {
    grid-template-columns: auto 1fr;
    grid-template-rows: auto auto;
  }
  .eb-incident {
    grid-column: 1 / -1;
  }
}

.eb-icon {
  width: 42px;
  height: 42px;
  border-radius: var(--radius-lg);
  display: grid;
  place-items: center;
  background: var(--warning-bg);
  border: 1px solid var(--warning-border);
  color: var(--warning);
  box-shadow: var(--shadow-xs);
}

.eb-title {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.eb-heading {
  margin: 0;
  font-size: var(--text-xl);
  font-weight: 950;
  color: var(--text-heading);
}

.eb-subtitle {
  margin: 0;
  color: var(--text-secondary);
  font-size: var(--text-sm);
  line-height: 1.45;
}

.eb-incident {
  display: flex;
  justify-content: flex-end;
}

.eb-code {
  font-family: var(--font-mono);
  font-size: 0.85em;
}

/* Body */
.eb-body {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.eb-message {
  margin: 0;
  color: var(--text-body);
  font-size: var(--text-base);
  line-height: 1.55;
}

.eb-guidance {
  margin: 0;
  padding-left: 18px;
  color: var(--text-tertiary);
  font-size: var(--text-sm);
  display: grid;
  gap: 6px;
}

/* Actions */
.eb-actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-sm);
  align-items: center;
}

.eb-actions .btn-primary {
  min-width: 160px;
}

/* Details */
.eb-details {
  border-top: 1px solid var(--border-light);
  padding-top: var(--space-md);
}

.eb-summary {
  cursor: pointer;
  color: var(--text-secondary);
  font-weight: 850;
  font-size: var(--text-sm);
  user-select: none;
}

.eb-summary:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);
  border-radius: var(--radius-sm);
}

.eb-pre {
  margin-top: var(--space-sm);
  padding: var(--space-md);
  background: var(--surface-base);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  font-family: var(--font-mono);
  font-size: 0.8rem;
  line-height: 1.45;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-word;
}

/* Support slot */
.eb-support {
  padding-top: var(--space-xs);
}

/* Spinner sizing (if your global spinner differs) */
.spinner {
  width: 16px;
  height: 16px;
  margin-right: 8px;
}
</style>
