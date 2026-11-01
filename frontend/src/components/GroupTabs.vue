<script setup lang="ts">
// Module groups as binder index tabs: consultants keep configuration workbooks tabbed by
// Oracle module, so the grouping RET detects is presented the same way. The selected tab
// joins the sheet below it.
import { int } from "@/lib/format";

export type GroupTab = { code: string; name?: string | null; count: number };

defineProps<{ groups: GroupTab[]; total: number; label: string }>();
const selected = defineModel<string | null>({ required: true });
</script>

<template>
  <div class="tabs" role="toolbar" :aria-label="label">
    <button type="button" class="tab" :aria-pressed="selected === null" @click="selected = null">
      <span class="code">All</span>
      <span class="n num">{{ int(total) }}</span>
    </button>
    <button v-for="g in groups" :key="g.code" type="button" class="tab" :aria-pressed="selected === g.code"
            :title="g.name ?? 'Not a standard Oracle module code'" @click="selected = g.code">
      <span class="code">{{ g.code }}</span>
      <span class="n num">{{ int(g.count) }}</span>
      <span class="name">{{ g.name ?? "Custom" }}</span>
    </button>
  </div>
</template>

<style scoped>
.tabs {
  display: flex; gap: 3px; align-items: flex-end; overflow-x: auto; padding: 6px 2px 0;
  border-bottom: 1px solid var(--line-strong); scrollbar-width: thin;
}
.tab {
  position: relative; display: grid; grid-template-columns: auto auto; column-gap: 8px; align-items: baseline;
  min-width: 64px; padding: 7px 12px 6px; margin-bottom: -1px;
  border: 1px solid var(--line-strong); border-bottom-color: transparent; border-radius: 8px 8px 0 0;
  background: var(--sunken); color: var(--ink-2); cursor: pointer; text-align: start;
  font: inherit; transition: background 0.15s, translate 0.15s var(--ease-out);
  &:hover { background: color-mix(in srgb, var(--surface) 60%, var(--sunken)); color: var(--ink); }
  &[aria-pressed="true"] {
    z-index: 1; padding-top: 10px; background: var(--surface); color: var(--ink);
    border-bottom-color: var(--surface);
    &::before {
      content: ""; position: absolute; inset: -1px -1px auto; height: 3px;
      border-radius: 8px 8px 0 0; background: var(--gold);
    }
  }
}
.code { font: 700 var(--text-sm)/1.2 var(--mono); letter-spacing: 0.02em; }
.n { font-size: var(--text-xs); color: var(--ink-3); }
.name {
  grid-column: 1 / -1; max-width: 16ch; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  font-size: var(--text-xs); color: var(--ink-3);
}
</style>
