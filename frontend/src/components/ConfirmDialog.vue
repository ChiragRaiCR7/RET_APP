<script setup lang="ts">
import { nextTick, ref, watch } from "vue";

import { confirmState } from "@/state/confirm";

const dlg = ref<HTMLDialogElement | null>(null);

watch(
  () => confirmState.current,
  async (req) => {
    if (!req) return;
    await nextTick();
    dlg.value?.showModal();
  },
);

function onClose() {
  const req = confirmState.current;
  const ok = dlg.value?.returnValue === "confirm";
  if (dlg.value) dlg.value.returnValue = ""; // Esc sets no value; reset so it never leaks
  confirmState.current = null;
  req?.resolve(ok);
}
</script>

<template>
  <dialog ref="dlg" class="dialog" aria-labelledby="confirm-title" closedby="any" @close="onClose">
    <form v-if="confirmState.current" method="dialog" class="body">
      <h2 id="confirm-title">{{ confirmState.current.title }}</h2>
      <p class="muted">{{ confirmState.current.body }}</p>
      <div class="actions">
        <button class="btn" value="cancel" autofocus>Cancel</button>
        <button class="btn" :class="confirmState.current.danger ? 'btn-danger' : 'btn-primary'" value="confirm">
          {{ confirmState.current.action }}
        </button>
      </div>
    </form>
  </dialog>
</template>

<style scoped>
.body { display: grid; gap: var(--space-3); padding: var(--space-5); }
h2 { font-size: var(--text-lg); }
.actions { display: flex; justify-content: flex-end; gap: var(--space-2); margin-top: var(--space-2); }
</style>
