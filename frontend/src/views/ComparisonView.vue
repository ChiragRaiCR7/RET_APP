<script setup lang="ts">
import { X } from "lucide-vue-next";
import { computed, ref, watch } from "vue";
import { RouterLink } from "vue-router";

import { ApiError, get, type ComparisonDetail, type ComparisonItem, type Diff } from "@/api/client";
import PageHeader from "@/components/PageHeader.vue";
import StatusBadge from "@/components/StatusBadge.vue";
import DiffTable from "@/components/DiffTable.vue";
import { dateTime, int } from "@/lib/format";
import { fail } from "@/state/toasts";

const props = defineProps<{ id: string }>();
const data = ref<ComparisonDetail | null>(null);
const missing = ref(false);
const filter = ref<string | null>("MODIFIED");
const open = ref<ComparisonItem | null>(null);
const diff = ref<Diff | null>(null);
const diffLoading = ref(false);

watch(() => props.id, async () => {
  try {
    data.value = await get<ComparisonDetail>(`/comparisons/${props.id}`);
    if (!data.value.summary.MODIFIED) filter.value = null;
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) missing.value = true;
    else fail(e);
  }
}, { immediate: true });

const STATUSES = ["MODIFIED", "ADDED", "REMOVED", "SAME"] as const;
const LABEL = { MODIFIED: "Modified", ADDED: "Only after", REMOVED: "Only before", SAME: "Unchanged" } as const;
const items = computed(() => (data.value?.items ?? []).filter((i) => !filter.value || i.status === filter.value));

async function inspect(item: ComparisonItem) {
  open.value = item;
  diff.value = null;
  diffLoading.value = true;
  try {
    diff.value = await get<Diff>(`/comparisons/${props.id}/items/${item.id}/diff`);
  } catch (e) {
    fail(e);
  } finally {
    diffLoading.value = false;
  }
}
</script>

<template>
  <div v-if="missing" class="page"><PageHeader title="Comparison not found" /><RouterLink to="/compare" class="btn">Back to compare</RouterLink></div>
  <div v-else-if="data" class="page">
    <PageHeader :title="`${data.left_name} → ${data.right_name}`">
      <template #crumbs><nav aria-label="Breadcrumb" class="crumbs"><RouterLink to="/compare">Compare</RouterLink> /</nav></template>
      <template #lede>
        {{ dateTime(data.created_at) }}<template v-if="(data.options.ignore_columns as string[] | undefined)?.length"> ·
        ignoring {{ (data.options.ignore_columns as string[]).join(", ") }}</template>
      </template>
    </PageHeader>

    <div class="filters" role="toolbar" aria-label="Filter by result">
      <button v-for="s in STATUSES" :key="s" type="button" class="seg" :class="s.toLowerCase()" :aria-pressed="filter === s"
              @click="filter = filter === s ? null : s">
        <span class="v num">{{ int(data.summary[s] ?? 0) }}</span><span class="l">{{ LABEL[s] }}</span>
      </button>
    </div>

    <div class="table-region" tabindex="0" role="region" aria-label="Datasets compared">
      <table class="table">
        <thead>
          <tr><th scope="col">Dataset</th><th scope="col">Group</th><th scope="col">Result</th>
            <th scope="col" class="right">Rows before</th><th scope="col" class="right">Rows after</th>
            <th scope="col" class="right">Changed</th><th scope="col" class="right">Added</th><th scope="col" class="right">Removed</th></tr>
        </thead>
        <tbody>
          <tr v-for="i in items" :key="i.id" :class="{ sel: open?.id === i.id }">
            <th scope="row"><button type="button" class="linkish mono" @click="inspect(i)">{{ i.name }}</button></th>
            <td class="mono">{{ i.group }}</td>
            <td><StatusBadge :status="i.status" /></td>
            <td class="right num">{{ int(i.rows_left) }}</td>
            <td class="right num">{{ int(i.rows_right) }}</td>
            <td class="right num">{{ i.modified ? int(i.modified) : "" }}</td>
            <td class="right num">{{ i.added ? int(i.added) : "" }}</td>
            <td class="right num">{{ i.removed ? int(i.removed) : "" }}</td>
          </tr>
          <tr v-if="!items.length"><td colspan="8" class="subtle">No datasets in this category.</td></tr>
        </tbody>
      </table>
    </div>

    <section v-if="open" class="drill panel" :aria-label="`Differences in ${open.name}`">
      <header class="drill-head">
        <div>
          <h2 class="mono">{{ open.name }}</h2>
          <p v-if="diff" class="small muted num">
            {{ int(diff.stats.modified ?? 0) }} changed · {{ int(diff.stats.added ?? 0) }} added ·
            {{ int(diff.stats.removed ?? 0) }} removed · {{ int(diff.stats.equal ?? 0) }} unchanged rows
            <template v-if="diff.truncated"> · showing the first 2,000 differences</template>
          </p>
        </div>
        <button type="button" class="btn btn-quiet btn-icon" aria-label="Close differences" @click="open = null"><X aria-hidden="true" /></button>
      </header>
      <div v-if="diffLoading" class="skeleton" style="height: 160px" />
      <p v-else-if="diff && !diff.rows.length" class="muted">No row differences after applying the ignore rules.</p>
      <DiffTable v-else-if="diff" :diff="diff" />
    </section>
  </div>
  <div v-else class="page"><div class="skeleton" style="height: 200px" /></div>
</template>

<style scoped>
.page { display: grid; gap: var(--space-4); padding: var(--space-5) var(--space-6) var(--space-7); align-content: start; }
.crumbs { font-size: var(--text-sm); color: var(--ink-3); & a { color: var(--ink-2); } }
.filters { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }
.seg {
  display: grid; gap: 2px; padding: 10px 14px; text-align: start; cursor: pointer; font: inherit; color: var(--ink);
  background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius-lg);
  &:hover { border-color: var(--line-strong); }
  &[aria-pressed="true"] { border-color: var(--ink); box-shadow: 0 0 0 1px var(--ink); }
  & .v { font-size: var(--text-xl); font-weight: 700; } & .l { font-size: var(--text-sm); color: var(--ink-2); }
  &.modified .v { color: var(--warn); } &.added .v { color: var(--info); } &.removed .v { color: var(--bad); } &.same .v { color: var(--ok); }
}
.linkish { padding: 0; border: 0; background: none; color: var(--ink); font-weight: 600; cursor: pointer; text-align: start;
  text-decoration: underline; text-decoration-color: var(--line-strong); text-underline-offset: 0.2em;
  &:hover { text-decoration-color: var(--gold); } }
tr.sel > * { background: var(--gold-wash); }
.drill { display: grid; gap: var(--space-3); padding: var(--space-4); }
.drill-head { display: flex; justify-content: space-between; gap: var(--space-3); & h2 { font-size: var(--text-lg); } }
@media (max-width: 760px) { .page { padding: var(--space-4); } .filters { grid-template-columns: repeat(2, 1fr); } }
</style>
