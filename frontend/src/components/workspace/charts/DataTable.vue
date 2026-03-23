<template>
  <div class="data-table-wrapper">
    <div v-if="title" class="table-header">
      <h4>{{ title }}</h4>
      <div class="table-actions">
        <button v-if="exportable" @click="exportToCSV" class="btn-export" title="Export to CSV">
          📥 Export
        </button>
        <button v-if="data.length > 10" @click="toggleExpand" class="btn-toggle">
          {{ expanded ? '▲ Collapse' : '▼ Show All' }}
        </button>
      </div>
    </div>
    
    <div class="table-container" :class="{ scrollable: !expanded && data.length > 10 }">
      <table class="data-table" :class="tableClass">
        <thead>
          <tr>
            <th v-for="(col, idx) in columns" :key="idx" @click="sortBy(col.key)" :class="{ sortable: sortable }">
              <span>{{ col.label || col.key }}</span>
              <span v-if="sortable && sortColumn === col.key" class="sort-indicator">
                {{ sortDirection === 'asc' ? '↑' : '↓' }}
              </span>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, rowIdx) in displayedData" :key="rowIdx" :class="{ 'row-alternate': rowIdx % 2 === 1 }">
            <td v-for="(col, colIdx) in columns" :key="colIdx" :class="getCellClass(col, row[col.key])">
              {{ formatCell(row[col.key], col) }}
            </td>
          </tr>
        </tbody>
        <tfoot v-if="showSummary && summary">
          <tr class="summary-row">
            <td v-for="(col, idx) in columns" :key="idx" :class="{ 'summary-cell': true }">
              {{ getSummaryValue(col.key) }}
            </td>
          </tr>
        </tfoot>
      </table>
    </div>
    
    <div v-if="!expanded && data.length > 10" class="table-footer">
      Showing {{ displayedData.length }} of {{ data.length }} rows
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  data: {
    type: Array,
    required: true
  },
  columns: {
    type: Array,
    default: () => []
  },
  title: {
    type: String,
    default: null
  },
  sortable: {
    type: Boolean,
    default: true
  },
  exportable: {
    type: Boolean,
    default: true
  },
  showSummary: {
    type: Boolean,
    default: false
  },
  summary: {
    type: Object,
    default: null
  },
  tableClass: {
    type: String,
    default: ''
  },
  maxRows: {
    type: Number,
    default: 10
  }
})

const expanded = ref(false)
const sortColumn = ref(null)
const sortDirection = ref('asc')

const effectiveColumns = computed(() => {
  if (props.columns.length > 0) {
    return props.columns
  }
  
  // Auto-generate columns from first data row
  if (props.data.length > 0) {
    return Object.keys(props.data[0]).map(key => ({
      key,
      label: formatLabel(key)
    }))
  }
  
  return []
})

const columns = computed(() => effectiveColumns.value)

const sortedData = computed(() => {
  if (!sortColumn.value) return props.data
  
  return [...props.data].sort((a, b) => {
    const aVal = a[sortColumn.value]
    const bVal = b[sortColumn.value]
    
    // Handle null/undefined
    if (aVal == null && bVal == null) return 0
    if (aVal == null) return 1
    if (bVal == null) return -1
    
    // Numeric comparison
    if (typeof aVal === 'number' && typeof bVal === 'number') {
      return sortDirection.value === 'asc' ? aVal - bVal : bVal - aVal
    }
    
    // String comparison
    const aStr = String(aVal).toLowerCase()
    const bStr = String(bVal).toLowerCase()
    
    if (sortDirection.value === 'asc') {
      return aStr < bStr ? -1 : aStr > bStr ? 1 : 0
    } else {
      return aStr > bStr ? -1 : aStr < bStr ? 1 : 0
    }
  })
})

const displayedData = computed(() => {
  if (expanded.value || props.data.length <= props.maxRows) {
    return sortedData.value
  }
  return sortedData.value.slice(0, props.maxRows)
})

function sortBy(columnKey) {
  if (!props.sortable) return
  
  if (sortColumn.value === columnKey) {
    sortDirection.value = sortDirection.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortColumn.value = columnKey
    sortDirection.value = 'asc'
  }
}

function toggleExpand() {
  expanded.value = !expanded.value
}

function formatLabel(key) {
  return key
    .split('_')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

function formatCell(value, column) {
  if (value == null) return '—'

  // Array: show as comma list, truncate long arrays
  if (Array.isArray(value)) {
    if (value.length === 0) return '—'
    const items = value.map(v => (v == null ? '' : String(v).trim())).filter(Boolean)
    if (items.length > 6) return items.slice(0, 6).join(', ') + `… +${items.length - 6}`
    return items.join(', ')
  }

  // Object: key→value pairs, truncated
  if (typeof value === 'object') {
    try {
      const entries = Object.entries(value)
      if (!entries.length) return '—'
      const parts = entries.slice(0, 4).map(([k, v]) => `${k}: ${v}`)
      return parts.join(' · ') + (entries.length > 4 ? '…' : '')
    } catch {
      return '[Object]'
    }
  }

  // Custom formatter
  if (column.formatter && typeof column.formatter === 'function') {
    return column.formatter(value)
  }

  // Number formatting
  if (typeof value === 'number') {
    if (column.type === 'currency') {
      return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(value)
    }
    if (column.type === 'percentage') {
      return (value * 100).toFixed(2) + '%'
    }
    if (column.decimals != null) {
      return value.toFixed(column.decimals)
    }
    return value.toLocaleString()
  }

  // Date formatting
  if (column.type === 'date' && value) {
    const date = new Date(value)
    if (!isNaN(date)) {
      return date.toLocaleDateString()
    }
  }

  return String(value)
}

function getCellClass(column, value) {
  const classes = []
  
  if (column.align) {
    classes.push(`text-${column.align}`)
  }
  
  if (typeof value === 'number') {
    classes.push('cell-numeric')
  }
  
  if (column.type === 'url') {
    classes.push('cell-link')
  }
  
  return classes.join(' ')
}

function getSummaryValue(columnKey) {
  if (!props.summary || !props.summary[columnKey]) {
    return ''
  }
  
  const summaryDef = props.summary[columnKey]
  
  if (typeof summaryDef === 'string') {
    return summaryDef
  }
  
  if (typeof summaryDef === 'function') {
    return summaryDef(props.data)
  }
  
  return summaryDef.value || ''
}

function exportToCSV() {
  const headers = columns.value.map(col => col.label || col.key)
  const rows = props.data.map(row => 
    columns.value.map(col => {
      const value = row[col.key]
      return value != null ? String(value) : ''
    })
  )
  
  const csvContent = [
    headers.join(','),
    ...rows.map(row => row.map(cell => `"${cell.replace(/"/g, '""')}"`).join(','))
  ].join('\n')
  
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `${props.title || 'data'}.csv`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}
</script>

<style scoped>
.data-table-wrapper {
  margin: 1rem 0;
  background: var(--surface-elevated);
  border: 1px solid var(--border-medium);
  border-radius: var(--radius-md, 12px);
  overflow: hidden;
  box-shadow: var(--shadow-sm);
}

.table-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.75rem 1.25rem;
  background: var(--surface-raised);
  border-bottom: 2px solid var(--brand-primary);
}

.table-header h4 {
  margin: 0;
  color: var(--text-heading);
  font-size: var(--text-base, 1rem);
  font-weight: 700;
  font-family: var(--font-display);
}

.table-actions {
  display: flex;
  gap: 0.4rem;
}

.btn-export,
.btn-toggle {
  padding: 0.35rem 0.8rem;
  background: var(--surface-base);
  border: 1px solid var(--border-medium);
  border-radius: var(--radius-sm, 8px);
  color: var(--text-secondary);
  font-size: var(--text-sm, 0.875rem);
  cursor: pointer;
  transition: all var(--transition-fast, 150ms);
}

.btn-export:hover,
.btn-toggle:hover {
  border-color: var(--brand-primary);
  color: var(--text-heading);
  background: var(--brand-subtle);
}

.table-container {
  overflow-x: auto;
  max-height: 600px;
}

.table-container.scrollable {
  max-height: 480px;
  overflow-y: auto;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--text-sm, 0.875rem);
}

.data-table thead {
  position: sticky;
  top: 0;
  background: var(--surface-active);
  z-index: 10;
}

.data-table th {
  padding: 0.7rem 1rem;
  text-align: left;
  font-weight: 700;
  font-size: 0.8rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-heading);
  border-bottom: 2px solid var(--brand-primary);
  white-space: nowrap;
  user-select: none;
}

.data-table th.sortable {
  cursor: pointer;
  transition: background var(--transition-fast, 150ms);
}

.data-table th.sortable:hover {
  background: var(--brand-subtle);
}

.sort-indicator {
  margin-left: 0.4rem;
  color: var(--brand-primary);
  font-size: 0.95em;
}

.data-table td {
  padding: 0.6rem 1rem;
  border-bottom: 1px solid var(--border-light);
  color: var(--text-body);
  /* Critical fix: allow content to wrap instead of one giant no-wrap string */
  white-space: normal;
  word-break: break-word;
  max-width: 360px;
  vertical-align: top;
}

.row-alternate {
  background: var(--brand-subtle-2);
}

.data-table tbody tr:hover td {
  background: var(--brand-subtle);
}

.cell-numeric {
  text-align: right;
  font-variant-numeric: tabular-nums;
  font-family: var(--font-mono);
  font-size: 0.84rem;
}

.cell-link {
  color: var(--link);
  cursor: pointer;
}

.text-left   { text-align: left; }
.text-center { text-align: center; }
.text-right  { text-align: right; }

.summary-row {
  font-weight: 700;
  background: var(--surface-active);
  border-top: 2px solid var(--brand-primary);
}

.summary-cell {
  color: var(--text-heading);
}

.table-footer {
  padding: 0.6rem 1.25rem;
  background: var(--surface-raised);
  border-top: 1px solid var(--border-light);
  color: var(--text-tertiary);
  font-size: var(--text-xs, 0.75rem);
  text-align: center;
}
</style>