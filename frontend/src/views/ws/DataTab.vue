<script setup lang="ts">
import { FileSpreadsheet, Info, Trash2 } from "lucide-vue-next";
import { computed, ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";

import { del, type Dataset } from "@/api/client";
import DataGrid from "@/components/DataGrid.vue";
import GroupTabs from "@/components/GroupTabs.vue";
import { int } from "@/lib/format";
import { confirm } from "@/state/confirm";
import { fail, notify } from "@/state/toasts";
import { useWorkspace } from "@/state/workspace";

const { ws, reload } = useWorkspace();
const route = useRoute();
const router = useRouter();
const group = ref<string | null>(null);
const filter = ref("");

const datasets = computed(() => ws.value?.datasets ?? []);
const tabs = computed(() => {
  const counts = new Map<string, number>();
  for (const d of datasets.value) counts.set(d.group, (counts.get(d.group) ?? 0) + 1);
  const names = new Map(ws.value?.groups.map((g) => [g.code, g.module]) ?? []);
  return [...counts].sort().map(([code, count]) => ({ code, name: names.get(code), count }));
});
const listed = computed(() => {
  const f = filter.value.trim().toUpperCase();
  return datasets.value.filter((d) => (group.value === null || d.group === group.value) && (!f || d.name.includes(f)));
});
const selected = computed<Dataset | undefined>(() =>
  datasets.value.find((d) => d.id === route.query.d) ?? listed.value[0],
);
const focusRow = computed(() => (typeof route.query.row === "string" ? Number(route.query.row) : null));

watch(selected, (d) => {
  if (d && d.group !== group.value && group.value !== null) group.value = d.group;
});

function pick(d: Dataset) {
  void router.replace({ query: { d: d.id } });
}

async function remove(d: Dataset) {
  if (!(await confirm({ title: `Delete ${d.name}?`, body: "The dataset is removed from this workspace and the search index. Re-converting brings it back without your edits.", action: "Delete dataset", danger: true }))) return;
  try {
    await del(`/datasets/${d.id}`);
    notify(`Deleted ${d.name}.`);
    await router.replace({ query: {} });
    await reload();
  } catch (e) {
    fail(e);
  }
}
</script>

<template>
  <div v-if="ws && !datasets.length" class="empty">
    <Info aria-hidden="true" />
    <div>
      <p class="strong">Nothing converted yet</p>
      <p class="muted">Convert the workspace to turn its XML, CSV and XLSX files into datasets you can browse and edit here.</p>
      <RouterLink :to="{ name: 'files' }" class="btn btn-sm">Review files</RouterLink>
    </div>
  </div>

  <div v-else-if="ws" class="data">
    <GroupTabs v-model="group" :groups="tabs" :total="datasets.length" label="Filter datasets by module group" />
    <div class="sheet">
      <aside class="list" aria-label="Datasets">
        <label class="visually-hidden" for="ds-filter">Filter datasets</label>
        <input id="ds-filter" v-model="filter" class="input" type="search" placeholder="Filter by name…" />
        <ul>
          <li v-for="d in listed" :key="d.id">
            <button type="button" class="item" :aria-current="selected?.id === d.id ? 'true' : undefined" @click="pick(d)">
              <FileSpreadsheet aria-hidden="true" />
              <span class="nm" :title="d.name">{{ d.name.replace(/\.CSV$/, "") }}</span>
              <span class="dim num">{{ int(d.rows) }} × {{ int(d.columns) }}<template v-if="d.edited"> · edited</template></span>
            </button>
          </li>
          <li v-if="!listed.length" class="subtle small pad">No datasets match.</li>
        </ul>
      </aside>

      <div v-if="selected" class="detail">
        <div class="head">
          <div>
            <h2 class="mono">{{ selected.name }}</h2>
            <p class="small subtle path">
              <span class="mono">{{ selected.group }}</span>
              <template v-if="selected.record_tag"> · record &lt;{{ selected.record_tag }}&gt;</template>
              · {{ selected.logical_path }}
            </p>
          </div>
          <button type="button" class="btn btn-quiet btn-sm" @click="remove(selected)"><Trash2 aria-hidden="true" /> Delete</button>
        </div>
        <DataGrid :dataset="selected" :focus-row="focusRow" @changed="reload" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.data { display: grid; }
.sheet {
  display: grid; grid-template-columns: 260px minmax(0, 1fr);
  background: var(--surface); border: 1px solid var(--line-strong); border-top: 0;
  border-radius: 0 0 var(--radius-lg) var(--radius-lg); min-height: 60vh;
}
.list { border-right: 1px solid var(--line); padding: 10px; display: grid; gap: 8px; align-content: start;
  & ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 1px; max-height: 70vh; overflow: auto; } }
.item {
  display: grid; grid-template-columns: 16px minmax(0, 1fr); column-gap: 8px; width: 100%; padding: 7px 8px;
  border: 0; border-radius: var(--radius); background: none; color: var(--ink-2); text-align: start; cursor: pointer; font: inherit;
  & svg { width: 16px; height: 16px; margin-top: 2px; color: var(--ink-3); }
  &:hover { background: var(--sunken); color: var(--ink); }
  &[aria-current="true"] { background: var(--gold-wash); color: var(--ink); & svg { color: var(--gold-ink); } }
}
.nm { font: 600 var(--text-sm)/1.35 var(--mono); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dim { grid-column: 2; font-size: var(--text-xs); color: var(--ink-3); }
.pad { padding: 8px; }
.detail { min-width: 0; padding: var(--space-4); display: grid; gap: var(--space-3); align-content: start; }
.head { display: flex; justify-content: space-between; gap: var(--space-3); align-items: flex-start; }
h2 { font-size: var(--text-lg); overflow-wrap: anywhere; }
.path { overflow-wrap: anywhere; }
.empty { display: flex; gap: var(--space-4); padding: var(--space-5); border: 1px solid var(--line); border-radius: var(--radius-lg); background: var(--surface); max-width: 70ch;
  & > svg { width: 24px; height: 24px; flex: none; color: var(--ink-3); } & .strong { font-weight: 650; } & > div { display: grid; gap: 8px; justify-items: start; } }
@media (max-width: 1000px) {
  .sheet { grid-template-columns: 1fr; }
  .list { border-right: 0; border-bottom: 1px solid var(--line); & ul { max-height: 30vh; } }
}
</style>
