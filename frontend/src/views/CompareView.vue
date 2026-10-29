<script setup lang="ts">
import { ArrowLeftRight, GitCompareArrows, LoaderCircle } from "lucide-vue-next";
import { computed, onMounted, ref } from "vue";
import { RouterLink, useRouter } from "vue-router";

import { get, post, waitForJob, type Comparison, type Job, type Workspace } from "@/api/client";
import PageHeader from "@/components/PageHeader.vue";
import StatusBadge from "@/components/StatusBadge.vue";
import { ago, int } from "@/lib/format";
import { fail } from "@/state/toasts";

const router = useRouter();
const workspaces = ref<Workspace[]>([]);
const history = ref<Comparison[] | null>(null);
const left = ref("");
const right = ref("");
const ignoreCase = ref(false);
const trim = ref(true);
const ignoreCols = ref("CreatedBy, CreationDate, LastUpdatedBy, LastUpdateDate, LastUpdateLogin");
const running = ref<{ progress: number; total: number } | null>(null);

const ready = computed(() => workspaces.value.filter((w) => w.status === "converted"));
const names = computed(() => new Map(workspaces.value.map((w) => [w.id, w.name])));

onMounted(async () => {
  try {
    [workspaces.value, history.value] = await Promise.all([
      get<Workspace[]>("/workspaces"),
      get<Comparison[]>("/comparisons"),
    ]);
    left.value = ready.value[1]?.id ?? "";
    right.value = ready.value[0]?.id ?? "";
  } catch (e) {
    fail(e);
  }
});

async function start() {
  try {
    const job = await post<Job>("/comparisons", {
      left_workspace_id: left.value,
      right_workspace_id: right.value,
      ignore_case: ignoreCase.value,
      trim_whitespace: trim.value,
      ignore_columns: ignoreCols.value.split(",").map((c) => c.trim()).filter(Boolean),
    });
    running.value = { progress: 0, total: 0 };
    const final = await waitForJob(job.id, (j) => (running.value = { progress: j.progress, total: j.total }));
    if (final.status === "failed") throw new Error(final.message);
    await router.push({ name: "comparison", params: { id: job.subject_id } });
  } catch (e) {
    fail(e, "Comparison failed");
  } finally {
    running.value = null;
  }
}

function swap() {
  [left.value, right.value] = [right.value, left.value];
}
</script>

<template>
  <div class="page">
    <PageHeader title="Compare">
      <template #lede>
        Pair two converted workspaces — for example last month's extract and this month's — and see which
        datasets changed, row by row.
      </template>
    </PageHeader>

    <p v-if="workspaces.length && ready.length < 2" class="callout warn">
      <GitCompareArrows aria-hidden="true" />
      You need two converted workspaces to compare. You have {{ ready.length }}.
      <RouterLink to="/">Upload and convert another extract</RouterLink>.
    </p>

    <form class="setup panel" @submit.prevent="start">
      <div class="sides">
        <div class="field">
          <label for="left">Before</label>
          <select id="left" v-model="left" class="input" required>
            <option value="" disabled>Choose a workspace</option>
            <option v-for="w in ready" :key="w.id" :value="w.id" :disabled="w.id === right">{{ w.name }} · {{ ago(w.created_at) }}</option>
          </select>
        </div>
        <button type="button" class="btn btn-quiet btn-icon swap" aria-label="Swap before and after" @click="swap"><ArrowLeftRight aria-hidden="true" /></button>
        <div class="field">
          <label for="right">After</label>
          <select id="right" v-model="right" class="input" required>
            <option value="" disabled>Choose a workspace</option>
            <option v-for="w in ready" :key="w.id" :value="w.id" :disabled="w.id === left">{{ w.name }} · {{ ago(w.created_at) }}</option>
          </select>
        </div>
      </div>
      <details class="opts">
        <summary>Matching options</summary>
        <div class="opt-body">
          <label class="check"><input v-model="trim" type="checkbox" /> Ignore leading and trailing spaces</label>
          <label class="check"><input v-model="ignoreCase" type="checkbox" /> Ignore upper/lower case</label>
          <div class="field">
            <label for="ign">Columns to ignore</label>
            <input id="ign" v-model="ignoreCols" class="input" />
            <p class="hint">Comma-separated. Audit (WHO) columns are ignored by default so re-exports don't show as changes.</p>
          </div>
        </div>
      </details>
      <div>
        <button class="btn btn-primary" :disabled="!left || !right || left === right || !!running" :aria-busy="!!running">
          <LoaderCircle v-if="running" class="spin" aria-hidden="true" /><GitCompareArrows v-else aria-hidden="true" />
          {{ running ? (running.total ? `Comparing ${running.progress} / ${running.total}` : "Comparing…") : "Compare" }}
        </button>
      </div>
    </form>

    <section aria-labelledby="hist" class="hist">
      <h2 id="hist">Previous comparisons</h2>
      <p v-if="history && !history.length" class="muted">None yet.</p>
      <div v-else-if="history" class="table-region" tabindex="0" role="region" aria-labelledby="hist">
        <table class="table">
          <thead><tr><th scope="col">Before → After</th><th scope="col">Status</th><th scope="col" class="right">Modified</th><th scope="col" class="right">Added</th><th scope="col" class="right">Removed</th><th scope="col">When</th></tr></thead>
          <tbody>
            <tr v-for="c in history" :key="c.id">
              <th scope="row" class="pair"><RouterLink :to="{ name: 'comparison', params: { id: c.id } }">
                {{ names.get(c.left_workspace_id) ?? "deleted" }} → {{ names.get(c.right_workspace_id) ?? "deleted" }}</RouterLink></th>
              <td><StatusBadge :status="c.status" /></td>
              <td class="right num">{{ int(c.summary.MODIFIED ?? 0) }}</td>
              <td class="right num">{{ int(c.summary.ADDED ?? 0) }}</td>
              <td class="right num">{{ int(c.summary.REMOVED ?? 0) }}</td>
              <td>{{ ago(c.created_at) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>

<style scoped>
.page { display: grid; gap: var(--space-5); padding: var(--space-6); max-width: 1100px; align-content: start; }
.setup { display: grid; gap: var(--space-4); padding: var(--space-5); }
.sides { display: grid; grid-template-columns: 1fr auto 1fr; gap: var(--space-3); align-items: end; }
.swap { margin-bottom: 1px; }
.opts summary { cursor: pointer; font-weight: 600; color: var(--ink-2); }
.opt-body { display: grid; gap: var(--space-3); padding-top: var(--space-3); max-width: 70ch; }
.hist { display: grid; gap: var(--space-3); & h2 { font-size: var(--text-lg); } }
.pair { white-space: normal; font-weight: 600; & a { text-decoration: none; } & a:hover { text-decoration: underline; text-decoration-color: var(--gold); } }
@media (max-width: 760px) {
  .page { padding: var(--space-4); }
  .sides { grid-template-columns: 1fr; } .swap { justify-self: center; rotate: 90deg; }
}
</style>
