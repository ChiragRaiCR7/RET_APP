<template>
  <div class="comparison-panel">
    <div class="card-header">
      <div class="card-title-group">
        <h3 class="card-title">📊 Compare Two Inputs (ZIP/XML/CSV → CSV diff)</h3>
        <p class="card-description">Compare results are best-effort for keyless CSVs. Drilldown shows only changed rows/columns side-by-side.</p>
      </div>
    </div>

    <!-- Comparison Options -->
    <div class="comparison-options">
      <label class="toggle-control">
        <input type="checkbox" v-model="options.ignoreCase" class="toggle-input" />
        <span class="toggle-text">Ignore case</span>
      </label>
      <label class="toggle-control">
        <input type="checkbox" v-model="options.trimWhitespace" class="toggle-input" />
        <span class="toggle-text">Trim whitespace</span>
      </label>
      <label class="toggle-control">
        <input type="checkbox" v-model="options.similarityPairing" class="toggle-input" />
        <span class="toggle-text">Similarity pairing (enhanced matching)</span>
      </label>
    </div>

    <!-- Side-by-Side Upload -->
    <div class="sides-grid">
      <!-- Side A -->
      <div class="side-section">
        <h4 class="side-title">Side A</h4>
        <div class="form-group">
          <label class="form-label">Input type A</label>
          <div class="radio-group">
            <label class="radio-label">
              <input type="radio" v-model="sideA.inputType" value="zip" />
              <span>ZIP</span>
            </label>
            <label class="radio-label">
              <input type="radio" v-model="sideA.inputType" value="xml" />
              <span>XML</span>
            </label>
            <label class="radio-label">
              <input type="radio" v-model="sideA.inputType" value="csv" />
              <span>CSV</span>
            </label>
          </div>
        </div>

        <div class="upload-zone-sm">
          <label class="form-label">Upload {{ sideA.inputType.toUpperCase() }} A</label>
          <div 
            class="file-drop-zone"
            :class="{ dragging: sideA.dragging, 'has-file': sideA.file }"
            @dragover.prevent="sideA.dragging = true"
            @dragleave.prevent="sideA.dragging = false"
            @drop.prevent="onDropA"
            @click="$refs.inputA.click()"
          >
            <div v-if="!sideA.file">
              <div class="drop-icon">📁</div>
              <p>Drag and drop file here</p>
              <p class="drop-hint">Limit 200MB per file • {{ sideA.inputType.toUpperCase() }}</p>
            </div>
            <div v-else class="file-info">
              <span class="file-icon">📄</span>
              <span class="file-name">{{ sideA.file.name }}</span>
              <span class="file-size">{{ formatSize(sideA.file.size) }}</span>
              <button class="btn-remove" @click.stop="removeFileA">×</button>
            </div>
            <button class="btn btn-sm btn-secondary browse-btn" @click.stop="$refs.inputA.click()">
              Browse files
            </button>
          </div>
          <input 
            ref="inputA" 
            type="file" 
            @change="onFileA"
            :accept="getAcceptTypes(sideA.inputType)"
            style="display: none"
          />
        </div>
      </div>

      <!-- Side B -->
      <div class="side-section">
        <h4 class="side-title">Side B</h4>
        <div class="form-group">
          <label class="form-label">Input type B</label>
          <div class="radio-group">
            <label class="radio-label">
              <input type="radio" v-model="sideB.inputType" value="zip" />
              <span>ZIP</span>
            </label>
            <label class="radio-label">
              <input type="radio" v-model="sideB.inputType" value="xml" />
              <span>XML</span>
            </label>
            <label class="radio-label">
              <input type="radio" v-model="sideB.inputType" value="csv" />
              <span>CSV</span>
            </label>
          </div>
        </div>

        <div class="upload-zone-sm">
          <label class="form-label">Upload {{ sideB.inputType.toUpperCase() }} B</label>
          <div 
            class="file-drop-zone"
            :class="{ dragging: sideB.dragging, 'has-file': sideB.file }"
            @dragover.prevent="sideB.dragging = true"
            @dragleave.prevent="sideB.dragging = false"
            @drop.prevent="onDropB"
            @click="$refs.inputB.click()"
          >
            <div v-if="!sideB.file">
              <div class="drop-icon">📁</div>
              <p>Drag and drop file here</p>
              <p class="drop-hint">Limit 200MB per file • {{ sideB.inputType.toUpperCase() }}</p>
            </div>
            <div v-else class="file-info">
              <span class="file-icon">📄</span>
              <span class="file-name">{{ sideB.file.name }}</span>
              <span class="file-size">{{ formatSize(sideB.file.size) }}</span>
              <button class="btn-remove" @click.stop="removeFileB">×</button>
            </div>
            <button class="btn btn-sm btn-secondary browse-btn" @click.stop="$refs.inputB.click()">
              Browse files
            </button>
          </div>
          <input 
            ref="inputB" 
            type="file" 
            @change="onFileB"
            :accept="getAcceptTypes(sideB.inputType)"
            style="display: none"
          />
        </div>
      </div>
    </div>

    <!-- Compare Button -->
    <div class="compare-action">
      <button 
        class="btn btn-primary btn-lg compare-btn"
        @click="runComparison"
        :disabled="!canCompare || comparing"
      >
        <span v-if="comparing" class="spinner"></span>
        {{ comparing ? 'Comparing...' : '🔍 Compare Now' }}
      </button>
      <p class="compare-hint">Upload Side A and Side B, then click Compare Now.</p>
    </div>

    <!-- Progress Indicator -->
    <div v-if="comparing" class="progress-section">
      <div class="progress-steps">
        <div class="progress-step" :class="{ active: progressStep >= 1, done: progressStep > 1 }">
          Preparing Side A and B...
        </div>
        <div class="progress-step" :class="{ active: progressStep >= 2, done: progressStep > 2 }">
          Finalizing...
        </div>
        <div class="progress-step" :class="{ active: progressStep >= 3 }">
          Compare complete.
        </div>
      </div>
      <div class="progress-bar">
        <div class="progress-fill" :style="{ width: progressPercent + '%' }"></div>
      </div>
    </div>

    <!-- Results Section -->
    <div v-if="results" class="results-section">
      <!-- Similarity Dashboard -->
      <div class="dashboard-card">
        <h4 class="section-title">📊 Similarity Dashboard (Group+Filename matching)</h4>
        <div class="dashboard-metrics">
          <div class="metric-card large">
            <div class="metric-label">Overall (proxy)</div>
            <div class="metric-value">{{ results.similarity }}%</div>
          </div>
          <div class="metric-card">
            <div class="metric-icon">✅</div>
            <div class="metric-label">Same</div>
            <div class="metric-value">{{ results.same }}</div>
          </div>
          <div class="metric-card">
            <div class="metric-icon">✏️</div>
            <div class="metric-label">Modified</div>
            <div class="metric-value">{{ results.modified }}</div>
          </div>
          <div class="metric-card">
            <div class="metric-icon">➕/🗑️</div>
            <div class="metric-label">Added / Removed</div>
            <div class="metric-value">{{ results.added }}/{{ results.removed }}</div>
          </div>
        </div>
      </div>

      <!-- Collapsible Sections -->
      <details class="collapsible-section">
        <summary>📋 Input details</summary>
        <div class="section-content">
          <p><strong>Side A:</strong> {{ sideA.file?.name }} ({{ formatSize(sideA.file?.size) }})</p>
          <p><strong>Side B:</strong> {{ sideB.file?.name }} ({{ formatSize(sideB.file?.size) }})</p>
        </div>
      </details>

      <details class="collapsible-section">
        <summary>📁 Folder structure changes (logical paths only)</summary>
        <div class="section-content">
          <p v-if="!results.folderChanges?.length">No folder structure changes detected.</p>
          <ul v-else>
            <li v-for="(change, idx) in results.folderChanges" :key="idx">{{ change }}</li>
          </ul>
        </div>
      </details>

      <details class="collapsible-section">
        <summary>📈 Group count deltas (OK only)</summary>
        <div class="section-content">
          <p v-if="!results.groupDeltas?.length">No group count changes.</p>
        </div>
      </details>

      <!-- Change List Table -->
      <div class="change-list-section">
        <h4 class="section-title">📋 Change list</h4>
        <div class="filter-bar">
          <button class="filter-btn" :class="{ active: statusFilter === 'MODIFIED' }" @click="statusFilter = statusFilter === 'MODIFIED' ? '' : 'MODIFIED'">Only MODIFIED</button>
          <button class="filter-btn warning" :class="{ active: statusFilter === 'ADDED_REMOVED' }" @click="statusFilter = statusFilter === 'ADDED_REMOVED' ? '' : 'ADDED_REMOVED'">Only ADDED/REMOVED</button>
          <button class="filter-btn" :class="{ active: statusFilter === '' }" @click="statusFilter = ''">Everything</button>
        </div>

        <div class="status-filters">
          <label class="form-label">Filter status</label>
          <div class="filter-badges">
            <span v-for="status in availableStatuses" :key="status" class="filter-badge" :class="{ active: selectedStatuses.includes(status) }" @click="toggleStatus(status)">{{ status }} ×</span>
          </div>
        </div>

        <div class="search-filter">
          <label class="form-label">Search Group/Filename</label>
          <input v-model="searchQuery" type="text" class="form-input" placeholder="Type to filter..." />
        </div>

        <p class="similarity-note">Cosine similarity is informational. Any SHA mismatch is MODIFIED.</p>

        <div class="data-table-wrapper">
          <table class="data-table">
            <thead>
              <tr>
                <th></th>
                <th>Status</th>
                <th>Group</th>
                <th>Filename</th>
                <th>Similarity%</th>
                <th>Rows_A</th>
                <th>Rows_B</th>
                <th>Cols_A</th>
                <th>Cols_B</th>
                <th>Message</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(change, idx) in filteredChanges" :key="idx">
                <td>{{ idx }}</td>
                <td><span class="status-badge" :class="getStatusBadgeClass(change.status)">{{ change.status }}</span></td>
                <td>{{ change.group }}</td>
                <td>{{ change.filename }}</td>
                <td>{{ change.similarity }}</td>
                <td>{{ change.rows_a }}</td>
                <td>{{ change.rows_b }}</td>
                <td>{{ change.cols_a }}</td>
                <td>{{ change.cols_b }}</td>
                <td>
                  <span v-if="change.status === 'SAME'" class="message-badge success">✅ Content identical (SHA256 match).</span>
                  <span v-else-if="change.status === 'MODIFIED'" class="message-badge warning">❌ Content differs (SHA mismatch).</span>
                  <span v-else>{{ change.message }}</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Drilldown Section -->
      <div class="drilldown-section">
        <h4 class="section-title">🔍 Drilldown: Side-by-side deltas (only changes)</h4>
        <div class="form-group">
          <label class="form-label">Pick a file (Group+Filename)</label>
          <select v-model="drilldownFile" class="form-select" @change="loadDrilldown">
            <option value="">Select a file...</option>
            <option v-for="change in results.changes.filter(c => ['MODIFIED','ADDED','REMOVED'].includes(c.status))" :key="change.filename + change.group" :value="change.filename + '||' + (change.group || '')">
              {{ change.group }} | {{ change.filename }} ({{ change.status }})
            </option>
          </select>
        </div>

        <div v-if="drilldownFile && drilldownData" class="drilldown-content">
          <p class="diff-complexity">Row counts: Side A = {{ drilldownData.sizeA }}, Side B = {{ drilldownData.sizeB }}</p>
          <p class="delta-summary">
            Deltas: 
            <span class="delta-modified">✏️ modified={{ drilldownData.modified }}</span> | 
            <span class="delta-added">➕ added={{ drilldownData.added }}</span> | 
            <span class="delta-removed">🗑️ removed={{ drilldownData.removed }}</span>
          </p>
          <p v-if="drilldownData.truncated" class="truncation-warning">⚠️ Results truncated (too many changes to display)</p>

          <div class="delta-tables">
            <div class="delta-side">
              <h5>🅰️ Side A — only changes</h5>
              <div class="data-table-wrapper">
                <table class="data-table delta-table">
                  <thead>
                    <tr>
                      <th>Kind</th>
                      <th>Row A</th>
                      <th>Row B</th>
                      <th v-for="col in drilldownData.columns" :key="col">{{ col }}</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="(row, idx) in drilldownData.deltaA" :key="idx" :class="getRowClass(row._kind_)">
                      <td><span :class="'kind-badge kind-' + (row._kind_ || '').toLowerCase()">{{ row._kind_ }}</span></td>
                      <td>{{ row._rowA_ }}</td>
                      <td>{{ row._rowB_ }}</td>
                      <td v-for="col in drilldownData.columns" :key="col" :class="getCellClass(row, col, 'A')">
                        <span class="cell-indicator" :class="getCellIndicatorClass(row, col)" title="Change indicator">●</span>
                        {{ row[col] || '' }}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            <div class="delta-side">
              <h5>🅱️ Side B — only changes</h5>
              <div class="data-table-wrapper">
                <table class="data-table delta-table">
                  <thead>
                    <tr>
                      <th>Kind</th>
                      <th>Row A</th>
                      <th>Row B</th>
                      <th v-for="col in drilldownData.columns" :key="col">{{ col }}</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="(row, idx) in drilldownData.deltaB" :key="idx" :class="getRowClass(row._kind_)">
                      <td><span :class="'kind-badge kind-' + (row._kind_ || '').toLowerCase()">{{ row._kind_ }}</span></td>
                      <td>{{ row._rowA_ }}</td>
                      <td>{{ row._rowB_ }}</td>
                      <td v-for="col in drilldownData.columns" :key="col" :class="getCellClass(row, col, 'B')">
                        <span class="cell-indicator" :class="getCellIndicatorClass(row, col)" title="Change indicator">●</span>
                        {{ row[col] || '' }}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import api from '@/utils/api'
import { useToastStore } from '@/stores/toastStore'

const toast = useToastStore()
const emit = defineEmits(['comparison-complete'])

const options = reactive({ ignoreCase: false, trimWhitespace: true, similarityPairing: true })
const sideA = reactive({ inputType: 'zip', file: null, dragging: false })
const sideB = reactive({ inputType: 'zip', file: null, dragging: false })
const comparing = ref(false)
const progressStep = ref(0)
const progressPercent = ref(0)
const results = ref(null)
const statusFilter = ref('')
const selectedStatuses = ref(['MODIFIED', 'SAME'])
const searchQuery = ref('')
const availableStatuses = ['MODIFIED', 'SAME', 'ADDED', 'REMOVED']
const drilldownFile = ref('')
const drilldownData = ref(null)

const canCompare = computed(() => sideA.file && sideB.file)

const filteredChanges = computed(() => {
  if (!results.value?.changes) return []
  let changes = [...results.value.changes]
  if (statusFilter.value === 'MODIFIED') changes = changes.filter(c => c.status === 'MODIFIED')
  else if (statusFilter.value === 'ADDED_REMOVED') changes = changes.filter(c => c.status === 'ADDED' || c.status === 'REMOVED')
  if (selectedStatuses.value.length > 0) changes = changes.filter(c => selectedStatuses.value.includes(c.status))
  if (searchQuery.value) {
    const q = searchQuery.value.toLowerCase()
    changes = changes.filter(c => c.group?.toLowerCase().includes(q) || c.filename?.toLowerCase().includes(q))
  }
  return changes
})

function formatSize(bytes) {
  if (!bytes) return '0 KB'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

function getAcceptTypes(type) {
  const map = { zip: '.zip,application/zip', xml: '.xml,text/xml,application/xml', csv: '.csv,text/csv' }
  return map[type] || '*/*'
}

function onDropA(e) { sideA.dragging = false; if (e.dataTransfer.files.length) sideA.file = e.dataTransfer.files[0] }
function onDropB(e) { sideB.dragging = false; if (e.dataTransfer.files.length) sideB.file = e.dataTransfer.files[0] }
function onFileA(e) { if (e.target.files.length) sideA.file = e.target.files[0] }
function onFileB(e) { if (e.target.files.length) sideB.file = e.target.files[0] }
function removeFileA() { sideA.file = null }
function removeFileB() { sideB.file = null }

async function runComparison() {
  if (!canCompare.value) return
  comparing.value = true
  progressStep.value = 1
  progressPercent.value = 20
  results.value = null
  drilldownFile.value = ''
  drilldownData.value = null
  
  try {
    const formData = new FormData()
    formData.append('sideA', sideA.file)
    formData.append('sideB', sideB.file)
    progressStep.value = 2
    progressPercent.value = 60
    
    const res = await api.post('/comparison/run', formData, { headers: { 'Content-Type': 'multipart/form-data' } })
    progressStep.value = 3
    progressPercent.value = 100
    
    results.value = {
      similarity: res.data.similarity || 0,
      same: res.data.same || 0,
      modified: res.data.modified || 0,
      added: res.data.added || 0,
      removed: res.data.removed || 0,
      changes: res.data.changes || [],
      folderChanges: res.data.folder_changes || [],
      groupDeltas: res.data.group_deltas || []
    }
    emit('comparison-complete', results.value)
    toast.success('Comparison complete!')
  } catch (e) {
    toast.error('Comparison failed: ' + (e.response?.data?.detail || e.message))
  } finally {
    comparing.value = false
  }
}

function toggleStatus(status) {
  const idx = selectedStatuses.value.indexOf(status)
  if (idx >= 0) selectedStatuses.value.splice(idx, 1)
  else selectedStatuses.value.push(status)
}

function getStatusBadgeClass(status) {
  const map = { SAME: 'badge-success', MODIFIED: 'badge-warning', ADDED: 'badge-info', REMOVED: 'badge-error' }
  return map[status] || ''
}

function getRowClass(kind) {
  const map = { MODIFIED: 'row-modified', ADDED: 'row-added', REMOVED: 'row-removed' }
  return map[kind] || ''
}

function getCellClass(row, col, side) {
  const changedCols = row._changed_cols_ || []
  const colIndex = drilldownData.value?.columns?.indexOf(col)
  const isChanged = row._kind_ === 'ADDED' || row._kind_ === 'REMOVED'
    ? true
    : (changedCols.includes(colIndex) || changedCols.includes(col))
  if (isChanged) return side === 'A' ? 'cell-old' : 'cell-new'
  return ''
}

function getCellIndicatorClass(row, col) {
  const changedCols = row._changed_cols_ || []
  const colIndex = drilldownData.value?.columns?.indexOf(col)
  const isChanged = row._kind_ === 'ADDED' || row._kind_ === 'REMOVED'
    ? true
    : (changedCols.includes(colIndex) || changedCols.includes(col))
  return isChanged ? 'indicator-changed' : 'indicator-unchanged'
}

async function loadDrilldown() {
  if (!drilldownFile.value || !results.value) return

  const [filename, group] = drilldownFile.value.split('||')
  const change = results.value.changes.find(c => c.filename === filename && (c.group || '') === (group || ''))
  if (!change) {
    toast.warning('Cannot load drilldown - file not found')
    return
  }

  const hasA = !!change.csv_path_a
  const hasB = !!change.csv_path_b
  if (!hasA && !hasB) {
    toast.warning('Cannot load drilldown - file paths not available')
    return
  }

  try {
    toast.info('Loading drilldown comparison...')

    const params = new URLSearchParams({
      ignore_case: options.ignoreCase.toString(),
      trim_whitespace: options.trimWhitespace.toString(),
      similarity_pairing: options.similarityPairing.toString(),
      sim_threshold: '0.65'
    })

    if (hasA) params.append('csv_path_a', change.csv_path_a)
    if (hasB) params.append('csv_path_b', change.csv_path_b)

    const res = await api.post(`/comparison/drilldown?${params.toString()}`)

    if (res.data.error) {
      toast.error('Drilldown failed: ' + res.data.error)
      return
    }

    const deltaA = res.data.deltaA || {}
    const deltaB = res.data.deltaB || {}
    const stats = res.data.stats || {}
    const header = res.data.header || []

    drilldownData.value = {
      sizeA: res.data.row_count_A || 0,
      sizeB: res.data.row_count_B || 0,
      modified: stats.modified || 0,
      added: stats.added || 0,
      removed: stats.removed || 0,
      columns: header,
      deltaA: deltaA.rows || [],
      deltaB: deltaB.rows || [],
      truncated: res.data.truncated || false,
      header
    }

    toast.success('Drilldown loaded!')
  } catch (e) {
    toast.error('Failed to load drilldown: ' + (e.response?.data?.detail || e.message))
    drilldownData.value = null
  }
}
</script>

<style scoped>
.comparison-panel { padding: 0; }
.comparison-options { display: flex; flex-wrap: wrap; gap: var(--space-lg); align-items: center; padding: var(--space-md); background: var(--surface-base); border-radius: var(--radius-md); margin-bottom: var(--space-lg); }
.toggle-control { display: flex; align-items: center; gap: var(--space-sm); cursor: pointer; }
.toggle-input { width: 40px; height: 20px; appearance: none; background: var(--border-medium); border-radius: 10px; position: relative; cursor: pointer; transition: background 0.2s; }
.toggle-input:checked { background: var(--brand-primary); }
.toggle-input::before { content: ''; position: absolute; width: 16px; height: 16px; border-radius: 50%; background: white; top: 2px; left: 2px; transition: transform 0.2s; }
.toggle-input:checked::before { transform: translateX(20px); }
.threshold-control { display: flex; align-items: center; gap: var(--space-sm); }
.threshold-slider { width: 100px; accent-color: var(--brand-primary); }
.threshold-value { font-weight: 600; color: var(--brand-primary); }
.sides-grid { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-lg); margin-bottom: var(--space-lg); }
.side-section { background: var(--surface-base); border-radius: var(--radius-md); padding: var(--space-lg); }
.side-title { font-size: 1.1rem; font-weight: 700; margin-bottom: var(--space-md); }
.radio-group { display: flex; gap: var(--space-lg); }
.radio-label { display: flex; align-items: center; gap: var(--space-xs); cursor: pointer; }
.file-drop-zone { border: 2px dashed var(--border-medium); border-radius: var(--radius-md); padding: var(--space-lg); text-align: center; cursor: pointer; transition: all 0.2s; min-height: 150px; display: flex; flex-direction: column; align-items: center; justify-content: center; }
.file-drop-zone:hover, .file-drop-zone.dragging { border-color: var(--brand-primary); background: var(--brand-subtle); }
.file-drop-zone.has-file { border-style: solid; border-color: var(--success); }
.drop-icon { font-size: 2rem; margin-bottom: var(--space-sm); }
.drop-hint { font-size: 0.85rem; color: var(--text-tertiary); }
.file-info { display: flex; align-items: center; gap: var(--space-sm); }
.file-icon { font-size: 1.5rem; }
.file-name { font-weight: 600; }
.file-size { color: var(--text-tertiary); font-size: 0.85rem; }
.btn-remove { background: var(--error); color: white; border: none; border-radius: 50%; width: 24px; height: 24px; cursor: pointer; font-size: 1rem; line-height: 1; }
.browse-btn { margin-top: var(--space-sm); }
.compare-action { text-align: center; margin-bottom: var(--space-xl); }
.compare-btn { min-width: 300px; }
.compare-hint { color: var(--text-tertiary); margin-top: var(--space-sm); }
.progress-section { margin-bottom: var(--space-xl); }
.progress-steps { display: flex; flex-direction: column; gap: var(--space-xs); margin-bottom: var(--space-md); }
.progress-step { padding: var(--space-sm); border-radius: var(--radius-sm); background: var(--surface-base); color: var(--text-tertiary); }
.progress-step.active { background: var(--brand-subtle); color: var(--text-body); }
.progress-step.done { color: var(--success); }
.progress-bar { height: 8px; background: var(--surface-base); border-radius: 4px; overflow: hidden; }
.progress-fill { height: 100%; background: linear-gradient(90deg, var(--brand-primary), var(--brand-light)); transition: width 0.3s; }
.results-section { margin-top: var(--space-xl); }
.dashboard-card { background: var(--surface-base); border-radius: var(--radius-md); padding: var(--space-lg); margin-bottom: var(--space-lg); }
.section-title { font-size: 1rem; font-weight: 700; margin-bottom: var(--space-md); }
.dashboard-metrics { display: flex; gap: var(--space-lg); flex-wrap: wrap; }
.metric-card { background: var(--surface-elevated); border: 1px solid var(--border-light); border-radius: var(--radius-md); padding: var(--space-md); text-align: center; min-width: 100px; }
.metric-card.large { min-width: 150px; }
.metric-card .metric-icon { font-size: 1.5rem; }
.metric-card .metric-label { font-size: 0.85rem; color: var(--text-tertiary); }
.metric-card .metric-value { font-size: 1.5rem; font-weight: 700; color: var(--text-heading); }
.collapsible-section { background: var(--surface-base); border-radius: var(--radius-md); margin-bottom: var(--space-md); }
.collapsible-section summary { padding: var(--space-md); cursor: pointer; font-weight: 600; }
.collapsible-section .section-content { padding: 0 var(--space-md) var(--space-md); }
.change-list-section { background: var(--surface-base); border-radius: var(--radius-md); padding: var(--space-lg); margin-bottom: var(--space-lg); }
.filter-bar { display: flex; gap: var(--space-sm); margin-bottom: var(--space-md); }
.filter-btn { padding: 8px 16px; border-radius: var(--radius-full); border: 1px solid var(--border-medium); background: var(--surface-elevated); cursor: pointer; font-weight: 600; transition: all 0.2s; }
.filter-btn:hover { border-color: var(--brand-primary); }
.filter-btn.active { background: var(--brand-primary); color: #000; border-color: var(--brand-primary); }
.filter-btn.warning.active { background: var(--warning); }
.status-filters { margin-bottom: var(--space-md); }
.filter-badges { display: flex; flex-wrap: wrap; gap: var(--space-xs); margin-top: var(--space-xs); }
.filter-badge { display: inline-flex; align-items: center; gap: 4px; padding: 4px 12px; border-radius: var(--radius-full); background: var(--surface-active); font-size: 0.85rem; cursor: pointer; transition: all 0.2s; }
.filter-badge.active { background: var(--brand-primary); color: #000; }
.search-filter { margin-bottom: var(--space-md); }
.search-filter .form-input { max-width: 300px; }
.similarity-note { font-size: 0.85rem; color: var(--text-tertiary); font-style: italic; margin-bottom: var(--space-md); }
.message-badge { display: inline-flex; align-items: center; gap: 4px; font-size: 0.8rem; }
.message-badge.success { color: var(--success); }
.message-badge.warning { color: var(--warning); }
.drilldown-section { background: var(--surface-base); border-radius: var(--radius-md); padding: var(--space-lg); }
.drilldown-content { margin-top: var(--space-lg); }
.diff-complexity { font-size: 0.85rem; color: var(--text-tertiary); }
.delta-summary { font-weight: 600; margin: var(--space-md) 0; }
.delta-tables { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-lg); }
.delta-side h5 { margin-bottom: var(--space-sm); }
.delta-table { font-size: 0.85rem; }
.row-modified { background: var(--warning-bg); }
.row-added { background: var(--success-bg); }
.row-removed { background: var(--error-bg); }
.cell-old { background: #fee2e2; }
.cell-new { background: #d1fae5; }
.cell-indicator { font-size: 0.7rem; margin-right: 4px; }
.indicator-changed { color: #ef4444; }
.indicator-unchanged { color: #22c55e; }
.kind-badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: 600; }
.kind-modified { background: #fef3c7; color: #92400e; }
.kind-added { background: #d1fae5; color: #065f46; }
.kind-removed { background: #fee2e2; color: #991b1b; }
.truncation-warning { color: var(--warning); font-weight: 600; background: var(--warning-bg); padding: var(--space-sm) var(--space-md); border-radius: var(--radius-sm); }
.delta-modified { color: #f59e0b; font-weight: 600; }
.delta-added { color: #10b981; font-weight: 600; }
.delta-removed { color: #ef4444; font-weight: 600; }
.spinner { display: inline-block; width: 16px; height: 16px; border: 2px solid transparent; border-top-color: currentColor; border-radius: 50%; animation: spin 0.8s linear infinite; margin-right: 8px; }
@keyframes spin { to { transform: rotate(360deg); } }
@media (max-width: 768px) { .sides-grid { grid-template-columns: 1fr; } .delta-tables { grid-template-columns: 1fr; } }
</style>
