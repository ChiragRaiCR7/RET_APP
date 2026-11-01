<script setup lang="ts">
import { Download, LoaderCircle } from "lucide-vue-next";
import { computed, onMounted, ref } from "vue";

import type { WorkspaceDetail } from "@/api/client";
import { plural } from "@/lib/format";
import { fail, notify } from "@/state/toasts";

const props = defineProps<{ ws: WorkspaceDetail }>();
const emit = defineEmits<{ close: [] }>();
const dlg = ref<HTMLDialogElement | null>(null);
const format = ref<"csv" | "xlsx">("csv");
const preserve = ref(false);
const groups = ref<string[]>([...new Set(props.ws.datasets.map((d) => d.group))].sort());
const picked = ref<Set<string>>(new Set(groups.value));
const busy = ref(false);

const chosen = computed(() => props.ws.datasets.filter((d) => picked.value.has(d.group)));
onMounted(() => dlg.value?.showModal());

function toggle(g: string) {
  const next = new Set(picked.value);
  if (next.has(g)) next.delete(g);
  else next.add(g);
  picked.value = next;
}

async function run() {
  busy.value = true;
  try {
    const res = await fetch(`/api/workspaces/${props.ws.id}/export`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        format: format.value,
        preserve_structure: preserve.value,
        dataset_ids: chosen.value.length === props.ws.datasets.length ? null : chosen.value.map((d) => d.id),
      }),
    });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail ?? `Export failed (${res.status})`);
    const name = /filename\*=UTF-8''([^;]+)/.exec(res.headers.get("content-disposition") ?? "")?.[1];
    const url = URL.createObjectURL(await res.blob());
    const a = Object.assign(document.createElement("a"), { href: url, download: decodeURIComponent(name ?? "export.zip") });
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 10_000);
    notify(`Exported ${plural(chosen.value.length, "dataset")}.`);
    dlg.value?.close();
  } catch (e) {
    fail(e, "Export failed");
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <dialog ref="dlg" class="dialog wide" aria-labelledby="export-title" closedby="any" @close="emit('close')">
    <form class="body" @submit.prevent="run">
      <h2 id="export-title">Export datasets</h2>

      <fieldset>
        <legend class="label">Format</legend>
        <label class="check"><input v-model="format" type="radio" value="csv" /> CSV (UTF-8)</label>
        <label class="check"><input v-model="format" type="radio" value="xlsx" /> Excel workbook (.xlsx)</label>
        <p v-if="format === 'xlsx'" class="hint">Every cell is written as text, so values such as formulas stay inert.</p>
      </fieldset>

      <fieldset>
        <legend class="label">Folder layout in the ZIP</legend>
        <label class="check"><input v-model="preserve" type="radio" :value="false" /> One folder per module group</label>
        <label class="check"><input v-model="preserve" type="radio" :value="true" /> Mirror the original archive paths</label>
      </fieldset>

      <fieldset>
        <legend class="label">Groups</legend>
        <div class="groups">
          <label v-for="g in groups" :key="g" class="chip" :class="{ on: picked.has(g) }">
            <input type="checkbox" :checked="picked.has(g)" @change="toggle(g)" /> <span class="mono">{{ g }}</span>
          </label>
        </div>
      </fieldset>

      <div class="actions">
        <span class="subtle small">{{ plural(chosen.length, "dataset") }}</span>
        <button type="button" class="btn" @click="dlg?.close()">Cancel</button>
        <button class="btn btn-primary" :disabled="!chosen.length || busy" :aria-busy="busy">
          <LoaderCircle v-if="busy" class="spin" aria-hidden="true" /><Download v-else aria-hidden="true" /> Download ZIP
        </button>
      </div>
    </form>
  </dialog>
</template>

<style scoped>
.wide { width: min(520px, calc(100vw - 32px)); }
.body { display: grid; gap: var(--space-4); padding: var(--space-5); }
h2 { font-size: var(--text-lg); }
fieldset { display: grid; gap: 8px; margin: 0; padding: 0; border: 0; }
legend { margin-bottom: 8px; }
.groups { display: flex; flex-wrap: wrap; gap: 6px; }
.chip {
  display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px 4px 8px; border: 1px solid var(--line-strong);
  border-radius: 999px; cursor: pointer; font-size: var(--text-sm);
  &.on { border-color: var(--gold-ink); background: var(--gold-wash); }
  & input { margin: 0; }
}
.actions { display: flex; align-items: center; justify-content: flex-end; gap: var(--space-2); margin-top: var(--space-2);
  & .subtle { margin-right: auto; } }
</style>
