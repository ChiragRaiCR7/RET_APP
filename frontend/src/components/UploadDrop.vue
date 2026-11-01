<script setup lang="ts">
import { FileArchive, LoaderCircle, Upload, X } from "lucide-vue-next";
import { computed, ref } from "vue";

import { uploadWorkspace, type WorkspaceDetail } from "@/api/client";
import { bytes } from "@/lib/format";
import { fail } from "@/state/toasts";

const emit = defineEmits<{ uploaded: [ws: WorkspaceDetail] }>();
const ACCEPT = ".zip,.xml,.gz,.csv,.xlsx";

const over = ref(false);
const file = ref<File | null>(null);
const progress = ref(0);
let abort: (() => void) | null = null;

const phase = computed(() =>
  !file.value ? "idle" : progress.value < 1 ? "uploading" : "scanning",
);

async function start(f: File | undefined) {
  if (!f || file.value) return;
  file.value = f;
  progress.value = 0;
  const job = uploadWorkspace(f, (p) => (progress.value = p));
  abort = job.abort;
  try {
    emit("uploaded", await job.promise);
  } catch (e) {
    fail(e, `Could not upload ${f.name}`);
  } finally {
    file.value = null;
    abort = null;
  }
}

function onDrop(e: DragEvent) {
  over.value = false;
  void start(e.dataTransfer?.files[0]);
}

function onPick(e: Event) {
  const input = e.target as HTMLInputElement;
  void start(input.files?.[0]);
  input.value = "";
}
</script>

<template>
  <div
    class="drop"
    :class="{ over, busy: phase !== 'idle' }"
    @dragenter.prevent="over = true"
    @dragover.prevent="over = true"
    @dragleave.self="over = false"
    @drop.prevent="onDrop"
  >
    <template v-if="phase === 'idle'">
      <div class="art" aria-hidden="true"><FileArchive /></div>
      <div class="copy">
        <p class="lead">Drop an Oracle export here</p>
        <p class="subtle small">
          ZIP (nested ZIPs welcome), XML, XML.GZ, CSV or XLSX. Files are grouped by module automatically.
        </p>
      </div>
      <label class="btn btn-primary pick">
        <Upload aria-hidden="true" /> Choose file
        <input type="file" class="visually-hidden" :accept="ACCEPT" @change="onPick" />
      </label>
    </template>
    <template v-else>
      <LoaderCircle class="spin art-spin" aria-hidden="true" />
      <div class="copy" role="status" aria-live="polite">
        <p class="lead">
          {{ phase === "uploading" ? `Uploading ${file?.name}` : `Scanning ${file?.name}` }}
        </p>
        <p class="subtle small num">
          <template v-if="phase === 'uploading'">
            {{ Math.round(progress * 100) }}% of {{ bytes(file?.size ?? 0) }}
          </template>
          <template v-else>Unpacking archives and detecting module groups…</template>
        </p>
        <div class="bar" :class="{ indeterminate: phase === 'scanning' }">
          <span :style="{ inlineSize: `${progress * 100}%` }" />
        </div>
      </div>
      <button v-if="phase === 'uploading'" type="button" class="btn btn-quiet" @click="abort?.()">
        <X aria-hidden="true" /> Cancel
      </button>
    </template>
  </div>
</template>

<style scoped>
.drop {
  display: flex; align-items: center; gap: var(--space-4); padding: var(--space-5);
  border: 1.5px dashed var(--line-strong); border-radius: var(--radius-lg); background: var(--surface);
  transition: border-color 0.15s, background 0.15s;
  &.over { border-color: var(--gold-ink); background: var(--gold-wash); }
  &.busy { border-style: solid; border-color: var(--line); }
}
.art {
  display: grid; place-items: center; width: 52px; height: 52px; flex: none;
  border-radius: var(--radius-lg); background: var(--gold-wash); color: var(--gold-ink);
  & svg { width: 26px; height: 26px; }
}
.art-spin { width: 28px; height: 28px; flex: none; color: var(--gold-ink); margin: 0 12px; }
.copy { flex: 1; min-width: 0; display: grid; gap: 4px; }
.lead { font-weight: 650; font-size: var(--text-lg); overflow-wrap: anywhere; }
.pick { cursor: pointer; }
.pick:has(input:focus-visible) { outline: 2px solid var(--focus); outline-offset: 2px; }
.bar {
  height: 4px; margin-top: 6px; border-radius: 4px; background: var(--sunken); overflow: hidden;
  & span { display: block; height: 100%; background: var(--gold); transition: inline-size 0.2s; }
  &.indeterminate span { inline-size: 35% !important; animation: slide 1.1s var(--ease-out) infinite; }
}
@keyframes slide { from { translate: -100% 0; } to { translate: 300% 0; } }
@media (prefers-reduced-motion: reduce) { .bar.indeterminate span { animation: none; inline-size: 100% !important; } }
@media (max-width: 640px) {
  .drop { flex-wrap: wrap; }
  .pick { width: 100%; }
}
</style>
