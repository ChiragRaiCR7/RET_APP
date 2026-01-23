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

<script setup>
const props = defineProps({
  headers: { type: Array, default: () => [] },
  columns: { type: Array, default: () => [] },
  rows: { type: Array, default: () => [] },
  ariaLabel: { type: String, default: 'Data table' }
})
</script>
