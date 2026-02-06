<template>
  <TransitionGroup name="toast" tag="div" class="toast-container">
    <div
      v-for="toast in toasts"
      :key="toast.id"
      class="toast"
      :class="[`toast--${toast.type}`]"
      @click="dismiss(toast.id)"
    >
      <div class="toast-icon">
        <template v-if="toast.type === 'success'">✓</template>
        <template v-else-if="toast.type === 'error'">✕</template>
        <template v-else-if="toast.type === 'warning'">⚠</template>
        <template v-else>ℹ</template>
      </div>
      <div class="toast-content">
        <p class="toast-message">{{ toast.message }}</p>
      </div>
      <button class="toast-close" @click.stop="dismiss(toast.id)" aria-label="Dismiss">
        ×
      </button>
    </div>
  </TransitionGroup>
</template>

<script setup>
import { computed } from 'vue'
import { useToastStore } from '@/stores/toastStore'

const toastStore = useToastStore()
const toasts = computed(() => toastStore.toasts)

function dismiss(id) {
  toastStore.remove(id)
}
</script>

<style scoped>
.toast-container {
  position: fixed;
  bottom: 20px;
  right: 20px;
  z-index: 9999;
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-width: 420px;
  pointer-events: none;
}

.toast {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 14px 16px;
  border-radius: var(--radius-lg, 12px);
  background: var(--surface, #1a1a2e);
  border: 1px solid var(--border, #3a3a5a);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
  pointer-events: auto;
  cursor: pointer;
  min-width: 320px;
  backdrop-filter: blur(12px);
  transition: all 0.3s ease;
}

.toast:hover {
  transform: translateX(-4px);
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.4);
}

.toast--success {
  background: linear-gradient(135deg, rgba(16, 185, 129, 0.15) 0%, rgba(16, 185, 129, 0.05) 100%);
  border-color: rgba(16, 185, 129, 0.4);
}

.toast--success .toast-icon {
  background: #10b981;
  color: white;
}

.toast--success .toast-message {
  color: #065f46;
}

.toast--error {
  background: linear-gradient(135deg, rgba(239, 68, 68, 0.15) 0%, rgba(239, 68, 68, 0.05) 100%);
  border-color: rgba(239, 68, 68, 0.4);
}

.toast--error .toast-icon {
  background: #ef4444;
  color: white;
}

.toast--error .toast-message {
  color: #991b1b;
}

.toast--warning {
  background: linear-gradient(135deg, rgba(245, 158, 11, 0.15) 0%, rgba(245, 158, 11, 0.05) 100%);
  border-color: rgba(245, 158, 11, 0.4);
}

.toast--warning .toast-icon {
  background: #f59e0b;
  color: white;
}

.toast--warning .toast-message {
  color: #92400e;
}

.toast--info {
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.15) 0%, rgba(59, 130, 246, 0.05) 100%);
  border-color: rgba(59, 130, 246, 0.4);
}

.toast--info .toast-icon {
  background: #3b82f6;
  color: white;
}

.toast--info .toast-message {
  color: #1e40af;
}

.toast-icon {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: bold;
}

.toast-content {
  flex: 1;
  min-width: 0;
}

.toast-message {
  margin: 0;
  color: var(--text-body, #1f2937);
  font-size: 14px;
  line-height: 1.5;
  word-wrap: break-word;
  font-weight: 500;
}

/* Dark mode adjustments */
@media (prefers-color-scheme: dark) {
  .toast--success .toast-message {
    color: #86efac;
  }
  
  .toast--error .toast-message {
    color: #fca5a5;
  }
  
  .toast--warning .toast-message {
    color: #fcd34d;
  }
  
  .toast--info .toast-message {
    color: #93c5fd;
  }
  
  .toast-message {
    color: var(--text-body, #e5e5e5);
  }
}

.toast-close {
  flex-shrink: 0;
  background: none;
  border: none;
  color: var(--muted, #888);
  cursor: pointer;
  font-size: 20px;
  line-height: 1;
  padding: 0;
  margin: -4px -4px -4px 4px;
  opacity: 0.6;
  transition: opacity 0.2s;
}

.toast-close:hover {
  opacity: 1;
}

/* Transition animations */
.toast-enter-active {
  animation: toast-in 0.35s ease-out;
}

.toast-leave-active {
  animation: toast-out 0.3s ease-in;
}

@keyframes toast-in {
  0% {
    opacity: 0;
    transform: translateX(100%);
  }
  100% {
    opacity: 1;
    transform: translateX(0);
  }
}

@keyframes toast-out {
  0% {
    opacity: 1;
    transform: translateX(0);
  }
  100% {
    opacity: 0;
    transform: translateX(100%);
  }
}

/* Mobile responsiveness */
@media (max-width: 480px) {
  .toast-container {
    bottom: 10px;
    right: 10px;
    left: 10px;
    max-width: none;
  }
  
  .toast {
    min-width: 0;
  }
}
</style>
