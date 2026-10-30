<template>
  <label class="toggle-inline">
    <input
      type="checkbox"
      :checked="modelValue"
      @change="$emit('update:modelValue', ($event.target as HTMLInputElement).checked)"
      style="accent-color: var(--brand-primary)"
    />
    <span>Enable Edit Mode</span>
  </label>
</template>

<script setup lang="ts">
defineProps({
  modelValue: {
    type: Boolean,
    default: false
  }
})

defineEmits(['update:modelValue'])
</script>

<style scoped>
.toggle-inline {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  font-weight: 700;
  font-size: 0.92rem;
  color: var(--text-primary);
  user-select: none;
}
</style>
