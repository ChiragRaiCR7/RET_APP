<script setup lang="ts">
import { Download, LoaderCircle, Play, RefreshCw, Trash2 } from "lucide-vue-next";
import { computed, onBeforeUnmount, provide, ref, watch } from "vue";
import { RouterLink, RouterView, useRouter } from "vue-router";

import { ApiError, del, get, post, waitForJob, type Job, type WorkspaceDetail } from "@/api/client";
import ExportDialog from "@/components/ExportDialog.vue";
import PageHeader from "@/components/PageHeader.vue";
import StatusBadge from "@/components/StatusBadge.vue";
import { bytes, dateTime, int, plural } from "@/lib/format";
import { confirm } from "@/state/confirm";
import { fail, notify } from "@/state/toasts";
import { WORKSPACE } from "@/state/workspace";

const props = defineProps<{ id: string }>();
const router = useRouter();
const ws = ref<WorkspaceDetail | null>(null);
const missing = ref(false);
const converting = ref<{ progress: number; total: number } | null>(null);
const exportOpen = ref(false);
let poll: AbortController | null = null;

async function reload() {
  try {
    ws.value = await get<WorkspaceDetail>(`/workspaces/${props.id}`);
    document.title = `${ws.value.name} · RET`;
    if (ws.value.active_job && !poll) void follow(ws.value.active_job);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) missing.value = true;
    else fail(e);
  }
}

async function follow(job: Job) {
  poll = new AbortController();
  converting.value = { progress: job.progress, total: job.total };
  try {
    const final = await waitForJob(job.id, (j) => (converting.value = { progress: j.progress, total: j.total }), poll.signal);
    if (final.status === "succeeded") notify(final.message);
    else fail(new Error(final.message), "Conversion failed");
  } catch (e) {
    if (!(e instanceof DOMException && e.name === "AbortError")) fail(e);
  } finally {
    converting.value = null;
    poll = null;
    await reload();
  }
}

async function convert(groups: string[] | null = null) {
  if (!ws.value) return;
  if (ws.value.datasets.length) {
    const ok = await confirm({
      title: "Convert again?",
      body: "Re-converting replaces the current datasets, including any edits you made, and clears the search index.",
      action: "Replace and convert",
      danger: true,
    });
    if (!ok) return;
  }
  try {
    const job = await post<Job>(`/workspaces/${props.id}/convert`, { groups });
    if (ws.value) ws.value.status = "converting";
    void follow(job); // follow() reloads when done; reloading here would start a second poller
  } catch (e) {
    fail(e, "Could not start conversion");
  }
}

async function remove() {
  if (!ws.value) return;
  const ok = await confirm({
    title: `Delete ${ws.value.name}?`,
    body: "This permanently removes the uploaded files, converted datasets, search index and conversation. It cannot be undone.",
    action: "Delete workspace",
    danger: true,
  });
  if (!ok) return;
  try {
    await del(`/workspaces/${props.id}`);
    notify(`Deleted ${ws.value.name}.`);
    await router.replace("/");
  } catch (e) {
    fail(e);
  }
}

watch(() => props.id, () => {
  poll?.abort();
  ws.value = null;
  missing.value = false;
  void reload();
}, { immediate: true });
onBeforeUnmount(() => poll?.abort());

provide(WORKSPACE, { ws, reload, convert, converting });

const included = computed(() => ws.value?.sources.filter((s) => !s.excluded).length ?? 0);
const tabs = [
  { name: "files", label: "Files" },
  { name: "data", label: "Data" },
  { name: "structure", label: "Structure" },
  { name: "ask", label: "Ask" },
] as const;
</script>

<template>
  <div v-if="missing" class="page">
    <PageHeader title="Workspace not found">
      <template #lede>It may have been deleted, or it belongs to someone else.</template>
    </PageHeader>
    <RouterLink to="/" class="btn">Back to workspaces</RouterLink>
  </div>

  <div v-else class="page">
    <PageHeader :title="ws?.name ?? 'Loading…'">
      <template #crumbs>
        <nav aria-label="Breadcrumb" class="crumbs"><RouterLink to="/">Workspaces</RouterLink> /</nav>
      </template>
      <template #status>
        <StatusBadge v-if="ws" :status="ws.status" />
      </template>
      <template #lede>
        <span v-if="ws" class="meta num">
          {{ plural(ws.sources.length, "file") }} in {{ plural(ws.groups.length, "group") }} ·
          {{ bytes(ws.upload_bytes) }} uploaded · {{ dateTime(ws.created_at) }}
          <template v-if="ws.datasets.length"> · {{ plural(ws.datasets.length, "dataset") }}</template>
        </span>
      </template>
      <template #actions>
        <template v-if="ws">
          <button v-if="converting" class="btn btn-primary" disabled aria-busy="true">
            <LoaderCircle class="spin" aria-hidden="true" />
            Converting {{ converting.total ? `${int(converting.progress)} / ${int(converting.total)}` : "…" }}
          </button>
          <button v-else-if="ws.status !== 'converted'" class="btn btn-primary" :disabled="!included" @click="convert()">
            <Play aria-hidden="true" /> Convert {{ plural(included, "file") }}
          </button>
          <template v-else>
            <button class="btn btn-primary" @click="exportOpen = true"><Download aria-hidden="true" /> Export</button>
            <button class="btn" @click="convert()"><RefreshCw aria-hidden="true" /> Re-convert</button>
          </template>
          <button class="btn btn-quiet btn-icon" aria-label="Delete workspace" title="Delete workspace"
                  :disabled="!!converting" @click="remove">
            <Trash2 aria-hidden="true" />
          </button>
        </template>
      </template>
    </PageHeader>

    <nav class="tabs" aria-label="Workspace sections">
      <RouterLink v-for="t in tabs" :key="t.name" :to="{ name: t.name, params: { id } }" class="tab"
                  active-class="on" :aria-current="$route.name === t.name ? 'page' : undefined">
        {{ t.label }}
        <span v-if="t.name === 'data' && ws?.datasets.length" class="count num">{{ ws.datasets.length }}</span>
      </RouterLink>
    </nav>

    <div v-if="!ws" class="loading" aria-busy="true"><span class="skeleton" /><span class="skeleton" /></div>
    <RouterView v-else />

    <ExportDialog v-if="ws && exportOpen" :ws="ws" @close="exportOpen = false" />
  </div>
</template>

<style scoped>
.page { display: grid; gap: var(--space-4); padding: var(--space-5) var(--space-6) var(--space-7); align-content: start; }
.crumbs { font-size: var(--text-sm); color: var(--ink-3); & a { color: var(--ink-2); } }
.meta { color: var(--ink-2); }
.tabs {
  display: flex; gap: var(--space-1); border-bottom: 1px solid var(--line); overflow-x: auto;
  margin-top: var(--space-2);
}
.tab {
  position: relative; display: inline-flex; align-items: center; gap: 8px; padding: 10px 14px 12px;
  color: var(--ink-2); font-weight: 600; text-decoration: none; white-space: nowrap;
  &:hover { color: var(--ink); }
  &.on { color: var(--ink); }
  &.on::after { content: ""; position: absolute; inset: auto 8px -1px; height: 2px; background: var(--gold); border-radius: 2px; }
}
.count { padding: 1px 7px; border-radius: 999px; background: var(--sunken); color: var(--ink-2); font-size: var(--text-xs); }
.loading { display: grid; gap: 10px; & .skeleton { height: 18px; } & .skeleton:last-child { width: 60%; } }
@media (max-width: 860px) { .page { padding: var(--space-4); } }
</style>
