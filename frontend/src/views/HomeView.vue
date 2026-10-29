<script setup lang="ts">
import { ArrowRight, FolderOpen } from "lucide-vue-next";
import { onMounted, ref } from "vue";
import { RouterLink, useRouter } from "vue-router";

import { get, type Workspace, type WorkspaceDetail } from "@/api/client";
import PageHeader from "@/components/PageHeader.vue";
import StatusBadge from "@/components/StatusBadge.vue";
import UploadDrop from "@/components/UploadDrop.vue";
import { ago, bytes, dateTime, int } from "@/lib/format";
import { session } from "@/state/session";
import { fail, notify } from "@/state/toasts";

const router = useRouter();
const items = ref<Workspace[] | null>(null);

onMounted(async () => {
  try {
    items.value = await get<Workspace[]>("/workspaces");
  } catch (e) {
    fail(e);
    items.value = [];
  }
});

function opened(ws: WorkspaceDetail) {
  notify(`Scanned ${ws.name}: ${ws.sources.length} files in ${ws.groups.length} groups.`);
  void router.push({ name: "files", params: { id: ws.id } });
}
</script>

<template>
  <div class="page">
    <PageHeader title="Workspaces">
      <template #lede>
        Hello {{ session.user?.username }}. Each upload becomes a workspace you can convert, edit,
        compare and question.
      </template>
    </PageHeader>

    <UploadDrop @uploaded="opened" />

    <section aria-labelledby="ws-list" class="list">
      <h2 id="ws-list" class="section-title">Your workspaces</h2>

      <div v-if="items === null" class="table-region" aria-busy="true">
        <div v-for="i in 3" :key="i" class="skeleton-row"><span class="skeleton" /></div>
      </div>

      <div v-else-if="items.length === 0" class="empty">
        <FolderOpen aria-hidden="true" />
        <div>
          <p class="strong">No workspaces yet</p>
          <p class="muted">
            Upload an extract above. RET unpacks nested ZIPs, groups files by Oracle module
            (AR, GL, FUN, INV…), converts XML to tables and keeps everything in this workspace.
          </p>
        </div>
      </div>

      <div v-else class="table-region" tabindex="0" role="region" aria-labelledby="ws-list">
        <table class="table">
          <thead>
            <tr>
              <th scope="col">Name</th>
              <th scope="col">Status</th>
              <th scope="col" class="right">Upload</th>
              <th scope="col" class="right">Indexed rows</th>
              <th scope="col">Created</th>
              <th scope="col"><span class="visually-hidden">Open</span></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="ws in items" :key="ws.id">
              <th scope="row" class="name">
                <RouterLink :to="{ name: 'files', params: { id: ws.id } }">{{ ws.name }}</RouterLink>
              </th>
              <td><StatusBadge :status="ws.status" /></td>
              <td class="right num">{{ bytes(ws.upload_bytes) }}</td>
              <td class="right num">{{ ws.indexed_at ? int(ws.indexed_rows) : "—" }}</td>
              <td><time :datetime="ws.created_at" :title="dateTime(ws.created_at)">{{ ago(ws.created_at) }}</time></td>
              <td class="right">
                <RouterLink :to="{ name: ws.status === 'converted' ? 'data' : 'files', params: { id: ws.id } }"
                            class="btn btn-quiet btn-sm" :aria-label="`Open ${ws.name}`">
                  Open <ArrowRight aria-hidden="true" />
                </RouterLink>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>

<style scoped>
.page { display: grid; gap: var(--space-5); padding: var(--space-6); max-width: 1180px; }
.list { display: grid; gap: var(--space-3); }
.section-title { font-size: var(--text-lg); }
.name { font-weight: 600; white-space: normal; min-width: 240px;
  & a { text-decoration: none; } & a:hover { text-decoration: underline; text-decoration-color: var(--gold); } }
.skeleton-row { padding: 14px 12px; border-bottom: 1px solid var(--line); & .skeleton { display: block; height: 14px; width: 60%; } }
.empty {
  display: flex; gap: var(--space-4); padding: var(--space-5); border: 1px solid var(--line);
  border-radius: var(--radius-lg); background: var(--surface); max-width: 70ch;
  & svg { width: 28px; height: 28px; flex: none; color: var(--ink-3); }
  & .strong { font-weight: 650; margin-bottom: 4px; }
}
@media (max-width: 860px) { .page { padding: var(--space-4); } }
</style>
