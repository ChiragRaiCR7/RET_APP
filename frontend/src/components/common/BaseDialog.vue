<script setup lang="ts">
/**
 * Modal built on the native <dialog>: showModal() gives focus containment, Escape,
 * an inert background and the top layer, so none of that is hand-rolled per modal.
 * Content is mounted only while open, so its state resets between openings.
 * Parent classes fall through to the <dialog> element for sizing and surface styles.
 */
import { onMounted, ref, watch } from 'vue'

const props = defineProps<{ open: boolean; labelledby?: string }>()
const emit = defineEmits<{ close: [] }>()
const el = ref<HTMLDialogElement | null>(null)

function sync(open: boolean): void {
  const d = el.value
  if (!d) return
  if (open && !d.open) d.showModal()
  else if (!open && d.open) d.close()
}

watch(() => props.open, sync, { flush: 'post' })
onMounted(() => sync(props.open))

// A click whose target is the <dialog> itself landed on the backdrop (the box has no padding).
function onClick(event: MouseEvent): void {
  if (event.target === el.value) emit('close')
}
</script>

<template>
  <dialog ref="el" class="base-dialog" :aria-labelledby="labelledby" @cancel.prevent="emit('close')" @click="onClick">
    <slot v-if="open" />
  </dialog>
</template>

<style scoped>
.base-dialog {
  padding: 0;
  border: none;
  color: inherit;
  max-width: calc(100vw - 16px);
  max-height: calc(100vh - 16px);
}
.base-dialog::backdrop { background: rgb(0 0 0 / 0.6); }
</style>
