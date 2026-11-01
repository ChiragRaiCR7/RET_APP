<script setup lang="ts">
import { ChevronLeft, ChevronRight, Download, Eye, EyeOff, Pencil, Plus, Save, Search, Trash2, Undo2 } from "lucide-vue-next";
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";

import { ApiError, get, patch, query, type Dataset, type DatasetPage, type EditIn } from "@/api/client";
import { int, plural } from "@/lib/format";
import { confirm } from "@/state/confirm";
import { fail, notify } from "@/state/toasts";

const props = defineProps<{ dataset: Dataset; focusRow?: number | null }>();
const emit = defineEmits<{ changed: [ds: Dataset] }>();

const LIMIT = 100;
const page = ref<DatasetPage | null>(null);
const loading = ref(false);
const offset = ref(0);
const q = ref("");
const showQuiet = ref(false);
const editing = ref(false);
const pending = ref(new Map<string, { row: number; column: string; value: string }>());
const doomed = ref(new Set<number>());
const draft = ref<Record<string, string> | null>(null);
const active = ref<{ row: number; col: number } | null>(null);
const saving = ref(false);
let ctrl: AbortController | null = null;
let debounce: ReturnType<typeof setTimeout> | undefined;

const header = computed(() => page.value?.columns ?? []);
const visible = computed(() =>
  header.value.map((c, i) => ({ ...c, i })).filter((c) => showQuiet.value || c.kind !== "low"),
);
const quietCount = computed(() => header.value.filter((c) => c.kind === "low").length);
const changes = computed(() => pending.value.size + doomed.value.size + (draft.value ? 1 : 0));

async function load() {
  ctrl?.abort();
  ctrl = new AbortController();
  loading.value = true;
  try {
    page.value = await get<DatasetPage>(
      `/datasets/${props.dataset.id}${query({ offset: offset.value, limit: LIMIT, q: q.value.trim() })}`,
      ctrl.signal,
    );
  } catch (e) {
    if (!(e instanceof DOMException && e.name === "AbortError")) fail(e);
  } finally {
    loading.value = false;
  }
}

function reset() {
  pending.value = new Map();
  doomed.value = new Set();
  draft.value = null;
  active.value = null;
}

watch(() => props.dataset.id, async () => {
  if (changes.value && !(await confirm({ title: "Discard unsaved edits?", body: "You switched datasets with edits that were not saved.", action: "Discard", danger: true }))) return;
  reset();
  editing.value = false;
  q.value = "";
  offset.value = props.focusRow != null ? Math.floor(props.focusRow / LIMIT) * LIMIT : 0;
  await load();
  void scrollToFocus();
}, { immediate: true });

watch(() => props.focusRow, async (row) => {
  if (row == null) return;
  const target = Math.floor(row / LIMIT) * LIMIT;
  if (q.value || target !== offset.value) {
    q.value = "";
    offset.value = target;
    await load();
  }
  void scrollToFocus();
});

async function scrollToFocus() {
  await nextTick();
  document.querySelector(".grid tr.focus")?.scrollIntoView({ block: "center" });
}

watch(q, () => {
  clearTimeout(debounce);
  debounce = setTimeout(() => {
    offset.value = 0;
    void load();
  }, 250);
});
onBeforeUnmount(() => {
  ctrl?.abort();
  clearTimeout(debounce);
});

function go(delta: number) {
  offset.value = Math.max(0, offset.value + delta * LIMIT);
  void load();
}

const key = (row: number, col: string) => `${row}\u0000${col}`;
function cellValue(absRow: number, col: string, raw: string | undefined) {
  return pending.value.get(key(absRow, col))?.value ?? raw ?? "";
}
async function startEdit(rowIdx: number, colIdx: number) {
  if (!editing.value || doomed.value.has(offset.value + rowIdx)) return;
  active.value = { row: rowIdx, col: colIdx };
  await nextTick();
  const el = document.querySelector<HTMLInputElement>(".grid input.cell-input");
  el?.focus();
  el?.select();
}
function commit(rowIdx: number, colIdx: number, value: string) {
  const absRow = offset.value + rowIdx;
  const column = header.value[colIdx]?.name;
  const original = page.value?.rows[rowIdx]?.[colIdx] ?? "";
  if (column === undefined) return;
  const next = new Map(pending.value);
  if (value === original) next.delete(key(absRow, column));
  else next.set(key(absRow, column), { row: absRow, column, value });
  pending.value = next;
  active.value = null;
}
function toggleDelete(rowIdx: number) {
  const abs = offset.value + rowIdx;
  const next = new Set(doomed.value);
  if (next.has(abs)) next.delete(abs);
  else next.add(abs);
  doomed.value = next;
}

async function save() {
  const body: EditIn = {
    cells: [...pending.value.values()],
    append_rows: draft.value ? [Object.fromEntries(Object.entries(draft.value).filter(([, v]) => v !== ""))] : [],
    delete_rows: [...doomed.value],
  };
  saving.value = true;
  try {
    const ds = await patch<Dataset>(`/datasets/${props.dataset.id}`, body);
    notify(`Saved ${plural(changes.value, "change")} to ${ds.name}.`);
    reset();
    editing.value = false;
    emit("changed", ds);
    await load();
  } catch (e) {
    fail(e instanceof ApiError ? e : new Error(String(e)), "Could not save");
  } finally {
    saving.value = false;
  }
}

async function stopEditing() {
  if (changes.value && !(await confirm({ title: "Discard unsaved edits?", body: `${plural(changes.value, "change")} will be lost.`, action: "Discard", danger: true }))) return;
  reset();
  editing.value = false;
}

const from = computed(() => (page.value?.total ? offset.value + 1 : 0));
const to = computed(() => Math.min(offset.value + LIMIT, page.value?.total ?? 0));
const dl = (fmt: string) => `/api/datasets/${props.dataset.id}/download?format=${fmt}`;
</script>

<template>
  <section class="grid-wrap" :aria-label="`${dataset.name} data`">
    <div class="toolbar">
      <label class="search">
        <Search aria-hidden="true" />
        <span class="visually-hidden">Search rows</span>
        <input v-model="q" class="input" type="search" placeholder="Find in rows…" :disabled="editing" />
      </label>
      <button v-if="quietCount" type="button" class="btn btn-sm" :aria-pressed="showQuiet" @click="showQuiet = !showQuiet"
              :title="'Columns that are mostly empty, constant, or simple flags'">
        <component :is="showQuiet ? EyeOff : Eye" aria-hidden="true" />
        {{ showQuiet ? "Hide" : "Show" }} {{ quietCount }} quiet {{ quietCount === 1 ? "column" : "columns" }}
      </button>
      <span class="spacer" />
      <template v-if="!editing">
        <button type="button" class="btn btn-sm" @click="editing = true"><Pencil aria-hidden="true" /> Edit</button>
        <a class="btn btn-sm" :href="dl('csv')" download><Download aria-hidden="true" /> CSV</a>
        <a class="btn btn-sm" :href="dl('xlsx')" download><Download aria-hidden="true" /> Excel</a>
      </template>
      <template v-else>
        <span class="small muted num" role="status">{{ changes ? plural(changes, "unsaved change") : "Click a cell to edit" }}</span>
        <button type="button" class="btn btn-sm" :disabled="!!draft" @click="draft = Object.fromEntries(header.map((c) => [c.name, '']))">
          <Plus aria-hidden="true" /> Add row
        </button>
        <button type="button" class="btn btn-sm btn-quiet" @click="stopEditing"><Undo2 aria-hidden="true" /> Cancel</button>
        <button type="button" class="btn btn-sm btn-primary" :disabled="!changes || saving" :aria-busy="saving" @click="save">
          <Save aria-hidden="true" /> Save
        </button>
      </template>
    </div>

    <div class="table-region grid" :class="{ editing, loading }" tabindex="0" role="region" :aria-label="`Rows of ${dataset.name}`" :aria-busy="loading">
      <table class="table">
        <thead>
          <tr>
            <th scope="col" class="rownum">#</th>
            <th v-for="c in visible" :key="c.i" scope="col" :class="{ quiet: c.kind === 'low' }" :title="c.reason ? `Quiet column: ${c.reason}` : undefined">
              {{ c.name }}
            </th>
            <th v-if="editing" scope="col" class="act"><span class="visually-hidden">Delete</span></th>
          </tr>
        </thead>
        <tbody v-if="page">
          <tr v-for="(row, r) in page.rows" :key="offset + r"
              :class="{ focus: focusRow === offset + r && !q, doomed: doomed.has(offset + r) }">
            <th scope="row" class="rownum num">{{ int(offset + r + 1) }}</th>
            <td v-for="c in visible" :key="c.i" :class="{ dirty: pending.has(`${offset + r}\u0000${c.name}`), quiet: c.kind === 'low' }"
                @click="startEdit(r, c.i)">
              <input v-if="active && active.row === r && active.col === c.i" class="cell-input"
                     :value="cellValue(offset + r, c.name, row[c.i])" :aria-label="`${c.name}, row ${offset + r + 1}`"
                     @keydown.enter="commit(r, c.i, ($event.target as HTMLInputElement).value)"
                     @keydown.esc="active = null" @blur="commit(r, c.i, ($event.target as HTMLInputElement).value)" />
              <button v-else-if="editing" type="button" class="cell-btn" :aria-label="`Edit ${c.name}, row ${offset + r + 1}`">
                {{ cellValue(offset + r, c.name, row[c.i]) }}
              </button>
              <template v-else>{{ row[c.i] }}</template>
            </td>
            <td v-if="editing" class="act">
              <button type="button" class="btn btn-quiet btn-sm btn-icon" :aria-pressed="doomed.has(offset + r)"
                      :aria-label="`${doomed.has(offset + r) ? 'Keep' : 'Delete'} row ${offset + r + 1}`" @click.stop="toggleDelete(r)">
                <component :is="doomed.has(offset + r) ? Undo2 : Trash2" aria-hidden="true" />
              </button>
            </td>
          </tr>
          <tr v-if="draft" class="draft">
            <th scope="row" class="rownum">new</th>
            <td v-for="c in visible" :key="c.i"><input v-model="draft[c.name]" class="cell-input" :aria-label="`New row ${c.name}`" /></td>
            <td class="act"><button type="button" class="btn btn-quiet btn-sm btn-icon" aria-label="Remove new row" @click="draft = null"><Trash2 aria-hidden="true" /></button></td>
          </tr>
          <tr v-if="!page.rows.length && !draft">
            <td :colspan="visible.length + 1" class="subtle">{{ q ? `No rows contain “${q}”.` : "This dataset has no rows." }}</td>
          </tr>
        </tbody>
        <tbody v-else>
          <tr v-for="i in 8" :key="i"><td :colspan="6"><span class="skeleton bar" /></td></tr>
        </tbody>
      </table>
    </div>

    <div class="pager">
      <p class="small muted num" aria-live="polite">
        <template v-if="page">{{ int(from) }}–{{ int(to) }} of {{ plural(page.total, q ? "matching row" : "row") }}</template>
      </p>
      <div class="pg">
        <button type="button" class="btn btn-sm" :disabled="offset === 0 || loading" @click="go(-1)"><ChevronLeft aria-hidden="true" /> Previous</button>
        <button type="button" class="btn btn-sm" :disabled="!page || to >= page.total || loading" @click="go(1)">Next <ChevronRight aria-hidden="true" /></button>
      </div>
    </div>
  </section>
</template>

<style scoped>
.grid-wrap { display: grid; gap: var(--space-3); min-width: 0; }
.toolbar { display: flex; align-items: center; gap: var(--space-2); flex-wrap: wrap; }
.spacer { flex: 1; }
.search { position: relative; flex: 0 1 280px;
  & svg { position: absolute; left: 10px; top: 50%; translate: 0 -50%; width: 15px; height: 15px; color: var(--ink-3); }
  & .input { padding-left: 32px; min-height: 30px; } }
.grid { max-height: 62vh; transition: opacity 0.15s; &.loading { opacity: 0.6; } }
.grid td { max-width: 42ch; overflow: hidden; text-overflow: ellipsis; font-family: var(--mono); font-size: var(--text-xs); }
.grid th.quiet, .grid td.quiet { color: var(--ink-3); }
.rownum { position: sticky; left: 0; z-index: 1; background: var(--raised); color: var(--ink-3); font-weight: 500; text-align: end; width: 1%; }
thead .rownum { z-index: 2; }
.editing td { cursor: text; padding: 0; }
.cell-btn, .cell-input {
  display: block; width: 100%; min-height: 31px; padding: 7px 12px; border: 0; background: none;
  color: inherit; font: inherit; text-align: start; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; cursor: text;
}
.cell-btn:hover { background: var(--gold-wash); }
.cell-input { min-width: 14ch; background: var(--surface); outline: 2px solid var(--ink); outline-offset: -2px; }
td.dirty { background: var(--gold-wash); box-shadow: inset 0 -2px 0 var(--gold); }
tr.doomed > td { text-decoration: line-through; color: var(--ink-3); background: var(--bad-wash); }
tr.focus > * { background: var(--gold-wash); }
tr.draft > * { background: var(--info-wash); }
.act { width: 1%; padding: 2px 6px !important; }
.bar { display: block; height: 12px; }
.pager { display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); flex-wrap: wrap; }
.pg { display: flex; gap: 6px; }
</style>
