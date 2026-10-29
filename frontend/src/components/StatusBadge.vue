<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{ status: string }>();

const look = computed(() => {
  switch (props.status) {
    case "converted":
    case "succeeded":
    case "SAME":
      return { cls: "ok", label: props.status === "SAME" ? "Same" : props.status === "converted" ? "Converted" : "Done" };
    case "converting":
    case "running":
    case "queued":
      return { cls: "gold", label: props.status === "converting" ? "Converting" : props.status === "queued" ? "Queued" : "Running" };
    case "failed":
      return { cls: "bad", label: "Failed" };
    case "MODIFIED":
      return { cls: "warn", label: "Modified" };
    case "ADDED":
      return { cls: "info", label: "Added" };
    case "REMOVED":
      return { cls: "bad", label: "Removed" };
    default:
      return { cls: "", label: "Scanned" };
  }
});
</script>

<template>
  <span class="badge" :class="look.cls">{{ look.label }}</span>
</template>
