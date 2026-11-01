<script setup lang="ts">
import { computed } from "vue";

import type { Diff } from "@/api/client";

const props = defineProps<{ diff: Diff }>();
const ignored = computed(() => new Set(props.diff.ignored));
// Show only columns that changed somewhere, plus the first column as an anchor for reading.
const shown = computed(() => {
  const cols = new Set<number>([0]);
  for (const r of props.diff.rows) if (r.kind === "MODIFIED") r.changed.forEach((c) => cols.add(c));
  if (cols.size <= 1) props.diff.header.forEach((_, i) => !ignored.value.has(i) && cols.add(i));
  return [...cols].sort((a, b) => a - b).slice(0, 40);
});
const KIND = { MODIFIED: "Changed", ADDED: "Added", REMOVED: "Removed" } as const;
</script>

<template>
  <div class="table-region" tabindex="0" role="region" aria-label="Row differences">
    <table class="table diff">
      <thead>
        <tr>
          <th scope="col">Change</th>
          <th scope="col" class="right">Row</th>
          <th v-for="c in shown" :key="c" scope="col">{{ diff.header[c] }}</th>
        </tr>
      </thead>
      <tbody>
        <template v-for="(r, i) in diff.rows" :key="i">
          <tr :class="r.kind.toLowerCase()">
            <th scope="row" :rowspan="r.kind === 'MODIFIED' ? 2 : 1"><span class="kind">{{ KIND[r.kind] }}</span></th>
            <td class="right num rn">{{ r.kind === "ADDED" ? `after ${(r.right_row ?? 0) + 1}` : `before ${(r.left_row ?? 0) + 1}` }}</td>
            <td v-for="c in shown" :key="c" :class="{ hot: r.kind === 'MODIFIED' && r.changed.includes(c) }">
              <del v-if="r.kind === 'MODIFIED' && r.changed.includes(c)">{{ r.left?.[c] }}</del>
              <template v-else>{{ (r.left ?? r.right)?.[c] }}</template>
            </td>
          </tr>
          <tr v-if="r.kind === 'MODIFIED'" class="modified after">
            <td class="right num rn">after {{ (r.right_row ?? 0) + 1 }}</td>
            <td v-for="c in shown" :key="c" :class="{ hot: r.changed.includes(c) }">
              <ins v-if="r.changed.includes(c)">{{ r.right?.[c] }}</ins>
              <span v-else class="same">{{ r.right?.[c] }}</span>
            </td>
          </tr>
        </template>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.diff { max-height: 60vh; }
.diff td { font-family: var(--mono); font-size: var(--text-xs); max-width: 36ch; overflow: hidden; text-overflow: ellipsis; }
.rn { color: var(--ink-3); font-family: var(--sans) !important; }
.kind { font-size: var(--text-xs); font-weight: 650; }
tr.added > * { background: var(--info-wash); }
tr.removed > * { background: var(--bad-wash); }
tr.removed td { color: var(--ink-2); }
tr.modified:not(.after) > * { border-bottom-style: dashed; }
td.hot { background: var(--warn-wash); }
del { color: var(--bad); text-decoration-thickness: 1px; }
ins { color: var(--ok); text-decoration: none; font-weight: 650; }
.same { color: var(--ink-3); }
</style>
