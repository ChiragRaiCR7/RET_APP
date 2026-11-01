<script setup lang="ts">
import { CircleAlert, CircleCheck, Info, X } from "lucide-vue-next";

import { dismiss, toasts } from "@/state/toasts";

const icon = { ok: CircleCheck, bad: CircleAlert, info: Info } as const;
</script>

<template>
  <div class="toasts" role="status" aria-live="polite">
    <TransitionGroup name="toast">
      <div v-for="t in toasts" :key="t.id" class="toast" :class="t.kind">
        <component :is="icon[t.kind]" aria-hidden="true" class="ic" />
        <p>{{ t.text }}</p>
        <button type="button" class="btn btn-quiet btn-sm btn-icon" aria-label="Dismiss" @click="dismiss(t.id)">
          <X aria-hidden="true" />
        </button>
      </div>
    </TransitionGroup>
  </div>
</template>

<style scoped>
.toasts {
  position: fixed; right: 16px; bottom: 16px; z-index: 50;
  display: grid; gap: 8px; width: min(380px, calc(100vw - 32px));
}
.toast {
  display: flex; align-items: flex-start; gap: 10px; padding: 10px 10px 10px 14px;
  background: var(--raised); border: 1px solid var(--line); border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  & p { flex: 1; padding-top: 4px; }
}
.ic { flex: none; width: 18px; height: 18px; margin-top: 5px; }
.ok .ic { color: var(--ok); }
.bad .ic { color: var(--bad); }
.info .ic { color: var(--info); }
.toast-enter-active, .toast-leave-active { transition: opacity 0.2s, translate 0.25s var(--ease-out); }
.toast-enter-from, .toast-leave-to { opacity: 0; translate: 0 8px; }
@media (prefers-reduced-motion: reduce) {
  .toast-enter-active, .toast-leave-active { transition: none; }
}
</style>
