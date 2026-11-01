<script setup lang="ts">
defineProps<{ title: string }>();
</script>

<template>
  <header class="head">
    <div class="titles">
      <slot name="crumbs" />
      <div class="row">
        <h1>{{ title }}</h1>
        <slot name="status" />
      </div>
      <p v-if="$slots.lede" class="lede"><slot name="lede" /></p>
    </div>
    <div v-if="$slots.actions" class="actions"><slot name="actions" /></div>
  </header>
</template>

<style scoped>
.head { display: flex; align-items: flex-end; justify-content: space-between; gap: var(--space-4); flex-wrap: wrap; }
.titles { display: grid; gap: 6px; min-width: 0; }
.row { display: flex; align-items: center; gap: var(--space-3); flex-wrap: wrap; }
h1 { overflow-wrap: anywhere; }
.lede { color: var(--ink-2); max-width: 70ch; }
.actions { display: flex; gap: var(--space-2); flex-wrap: wrap; }
</style>
