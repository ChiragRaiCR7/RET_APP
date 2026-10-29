<script setup lang="ts">
import { CircleAlert, Info } from "lucide-vue-next";
import { computed, ref } from "vue";

import { post } from "@/api/client";
import GroupTabs from "@/components/GroupTabs.vue";
import { bytes, int, plural } from "@/lib/format";
import { fail } from "@/state/toasts";
import { useWorkspace } from "@/state/workspace";

const { ws, reload, convert, converting } = useWorkspace();
const group = ref<string | null>(null);
const saving = ref(false);

const tabs = computed(() =>
  (ws.value?.groups ?? []).map((g) => ({ code: g.code, name: g.module, count: g.files })),
);
const rows = computed(() =>
  (ws.value?.sources ?? []).filter((s) => group.value === null || s.group === group.value),
);
const includedHere = computed(() => rows.value.filter((s) => !s.excluded).length);
const conversionNotes = computed(() => ws.value?.scan_notes.filter((n) => n.startsWith("Conversion failed")) ?? []);
const scanNotes = computed(() => ws.value?.scan_notes.filter((n) => !n.startsWith("Conversion failed")) ?? []);
const activeGroup = computed(() => ws.value?.groups.find((g) => g.code === group.value));

async function setExcluded(ids: string[], excluded: boolean) {
  if (!ws.value || !ids.length) return;
  saving.value = true;
  try {
    await post(`/workspaces/${ws.value.id}/exclusions`, { source_ids: ids, excluded });
    await reload();
  } catch (e) {
    fail(e);
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <div v-if="ws" class="tab">
    <div v-if="conversionNotes.length" class="callout bad" role="alert">
      <CircleAlert aria-hidden="true" />
      <div>
        <p><strong>{{ plural(conversionNotes.length, "file") }} could not be converted.</strong> Other files converted normally.</p>
        <ul class="notes"><li v-for="n in conversionNotes" :key="n" class="mono">{{ n.replace("Conversion failed for ", "") }}</li></ul>
      </div>
    </div>
    <details v-if="scanNotes.length" class="callout warn">
      <summary><CircleAlert aria-hidden="true" class="inline" /> {{ plural(scanNotes.length, "scan note") }}: some entries were skipped</summary>
      <ul class="notes"><li v-for="n in scanNotes" :key="n">{{ n }}</li></ul>
    </details>
    <p v-if="ws.status === 'scanned' && !converting" class="callout">
      <Info aria-hidden="true" />
      <span>Untick anything you don't need, then choose <strong>Convert</strong>. Excluded files are skipped
        and hidden from the results.</span>
    </p>

    <section aria-label="Source files">
      <GroupTabs v-model="group" :groups="tabs" :total="ws.sources.length" label="Filter files by module group" />
      <div class="sheet">
        <div class="bar">
          <p class="small muted num">
            <template v-if="activeGroup">
              <strong class="mono">{{ activeGroup.code }}</strong>
              {{ activeGroup.module ? `· ${activeGroup.module}` : "· custom group" }}
              <template v-if="activeGroup.domain"> · {{ activeGroup.domain }}</template> ·
            </template>
            {{ int(includedHere) }} of {{ plural(rows.length, "file") }} included
          </p>
          <div class="bulk">
            <button class="btn btn-sm" :disabled="saving || !!converting" @click="setExcluded(rows.map((r) => r.id), false)">Include all</button>
            <button class="btn btn-sm" :disabled="saving || !!converting" @click="setExcluded(rows.map((r) => r.id), true)">Exclude all</button>
          </div>
        </div>
        <div class="table-region flat" tabindex="0" role="region" aria-label="Files in this view">
          <table class="table">
            <thead>
              <tr>
                <th scope="col" class="w-check"><span class="visually-hidden">Include</span></th>
                <th scope="col">File</th>
                <th scope="col">Group</th>
                <th scope="col">Type</th>
                <th scope="col" class="right">Size</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="s in rows" :key="s.id" :class="{ off: s.excluded }">
                <td class="w-check">
                  <input type="checkbox" :checked="!s.excluded" :disabled="saving || !!converting"
                         :aria-label="`Include ${s.filename}`" @change="setExcluded([s.id], !($event.target as HTMLInputElement).checked)" />
                </td>
                <th scope="row" class="file">
                  <span class="fname">{{ s.filename }}</span>
                  <span class="path mono">{{ s.logical_path }}</span>
                </th>
                <td class="mono">{{ s.group }}</td>
                <td><span class="badge plain">{{ s.file_type.toUpperCase() }}</span></td>
                <td class="right num">{{ bytes(s.size) }}</td>
              </tr>
              <tr v-if="!rows.length"><td colspan="5" class="subtle">No files in this group.</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>

    <div v-if="ws.status !== 'converted' && !converting && ws.sources.length" class="next">
      <button class="btn btn-primary" :disabled="!ws.sources.some((s) => !s.excluded)" @click="convert()">
        Convert {{ plural(ws.sources.filter((s) => !s.excluded).length, "file") }}
      </button>
      <button v-if="group" class="btn" :disabled="!includedHere" @click="convert([group])">
        Convert only <span class="mono">{{ group }}</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.tab { display: grid; gap: var(--space-4); }
.sheet { background: var(--surface); border: 1px solid var(--line-strong); border-top: 0; border-radius: 0 0 var(--radius-lg) var(--radius-lg); }
.bar { display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); flex-wrap: wrap; padding: 10px 12px; border-bottom: 1px solid var(--line); }
.bulk { display: flex; gap: 6px; }
.flat { border: 0; border-radius: 0 0 var(--radius-lg) var(--radius-lg); max-height: 60vh; }
.w-check { width: 40px; }
.file { display: grid; gap: 2px; white-space: normal; font-weight: 500; min-width: 280px; }
.fname { font-weight: 600; }
.path { font-size: var(--text-xs); color: var(--ink-3); overflow-wrap: anywhere; }
.off > * { color: var(--ink-3); }
.off .fname { text-decoration: line-through; text-decoration-color: var(--line-strong); }
.notes { margin: 6px 0 0; padding-left: 18px; display: grid; gap: 2px; font-size: var(--text-sm); }
details.callout { display: block; & summary { cursor: pointer; font-weight: 600; } }
.inline { width: 16px; height: 16px; vertical-align: -3px; color: var(--warn); }
.next { display: flex; gap: var(--space-2); flex-wrap: wrap; }
</style>
