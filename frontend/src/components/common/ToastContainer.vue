<template>
  <TransitionGroup name="toast" tag="div" class="toast-container">
    <div
      v-for="toast in toasts"
      :key="toast.id"
      class="toast"
      :class="`toast--${toast.type}`"
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

      <button
        class="toast-close"
        @click.stop="dismiss(toast.id)"
        aria-label="Dismiss"
      >
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
/* =========================================================
   THEME VARIABLES — LIGHT MODE DEFAULT
   ========================================================= */

:root {
  --toast-surface: #ffffff;
  --toast-border: rgba(15, 23, 42, 0.08);
  --toast-shadow: rgba(0, 0, 0, 0.15);

  --toast-text-default: #0f172a;
  --toast-muted: #6b7280;

  /* Success */
  --toast-bg-success: linear-gradient(135deg, rgba(16,185,129,0.14) 0%, rgba(16,185,129,0.05) 100%);
  --toast-border-success: rgba(16,185,129,0.35);
  --toast-icon-success: #10b981;
  --toast-text-success: #065f46;

  /* Error */
  --toast-bg-error: linear-gradient(135deg, rgba(239,68,68,0.14) 0%, rgba(239,68,68,0.05) 100%);
  --toast-border-error: rgba(239,68,68,0.35);
  --toast-icon-error: #ef4444;
  --toast-text-error: #7f1d1d;

  /* Warning */
  --toast-bg-warning: linear-gradient(135deg, rgba(245,158,11,0.14) 0%, rgba(245,158,11,0.05) 100%);
  --toast-border-warning: rgba(245,158,11,0.35);
  --toast-icon-warning: #f59e0b;
  --toast-text-warning: #92400e;

  /* Info */
  --toast-bg-info: linear-gradient(135deg, rgba(59,130,246,0.14) 0%, rgba(59,130,246,0.05) 100%);
  --toast-border-info: rgba(59,130,246,0.35);
  --toast-icon-info: #3b82f6;
  --toast-text-info: #1e40af;

  --toast-icon-foreground: #ffffff;
}

/* =========================================================
   DARK MODE OVERRIDES
   ========================================================= */

@media (prefers-color-scheme: dark) {
  :root {
    --toast-surface: rgba(15, 23, 42, 0.85);
    --toast-border: rgba(255, 255, 255, 0.06);
    --toast-shadow: rgba(0, 0, 0, 0.45);

    --toast-text-default: #e5e7eb;
    --toast-muted: #9ca3af;

    --toast-bg-success: linear-gradient(135deg, rgba(16,185,129,0.12) 0%, rgba(16,185,129,0.04) 100%);
    --toast-border-success: rgba(16,185,129,0.25);
    --toast-text-success: #a7f3d0;

    --toast-bg-error: linear-gradient(135deg, rgba(239,68,68,0.12) 0%, rgba(239,68,68,0.04) 100%);
    --toast-border-error: rgba(239,68,68,0.25);
    --toast-text-error: #fecaca;

    --toast-bg-warning: linear-gradient(135deg, rgba(245,158,11,0.12) 0%, rgba(245,158,11,0.04) 100%);
    --toast-border-warning: rgba(245,158,11,0.25);
    --toast-text-warning: #fde68a;

    --toast-bg-info: linear-gradient(135deg, rgba(59,130,246,0.12) 0%, rgba(59,130,246,0.04) 100%);
    --toast-border-info: rgba(59,130,246,0.25);
    --toast-text-info: #bfdbfe;
  }
}

/* =========================================================
   CONTAINER
   ========================================================= */

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

/* =========================================================
   TOAST BASE
   ========================================================= */

.toast {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 14px 16px;
  border-radius: 12px;
  background: var(--toast-surface);
  border: 1px solid var(--toast-border);
  box-shadow: 0 8px 32px var(--toast-shadow);
  backdrop-filter: blur(12px);
  pointer-events: auto;
  cursor: pointer;
  min-width: 320px;
  transition: all 0.3s ease;
}

.toast:hover {
  transform: translateX(-4px);
  box-shadow: 0 12px 40px var(--toast-shadow);
}

/* =========================================================
   TYPE VARIANTS
   ========================================================= */

.toast--success {
  background: var(--toast-bg-success);
  border-color: var(--toast-border-success);
}

.toast--error {
  background: var(--toast-bg-error);
  border-color: var(--toast-border-error);
}

.toast--warning {
  background: var(--toast-bg-warning);
  border-color: var(--toast-border-warning);
}

.toast--info {
  background: var(--toast-bg-info);
  border-color: var(--toast-border-info);
}

/* =========================================================
   ICON
   ========================================================= */

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
  color: var(--toast-icon-foreground);
}

.toast--success .toast-icon { background: var(--toast-icon-success); }
.toast--error   .toast-icon { background: var(--toast-icon-error); }
.toast--warning .toast-icon { background: var(--toast-icon-warning); }
.toast--info    .toast-icon { background: var(--toast-icon-info); }

/* =========================================================
   CONTENT
   ========================================================= */

.toast-content {
  flex: 1;
  min-width: 0;
}

.toast-message {
  margin: 0;
  font-size: 14px;
  line-height: 1.5;
  font-weight: 500;
  word-wrap: break-word;
  color: var(--toast-text-default);
}

.toast--success .toast-message { color: var(--toast-text-success); }
.toast--error   .toast-message { color: var(--toast-text-error); }
.toast--warning .toast-message { color: var(--toast-text-warning); }
.toast--info    .toast-message { color: var(--toast-text-info); }

/* =========================================================
   CLOSE BUTTON
   ========================================================= */

.toast-close {
  flex-shrink: 0;
  background: none;
  border: none;
  color: var(--toast-muted);
  cursor: pointer;
  font-size: 20px;
  line-height: 1;
  padding: 0;
  margin: -4px -4px -4px 4px;
  opacity: 0.6;
  transition: opacity 0.2s ease;
}

.toast-close:hover {
  opacity: 1;
}

/* =========================================================
   TRANSITIONS
   ========================================================= */

.toast-enter-active {
  animation: toast-in 0.35s ease-out;
}

.toast-leave-active {
  animation: toast-out 0.3s ease-in;
}

@keyframes toast-in {
  from {
    opacity: 0;
    transform: translateX(100%);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}

@keyframes toast-out {
  from {
    opacity: 1;
    transform: translateX(0);
  }
  to {
    opacity: 0;
    transform: translateX(100%);
  }
}

/* =========================================================
   MOBILE
   ========================================================= */

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
