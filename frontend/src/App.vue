<script setup lang="ts">
import { computed } from "vue";
import { RouterView, useRoute } from "vue-router";

import AppShell from "@/components/AppShell.vue";
import ConfirmDialog from "@/components/ConfirmDialog.vue";
import ToastStack from "@/components/ToastStack.vue";

const route = useRoute();
const bare = computed(() => route.meta.public === true);
</script>

<template>
  <RouterView v-if="bare" />
  <AppShell v-else>
    <RouterView />
  </AppShell>
  <ToastStack />
  <ConfirmDialog />
</template>
