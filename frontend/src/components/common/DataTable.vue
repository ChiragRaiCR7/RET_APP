

<template>
  <div class="data-table-wrapper">
    <table class="data-table" role="table" :aria-label="ariaLabel">
      <thead>
        <tr>
          <th v-for="(h, idx) in headers" :key="idx">{{ h }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(row, rIdx) in rows" :key="rIdx">
          <td v-for="(key, cIdx) in columns" :key="cIdx">{{ row[key] }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
import type { PropType } from 'vue'

defineProps({
  headers: { type: Array as PropType<string[]>, default: () => [] },
  columns: { type: Array as PropType<string[]>, default: () => [] },
  rows: { type: Array as PropType<Record<string, unknown>[]>, default: () => [] },
  ariaLabel: { type: String, default: 'Data table' }
})
</script>
