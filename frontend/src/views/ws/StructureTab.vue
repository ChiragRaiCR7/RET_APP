<script setup lang="ts">
import { CircleAlert, Info } from "lucide-vue-next";
import { computed, ref, watch } from "vue";

import { get, query, type Structure } from "@/api/client";
import StructureTree from "@/components/StructureTree.vue";
import { int } from "@/lib/format";
import { fail } from "@/state/toasts";
import { useWorkspace } from "@/state/workspace";

const { ws } = useWorkspace();
const data = ref<Structure | null>(null);
const bg = ref("");
const needle = ref("");

async function load() {
  if (!ws.value) return;
  try {
    data.value = await get<Structure>(`/workspaces/${ws.value.id}/structure${query({ business_group: bg.value.trim() })}`);
  } catch (e) {
    fail(e);
  }
}
watch(() => [ws.value?.id, ws.value?.datasets.length], load, { immediate: true });

// Small organisations read best fully expanded; large ones open three levels deep.
const small = computed(() => Object.values(data.value?.counts ?? {}).reduce((a, b) => a + b, 0) <= 200);
const levels = computed(() => [
  ["ledger", "Ledgers"],
  ["legal_entity", "Legal entities"],
  ["operating_unit", "Operating units"],
  ["inventory_org", "Inventory orgs"],
] as const);
</script>

<template>
  <div class="tab">
    <div v-if="!data" class="skeleton" style="height: 120px" aria-busy="true" />

    <div v-else-if="data.status !== 'ready'" class="callout" :class="data.status === 'no_data' ? 'warn' : ''">
      <Info aria-hidden="true" />
      <div>
        <p><strong>{{ data.status === "missing_files" ? "No organization data in this workspace" : "Organization data found, but nothing could be linked" }}</strong></p>
        <p v-for="d in data.diagnostics" :key="d" class="small">{{ d }}</p>
      </div>
    </div>

    <template v-else-if="data.root">
      <ol class="ruler" aria-label="Hierarchy levels">
        <li v-for="[key, label] in levels" :key="key">
          <span class="v num">{{ int(data.counts[key] ?? 0) }}</span>
          <span class="l">{{ label }}</span>
        </li>
      </ol>

      <div class="tools">
        <label class="field grow">
          <span class="label">Find an entity</span>
          <input v-model="needle" class="input" type="search" placeholder="Ledger, legal entity, unit or org name" />
        </label>
        <form class="field" @submit.prevent="load">
          <label class="label" for="bg">Business group name</label>
          <div class="inline">
            <input id="bg" v-model="bg" class="input" placeholder="Default Business Group" maxlength="120" />
            <button class="btn">Apply</button>
          </div>
        </form>
      </div>

      <ul class="tree panel" aria-label="Business structure">
        <StructureTree :node="data.root" :needle="needle.trim().toLowerCase()" :expand-all="small" />
      </ul>

      <details v-if="data.diagnostics.length" class="callout warn diag">
        <summary><CircleAlert aria-hidden="true" class="ic" /> {{ data.diagnostics.length }} data quality notes</summary>
        <ul><li v-for="d in data.diagnostics" :key="d">{{ d }}</li></ul>
      </details>
      <p class="small subtle">Built from {{ data.sources.join(", ") }}.</p>
    </template>
  </div>
</template>

<style scoped>
.tab { display: grid; gap: var(--space-4); }
.ruler {
  display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); margin: 0; padding: 0; list-style: none;
  border: 1px solid var(--line); border-radius: var(--radius-lg); background: var(--surface); overflow: hidden;
  & li { position: relative; display: grid; gap: 2px; padding: 12px 16px; }
  & li + li { border-left: 1px solid var(--line); }
  & li + li::before { content: ""; position: absolute; left: -6px; top: 50%; width: 10px; height: 10px; translate: 0 -50%; rotate: 45deg;
    background: var(--surface); border: solid var(--line); border-width: 1px 1px 0 0; }
}
.v { font-size: var(--text-xl); font-weight: 700; }
.l { font-size: var(--text-sm); color: var(--ink-2); }
.tools { display: flex; gap: var(--space-4); flex-wrap: wrap; align-items: end; }
.grow { flex: 1 1 280px; }
.inline { display: flex; gap: 6px; }
.tree { margin: 0; padding: var(--space-3); overflow-x: auto; }
.diag { display: block; & summary { cursor: pointer; font-weight: 600; } & ul { margin: 8px 0 0; padding-left: 18px; } }
.ic { width: 16px; height: 16px; vertical-align: -3px; color: var(--warn); }
@media (max-width: 640px) { .ruler { grid-template-columns: repeat(2, 1fr); & li:nth-child(3) { border-left: 0; } } }
</style>
