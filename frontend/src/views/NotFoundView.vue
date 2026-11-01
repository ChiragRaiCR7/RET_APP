<script setup lang="ts">
import { RouterLink } from "vue-router";

import PageHeader from "@/components/PageHeader.vue";
</script>

<template>
  <div class="page">
    <PageHeader title="Page not found">
      <template #lede>The address doesn't match anything in RET.</template>
    </PageHeader>
    <div><RouterLink to="/" class="btn">Go to workspaces</RouterLink></div>
  </div>
</template>

<style scoped>
.page { display: grid; gap: var(--space-4); padding: var(--space-6); }
</style>
