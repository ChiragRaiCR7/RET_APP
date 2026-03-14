<template>
  <div class="drilldown-page">
    <header class="page-header">
      <div>
        <h2 class="page-title">Comparison Drilldown</h2>
        <p class="page-subtitle">
          {{ fileName || 'Single-file diff view' }}
        </p>
      </div>

      <div class="header-actions">
        <button class="btn btn-secondary" @click="goBack">Back to workspace</button>
        <button class="btn btn-secondary" @click="closeWindow">Close window</button>
      </div>
    </header>

    <div class="hint-line">
      Opened as a separate window for focused review. If close is blocked by browser policy, use “Back to workspace”.
    </div>

    <section v-if="loading" class="state-card">
      <span class="spinner" aria-hidden="true"></span>
      Loading drilldown…
    </section>

    <section v-else-if="error" class="state-card error">
      <div class="state-title">Unable to load drilldown</div>
      <div class="state-text">{{ error }}</div>
    </section>

    <section v-else-if="!isValidRequest" class="state-card">
      <div class="state-title">No drilldown target provided</div>
      <div class="state-text">
        Missing <code>csv_path_a</code> and <code>csv_path_b</code>. Reopen from the Compare tab.
      </div>
    </section>

    <template v-else>
      <section class="stats-grid" v-if="drilldownData">
        <div class="stat-card">
          <div class="k">Rows A</div>
          <div class="v">{{ drilldownData.sizeA }}</div>
        </div>
        <div class="stat-card">
          <div class="k">Rows B</div>
          <div class="v">{{ drilldownData.sizeB }}</div>
        </div>
        <div class="stat-card warn">
          <div class="k">Modified</div>
          <div class="v">{{ drilldownData.modified }}</div>
        </div>
        <div class="stat-card good">
          <div class="k">Added</div>
          <div class="v">{{ drilldownData.added }}</div>
        </div>
        <div class="stat-card bad">
          <div class="k">Removed</div>
          <div class="v">{{ drilldownData.removed }}</div>
        </div>
      </section>

      <p v-if="drilldownData?.truncated" class="warn-text">
        ⚠️ Result is truncated due to large difference volume.
      </p>

      <section
        v-if="visibleDiffColumns.length === 0 || (filteredDeltaA.length === 0 && filteredDeltaB.length === 0)"
        class="state-card"
      >
        <div class="state-title">No meaningful differences</div>
        <div class="state-text">Changes may exist only in ignored WHO columns.</div>
      </section>

      <section v-else class="diff-grid">
        <article class="diff-side">
          <h3 class="side-title">🅰️ ZIP1 (Side A)</h3>
          <div class="table-wrap">
            <table class="data-table" aria-label="Drilldown Side A table">
              <thead>
                <tr>
                  <th class="narrow">Kind</th>
                  <th class="narrow">Row#</th>
                  <th v-for="col in visibleDiffColumns" :key="`a-${col}`">{{ col }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(row, idx) in filteredDeltaA" :key="`a-${idx}`">
                  <td class="narrow"><span class="kind" :class="kindClass(row)">{{ row._kind_ }}</span></td>
                  <td class="narrow">{{ row._rowA_ }}</td>
                  <td
                    v-for="col in visibleDiffColumns"
                    :key="`a-${idx}-${col}`"
                    :class="cellClass(row, col, 'A')"
                  >
                    {{ formatCellValue(row[col]) }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </article>

        <article class="diff-side">
          <h3 class="side-title">🅱️ ZIP2 (Side B)</h3>
          <div class="table-wrap">
            <table class="data-table" aria-label="Drilldown Side B table">
              <thead>
                <tr>
                  <th class="narrow">Kind</th>
                  <th class="narrow">Row#</th>
                  <th v-for="col in visibleDiffColumns" :key="`b-${col}`">{{ col }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(row, idx) in filteredDeltaB" :key="`b-${idx}`">
                  <td class="narrow"><span class="kind" :class="kindClass(row)">{{ row._kind_ }}</span></td>
                  <td class="narrow">{{ row._rowB_ }}</td>
                  <td
                    v-for="col in visibleDiffColumns"
                    :key="`b-${idx}-${col}`"
                    :class="cellClass(row, col, 'B')"
                  >
                    {{ formatCellValue(row[col]) }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </article>
      </section>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { apiCall } from '@/utils/api'

const route = useRoute()
const router = useRouter()

const loading = ref(false)
const error = ref('')
const drilldownData = ref(null)
const changedColumns = ref(new Set())
const requestConfig = ref(null)

const WHO_COLUMNS = [
  'Created By',
  'Last Updated By',
  'Creation Date',
  'Last Update Date',
  'Last Update Login'
]

function parseBool(value, fallback = false) {
  if (value === undefined || value === null || value === '') return fallback
  const s = String(value).toLowerCase().trim()
  return ['1', 'true', 'yes', 'y', 'on'].includes(s)
}

function decodeHashPayload() {
  const hash = String(route.hash || '')
  const match = hash.match(/payload=([^&]+)/)
  if (!match?.[1]) return null

  try {
    const b64 = decodeURIComponent(match[1])
    const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0))
    const json = new TextDecoder().decode(bytes)
    return JSON.parse(json)
  } catch {
    return null
  }
}

function normalizeColName(name) {
  return String(name || '').trim().toLowerCase().replace(/\s+/g, ' ')
}

const ignoredColumns = computed(() => {
  const cols = requestConfig.value?.options?.ignore_columns
  if (Array.isArray(cols) && cols.length) return cols
  return WHO_COLUMNS
})

const ignoredColumnSet = computed(() => new Set((ignoredColumns.value || []).map(normalizeColName)))

function isIgnoredColumn(col) {
  return ignoredColumnSet.value.has(normalizeColName(col))
}

function resolveRequestConfig() {
  const hashPayload = decodeHashPayload() || {}
  const q = route.query || {}

  const optionsFromHash = hashPayload.options || {}

  return {
    filename: String(hashPayload.filename || q.filename || ''),
    csv_path_a: String(hashPayload.csv_path_a || q.csv_path_a || ''),
    csv_path_b: String(hashPayload.csv_path_b || q.csv_path_b || ''),
    options: {
      ignore_case: optionsFromHash.ignore_case ?? parseBool(q.ignore_case, false),
      trim_whitespace: optionsFromHash.trim_whitespace ?? parseBool(q.trim_whitespace, true),
      similarity_pairing: optionsFromHash.similarity_pairing ?? parseBool(q.similarity_pairing, true),
      sim_threshold: String(optionsFromHash.sim_threshold ?? q.sim_threshold ?? '0.65'),
      ignore_columns: Array.isArray(optionsFromHash.ignore_columns) && optionsFromHash.ignore_columns.length
        ? optionsFromHash.ignore_columns
        : WHO_COLUMNS
    }
  }
}

const isValidRequest = computed(() => {
  const cfg = requestConfig.value
  if (!cfg) return false
  return !!cfg.csv_path_a || !!cfg.csv_path_b
})

const fileName = computed(() => {
  const cfg = requestConfig.value
  if (!cfg?.filename) return 'Compared file'
  return cfg.filename
})

const visibleDiffColumns = computed(() => {
  const cols = drilldownData.value?.columns || []
  return cols.filter(c => changedColumns.value.has(c) && !isIgnoredColumn(c))
})

const filteredDeltaA = computed(() => {
  const rows = drilldownData.value?.deltaA || []
  const cols = visibleDiffColumns.value
  if (!cols.length) return []
  return rows.filter(r => cols.some(c => cellHasChange(r, c)))
})

const filteredDeltaB = computed(() => {
  const rows = drilldownData.value?.deltaB || []
  const cols = visibleDiffColumns.value
  if (!cols.length) return []
  return rows.filter(r => cols.some(c => cellHasChange(r, c)))
})

function cellHasChange(row, col) {
  if (isIgnoredColumn(col)) return false
  const idx = drilldownData.value?.columns?.indexOf(col)
  const kind = String(row?._kind_ || '').toUpperCase()

  if (kind === 'ADDED' || kind === 'REMOVED') {
    const v = row?.[col]
    return v !== null && v !== undefined && String(v).trim() !== ''
  }

  const changedCols = row?._changed_cols_ || []
  return changedCols.includes(idx) || changedCols.includes(col)
}

function kindClass(row) {
  const kind = String(row?._kind_ || '').toLowerCase()
  return `kind-${kind}`
}

function cellClass(row, col, side) {
  if (!cellHasChange(row, col)) return ''
  const kind = String(row?._kind_ || '').toUpperCase()
  if (kind === 'REMOVED') return 'cell-old'
  if (kind === 'ADDED') return 'cell-new'
  return side === 'A' ? 'cell-old' : 'cell-new'
}

function formatCellValue(value, maxLen = 90) {
  if (value === null || value === undefined) return ''
  const s = String(value)
  return s.length > maxLen ? `${s.slice(0, maxLen)}…` : s
}

async function loadDrilldown() {
  requestConfig.value = resolveRequestConfig()
  error.value = ''
  drilldownData.value = null
  changedColumns.value = new Set()

  if (!isValidRequest.value) return

  loading.value = true
  try {
    const cfg = requestConfig.value
    const params = new URLSearchParams({
      ignore_case: String(!!cfg.options.ignore_case),
      trim_whitespace: String(!!cfg.options.trim_whitespace),
      similarity_pairing: String(!!cfg.options.similarity_pairing),
      sim_threshold: cfg.options.sim_threshold
    })

    if (cfg.options.ignore_columns?.length) {
      params.append('ignore_columns', cfg.options.ignore_columns.join(','))
    }
    if (cfg.csv_path_a) params.append('csv_path_a', cfg.csv_path_a)
    if (cfg.csv_path_b) params.append('csv_path_b', cfg.csv_path_b)

    const data = await apiCall({
      method: 'post',
      url: `/comparison/drilldown?${params.toString()}`,
      long: false
    })

    if (data?.error) throw new Error(data.error)

    const header = data.header || []
    const deltaA = data.deltaA?.rows || []
    const deltaB = data.deltaB?.rows || []
    const stats = data.stats || {}

    drilldownData.value = {
      sizeA: data.row_count_A || 0,
      sizeB: data.row_count_B || 0,
      modified: stats.modified || 0,
      added: stats.added || 0,
      removed: stats.removed || 0,
      columns: header,
      deltaA,
      deltaB,
      truncated: !!data.truncated
    }

    const set = new Set()
    const allRows = [...deltaA, ...deltaB]

    for (const row of allRows) {
      const changed = row._changed_cols_ || []
      for (const c of changed) {
        if (typeof c === 'number' && header[c]) {
          if (!isIgnoredColumn(header[c])) set.add(header[c])
        } else if (!isIgnoredColumn(c)) {
          set.add(c)
        }
      }

      if (row._kind_ === 'ADDED' || row._kind_ === 'REMOVED') {
        header.forEach((h) => { if (!isIgnoredColumn(h)) set.add(h) })
      }
    }

    changedColumns.value = set
  } catch (e) {
    error.value = e?.response?.data?.detail || e?.message || 'Failed to load drilldown.'
  } finally {
    loading.value = false
  }
}

function goBack() {
  router.push({ name: 'main' })
}

function closeWindow() {
  window.close()
}

watch(
  () => route.fullPath,
  () => {
    loadDrilldown()
  },
  { immediate: true }
)
</script>

<style scoped>
.drilldown-page {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  flex-wrap: wrap;
  padding: 14px;
  border-radius: 14px;
  border: 1px solid var(--border-light);
  background: linear-gradient(145deg, var(--surface-base), var(--surface-elevated));
}

.page-title {
  margin: 0;
  font-weight: 950;
  color: var(--text-heading, var(--text-primary));
}

.page-subtitle {
  margin: 6px 0 0;
  color: var(--text-secondary);
  font-size: 0.92rem;
}

.header-actions {
  display: inline-flex;
  gap: 8px;
  flex-wrap: wrap;
}

.hint-line {
  font-size: 0.86rem;
  color: var(--text-tertiary);
}

.state-card {
  border: 1px solid var(--border-light);
  border-radius: 12px;
  background: var(--surface-base);
  padding: 14px;
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  gap: 10px;
}

.state-card.error {
  border-color: rgba(239, 68, 68, 0.35);
  background: rgba(239, 68, 68, 0.08);
  color: #991b1b;
}

.state-title {
  font-weight: 900;
  color: var(--text-primary);
}

.state-text {
  margin-top: 6px;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(120px, 1fr));
  gap: 10px;
}

@media (max-width: 1000px) {
  .stats-grid { grid-template-columns: 1fr 1fr; }
}

.stat-card {
  border: 1px solid var(--border-light);
  border-radius: 12px;
  background: var(--surface-base);
  padding: 10px 12px;
}

.stat-card .k {
  font-size: 0.8rem;
  color: var(--text-tertiary);
}

.stat-card .v {
  margin-top: 2px;
  font-size: 1.05rem;
  font-weight: 950;
  color: var(--text-primary);
}

.stat-card.warn { border-left: 4px solid #f59e0b; }
.stat-card.good { border-left: 4px solid #22c55e; }
.stat-card.bad { border-left: 4px solid #ef4444; }

.warn-text {
  margin: 0;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid #fed7aa;
  background: #fff7ed;
  color: #9a3412;
  font-weight: 800;
}

.diff-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 12px;
}

@media (max-width: 1100px) {
  .diff-grid { grid-template-columns: 1fr; }
}

.diff-side {
  border: 1px solid var(--border-light);
  border-radius: 12px;
  background: var(--surface-base);
  padding: 10px;
  min-width: 0;
}

.side-title {
  margin: 0 0 8px;
  font-size: 0.95rem;
  font-weight: 900;
}

.table-wrap {
  max-height: 72vh;
  overflow: auto;
  border: 1px solid var(--border-light);
  border-radius: 10px;
  background: var(--surface-elevated);
}

.data-table {
  width: max-content;
  min-width: 100%;
  border-collapse: collapse;
  font-size: 0.86rem;
}

.data-table th,
.data-table td {
  padding: 8px 10px;
  border-bottom: 1px solid var(--border-light);
  white-space: nowrap;
}

.data-table thead th {
  position: sticky;
  top: 0;
  background: var(--surface-base);
  font-weight: 900;
  color: var(--text-primary);
}

.narrow { width: 72px; max-width: 72px; }

.kind {
  display: inline-flex;
  padding: 2px 8px;
  border-radius: 8px;
  font-size: 0.74rem;
  font-weight: 900;
  border: 1px solid transparent;
}

.kind-modified { background: #fef3c7; color: #92400e; border-color: #fde68a; }
.kind-added { background: #d1fae5; color: #065f46; border-color: #a7f3d0; }
.kind-removed { background: #fee2e2; color: #991b1b; border-color: #fecaca; }

.cell-old { background: rgba(239, 68, 68, 0.12); }
.cell-new { background: rgba(34, 197, 94, 0.12); }

.btn {
  border-radius: 10px;
  border: 1px solid var(--border-medium);
  background: var(--surface-elevated);
  color: var(--text-primary);
  padding: 9px 11px;
  font-weight: 900;
  cursor: pointer;
}

.btn-secondary:hover { background: var(--surface-hover); }

.spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid transparent;
  border-top-color: currentColor;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }
</style>
