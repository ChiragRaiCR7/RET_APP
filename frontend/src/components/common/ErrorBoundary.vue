<template>
  <div v-if="hasError" class="error-boundary">
    <div class="error-content">
      <div class="error-icon">⚠️</div>
      <h2 class="error-title">Something went wrong</h2>
      <p class="error-message">{{ errorMessage }}</p>
      <div class="error-actions">
        <button class="btn btn-primary" @click="resetError">
          Try Again
        </button>
        <button class="btn btn-secondary" @click="goHome">
          Go Home
        </button>
      </div>
      <details v-if="showDetails && errorDetails" class="error-details">
        <summary>Technical Details</summary>
        <pre>{{ errorDetails }}</pre>
      </details>
    </div>
  </div>
  <slot v-else />
</template>

<script setup>
import { ref, onErrorCaptured } from 'vue'
import { useRouter } from 'vue-router'

const props = defineProps({
  showDetails: {
    type: Boolean,
    default: false
  },
  fallbackMessage: {
    type: String,
    default: 'An unexpected error occurred. Please try again.'
  }
})

const emit = defineEmits(['error'])

const router = useRouter()
const hasError = ref(false)
const errorMessage = ref('')
const errorDetails = ref('')

onErrorCaptured((err, instance, info) => {
  hasError.value = true
  errorMessage.value = err.message || props.fallbackMessage
  errorDetails.value = `Error: ${err.message}\nComponent: ${instance?.$options?.name || 'Unknown'}\nInfo: ${info}\nStack: ${err.stack || 'No stack trace'}`
  
  // Emit error for parent handling
  emit('error', { error: err, instance, info })
  
  // Prevent error from propagating
  return false
})

function resetError() {
  hasError.value = false
  errorMessage.value = ''
  errorDetails.value = ''
}

function goHome() {
  resetError()
  router.push('/')
}
</script>

<style scoped>
.error-boundary {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 300px;
  padding: var(--space-xl);
}

.error-content {
  text-align: center;
  max-width: 500px;
}

.error-icon {
  font-size: 3rem;
  margin-bottom: var(--space-md);
}

.error-title {
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--text-heading);
  margin-bottom: var(--space-sm);
}

.error-message {
  color: var(--text-secondary);
  margin-bottom: var(--space-lg);
}

.error-actions {
  display: flex;
  gap: var(--space-md);
  justify-content: center;
  margin-bottom: var(--space-lg);
}

.error-details {
  text-align: left;
  margin-top: var(--space-lg);
}

.error-details summary {
  cursor: pointer;
  color: var(--text-tertiary);
  font-size: 0.85rem;
}

.error-details pre {
  margin-top: var(--space-sm);
  padding: var(--space-md);
  background: var(--surface-base);
  border-radius: var(--radius-sm);
  font-size: 0.75rem;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
