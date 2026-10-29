<script setup lang="ts">
import { computed } from "vue";

import type { StructureNode } from "@/api/client";

defineOptions({ name: "StructureTree" });
const props = defineProps<{ node: StructureNode; needle: string; depth?: number; expandAll?: boolean }>();

const LABEL: Record<StructureNode["type"], string> = {
  business_group: "Business group",
  ledger: "Ledger",
  legal_entity: "Legal entity",
  operating_unit: "Operating unit",
  inventory_org: "Inventory org",
};

function matches(n: StructureNode, needle: string): boolean {
  return !needle || n.name.toLowerCase().includes(needle) || (n.children ?? []).some((c) => matches(c, needle));
}
const kids = computed(() => (props.node.children ?? []).filter((c) => matches(c, props.needle)));
const hit = computed(() => !!props.needle && props.node.name.toLowerCase().includes(props.needle));
</script>

<template>
  <li :class="['node', node.type]">
    <details v-if="kids.length" :open="expandAll || (depth ?? 0) < 3 || !!needle">
      <summary>
        <span class="type">{{ LABEL[node.type] }}</span>
        <span class="name" :class="{ hit }">{{ node.name }}</span>
        <span class="n num">{{ kids.length }}</span>
      </summary>
      <ul>
        <StructureTree v-for="c in kids" :key="c.type + c.name" :node="c" :needle="needle" :depth="(depth ?? 0) + 1" :expand-all="expandAll" />
      </ul>
    </details>
    <div v-else class="leaf">
      <span class="type">{{ LABEL[node.type] }}</span>
      <span class="name" :class="{ hit }">{{ node.name }}</span>
    </div>
  </li>
</template>

<style scoped>
.node { list-style: none; }
ul { margin: 0; padding: 0 0 0 22px; border-left: 1px solid var(--line); margin-left: 9px; }
summary, .leaf {
  display: flex; align-items: baseline; gap: 10px; padding: 5px 8px; border-radius: var(--radius); cursor: default;
}
summary { cursor: pointer; list-style: none;
  &::-webkit-details-marker { display: none; }
  &::before { content: ""; width: 7px; height: 7px; flex: none; translate: 0 -1px; border: solid var(--ink-3); border-width: 0 1.5px 1.5px 0; rotate: -45deg; transition: rotate 0.15s; }
  &:hover { background: var(--sunken); } }
details[open] > summary::before { rotate: 45deg; }
.leaf::before { content: ""; width: 7px; height: 7px; flex: none; border-radius: 50%; background: var(--line-strong); }
.type { flex: none; font-size: var(--text-xs); color: var(--ink-3); text-transform: uppercase; letter-spacing: 0.04em; }
.name { font-weight: 550; }
.business_group > details > summary .name, .ledger > details > summary .name { font-weight: 700; }
.hit { background: var(--gold-wash); box-shadow: 0 0 0 2px var(--gold-wash); border-radius: 2px; }
.n { font-size: var(--text-xs); color: var(--ink-3); }
</style>
