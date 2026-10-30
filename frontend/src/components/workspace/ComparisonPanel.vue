<template>
  <div class="comparison-panel">
    <!-- Header -->
    <header class="card-header">
      <div class="card-title-group">
        <h3 class="card-title">📦 ZIP/XML/CSV Comparison (ZIP1 vs ZIP2)</h3>
        <p class="card-description">
          Compares files by <strong>same path + same name</strong>, converts XML/CSV → CSV, then compares content.
          UI shows only <strong>file names</strong> (paths hidden). <strong>File list</strong> focuses on record (row) counts.
        </p>
      </div>
    </header>

    <!-- Options -->
    <section class="comparison-options" aria-label="Comparison options">
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
    </section>

    <!-- Upload A/B -->
    <section class="sides-grid" aria-label="Inputs">
      <!-- Side A -->
      <div class="side-section">
        <h4 class="side-title">ZIP 1 (Side A)</h4>

        <div class="form-group">
          <label class="form-label">Input type A</label>
          <div class="radio-group">
            <label class="radio-label"><input type="radio" v-model="sideA.inputType" value="zip" /><span>ZIP</span></label>
            <label class="radio-label"><input type="radio" v-model="sideA.inputType" value="xml" /><span>XML</span></label>
            <label class="radio-label"><input type="radio" v-model="sideA.inputType" value="csv" /><span>CSV</span></label>
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
            @click="inputA?.click()"
            role="button"
            tabindex="0"
          >
            <div v-if="!sideA.file" class="drop-empty">
              <div class="drop-icon">📁</div>
              <p class="drop-title">Drag and drop file here</p>
              <p class="drop-hint">Limit 200MB per file • {{ sideA.inputType.toUpperCase() }}</p>
            </div>

            <div v-else class="file-info">
              <span class="file-icon">📄</span>
              <span class="file-name" :title="sideA.file.name">{{ sideA.file.name }}</span>
              <span class="file-size">{{ formatSize(sideA.file.size) }}</span>
              <button class="btn-remove" @click.stop="removeFileA" aria-label="Remove file A">×</button>
            </div>

            <button class="btn btn-sm btn-secondary browse-btn" @click.stop="inputA?.click()">Browse files</button>
          </div>

          <input ref="inputA" type="file" @change="onFileA" :accept="getAcceptTypes(sideA.inputType)" style="display:none" />
        </div>
      </div>

      <!-- Side B -->
      <div class="side-section">
        <h4 class="side-title">ZIP 2 (Side B)</h4>

        <div class="form-group">
          <label class="form-label">Input type B</label>
          <div class="radio-group">
            <label class="radio-label"><input type="radio" v-model="sideB.inputType" value="zip" /><span>ZIP</span></label>
            <label class="radio-label"><input type="radio" v-model="sideB.inputType" value="xml" /><span>XML</span></label>
            <label class="radio-label"><input type="radio" v-model="sideB.inputType" value="csv" /><span>CSV</span></label>
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
            @click="inputB?.click()"
            role="button"
            tabindex="0"
          >
            <div v-if="!sideB.file" class="drop-empty">
              <div class="drop-icon">📁</div>
              <p class="drop-title">Drag and drop file here</p>
              <p class="drop-hint">Limit 200MB per file • {{ sideB.inputType.toUpperCase() }}</p>
            </div>

            <div v-else class="file-info">
              <span class="file-icon">📄</span>
              <span class="file-name" :title="sideB.file.name">{{ sideB.file.name }}</span>
              <span class="file-size">{{ formatSize(sideB.file.size) }}</span>
              <button class="btn-remove" @click.stop="removeFileB" aria-label="Remove file B">×</button>
            </div>

            <button class="btn btn-sm btn-secondary browse-btn" @click.stop="inputB?.click()">Browse files</button>
          </div>

          <input ref="inputB" type="file" @change="onFileB" :accept="getAcceptTypes(sideB.inputType)" style="display:none" />
        </div>
      </div>
    </section>

    <!-- Compare -->
    <section class="compare-action">
      <button class="btn btn-primary btn-lg compare-btn" @click="runComparison" :disabled="!canCompare || comparing">
        <span v-if="comparing" class="spinner" aria-hidden="true"></span>
        {{ comparing ? "Comparing..." : "🔍 Compare Now" }}
      </button>
      <p class="compare-hint">Upload ZIP1 and ZIP2, then click Compare Now.</p>
    </section>

    <!-- Progress -->
    <section v-if="comparing" class="progress-section" aria-label="Progress">
      <div class="progress-steps">
        <div class="progress-step" :class="{ active: progressStep >= 1, done: progressStep > 1 }">Preparing ZIP1 and ZIP2...</div>
        <div class="progress-step" :class="{ active: progressStep >= 2, done: progressStep > 2 }">Uploading + Creating Job...</div>
        <div class="progress-step" :class="{ active: progressStep >= 3 }">Comparing content (async job)...</div>
      </div>
      <div class="progress-bar" role="progressbar" :aria-valuenow="progressPercent" aria-valuemin="0" aria-valuemax="100">
        <div class="progress-fill" :style="{ width: progressPercent + '%' }"></div>
      </div>
    </section>

    <!-- Results -->
    <section v-if="results" class="results-section" aria-label="Results">
      <div class="dashboard-card">
        <div class="dashboard-header">
          <div>
            <h4 class="section-title">🧾 Discrepancy Summary (Records/Rows)</h4>
            <p class="tiny-note" style="margin: 4px 0 0;">
              Summary is record (row) focused. File-level drilldown remains tabular and column-aware.
            </p>
          </div>

          <button class="btn btn-sm btn-secondary" @click="downloadReport" title="Download comparison report as CSV">
            📥 Download Report
          </button>
        </div>

        <!-- Summary table -->
        <div class="summary-table-wrapper">
          <table class="data-table summary-table" aria-label="Record discrepancy summary table">
            <thead>
              <tr>
                <th>Discrepancy</th>
                <th class="num">Total Records (ZIP 1)</th>
                <th class="num">Total Records (ZIP 2)</th>
                <th class="num">Rows Added (ZIP 2)</th>
                <th class="num">Rows Removed (ZIP 1)</th>
                <th class="num">Rows Modified</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>
                  <button class="dot-btn" :title="recordSummary.hasAnyDiscrepancy ? 'Has record discrepancies' : 'No record discrepancies'">
                    <span class="dot" :class="recordSummary.hasAnyDiscrepancy ? 'dot-red' : 'dot-green'">●</span>
                  </button>
                </td>

                <td class="num">{{ recordSummary.totalRowsA }}</td>
                <td class="num">{{ recordSummary.totalRowsB }}</td>
                <td class="num added">{{ recordSummary.totalAdded }}</td>
                <td class="num removed">{{ recordSummary.totalRemoved }}</td>
                <td class="num modified">{{ recordSummary.totalModified }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <p class="tiny-note">
          ✅ Green dot = No record differences. ❌ Red dot = Rows added/removed/modified exist.
        </p>

        <!-- Filters + Detail Table -->
        <div class="section-header-row" style="margin-top: 14px;">
          <h4 class="section-title">📋 File Details (Records/Rows per file)</h4>

          <div class="right-actions">
            <div class="search-filter-inline">
              <input v-model="searchQuery" type="text" class="form-input" placeholder="Search file name..." />
            </div>

            <div class="chip-row">
              <button class="chip" :class="{ active: statusFilter === '' }" @click="statusFilter = ''">All</button>
              <button class="chip" :class="{ active: statusFilter === 'SAME' }" @click="toggleQuickFilter('SAME')">Same</button>
              <button class="chip warn" :class="{ active: statusFilter === 'MODIFIED' }" @click="toggleQuickFilter('MODIFIED')">Mismatch</button>
            </div>
          </div>
        </div>

        <div class="data-table-wrapper" style="margin-top: 10px;">
          <table class="data-table" aria-label="File record comparison list">
            <thead>
              <tr>
                <th>#</th>
                <th>Status</th>
                <th>File name</th>
                <th>Oracle Module</th>
                <th>Similarity%</th>

                <th class="num">Records (ZIP 1)</th>
                <th class="num">Records (ZIP 2)</th>

                <th class="num">Rows Added (ZIP 2)</th>
                <th class="num">Rows Removed (ZIP 1)</th>
                <th class="num">Rows Modified</th>

                <th>Action</th>
              </tr>
            </thead>

            <tbody>
              <tr v-for="(c, idx) in filteredChanges" :key="idx" class="row-hover">
                <td>{{ idx + 1 }}</td>

                <td>
                  <span class="status-badge" :class="badgeClass(c.status)">{{ c.status }}</span>
                </td>

                <td class="file-cell">
                  <span class="file-name-only" :title="basename(c.filename)">{{ basename(c.filename) }}</span>
                </td>

                <td class="oracle-cell">
                  <span v-if="c.oracle_module_name" class="oracle-module-chip">{{ c.oracle_module_name }}</span>
                  <span
                    v-if="c.oracle_business_domain"
                    class="domain-dot"
                    :title="c.oracle_business_domain"
                    :style="{ background: getDomainColor(c.oracle_business_domain) }"
                  ></span>
                  <span v-if="!c.oracle_module_name" class="muted">—</span>
                </td>

                <td>{{ c.similarity ?? '-' }}</td>

                <td class="num">{{ displayNum(rowCountA(c)) }}</td>
                <td class="num">{{ displayNum(rowCountB(c)) }}</td>

                <td class="num added">{{ displayNum(addedRows(c)) }}</td>
                <td class="num removed">{{ displayNum(removedRows(c)) }}</td>
                <td class="num modified">{{ displayNum(modifiedRows(c)) }}</td>

                <td>
                  <div v-if="c.status === 'MODIFIED'" class="compare-action-cell">
                    <button class="btn btn-sm btn-secondary" @click="openDrilldownWindow(c)" title="Opens drilldown in a new window">
                      Compare Data ↗
                    </button>
                    <span class="muted action-subtle">new window</span>
                  </div>

                  <span v-else-if="c.status === 'SAME'" class="muted">Identical</span>
                  <span v-else-if="c.status === 'REMOVED'" class="muted">Only ZIP1</span>
                  <span v-else-if="c.status === 'ADDED'" class="muted">Only ZIP2</span>
                  <span v-else class="muted">-</span>
                </td>
              </tr>

              <tr v-if="filteredChanges.length === 0">
                <td colspan="10" class="no-data">No files match the filter.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>

    <!-- ===========================
         MODALS (tabular drilldown)
         =========================== -->
    <div v-if="showMismatchModal" class="modal-overlay" @click.self="closeAllModals">
      <div class="modal-card modal-wide">
        <div class="modal-header sticky">
          <div>
            <h4>Data mismatch (MODIFIED files)</h4>
            <p class="modal-subtitle">
              Side-by-side view shows <strong>only changed rows + columns</strong>. WHO columns are ignored.
              Use horizontal + vertical scrollbars; optional sync scroll available.
            </p>
          </div>
          <button class="modal-close" @click="closeAllModals" aria-label="Close modal">×</button>
        </div>

        <div class="modal-body modal-body-fill">
          <div class="modal-toolbar-row">
            <div class="form-group compact">
              <label class="form-label">Select mismatched file</label>
              <select v-model="selectedMismatchKey" class="form-select" @change="onMismatchSelected">
                <option value="">Select a file...</option>
                <option v-for="m in mismatchItems" :key="m.key" :value="m.key">{{ m.name }}</option>
              </select>
            </div>

            <label class="scroll-sync-toggle" title="Sync vertical + horizontal scrolling between Side A and Side B">
              <input type="checkbox" v-model="scrollSyncEnabled" />
              <span>Sync scroll</span>
            </label>
          </div>

          <div class="who-note">
            Ignored WHO columns:
            <code>{{ WHO_COLUMNS.join(', ') }}</code>
          </div>

          <div v-if="diffLoading" class="loading-note" role="status" aria-live="polite">
            <span class="spinner" aria-hidden="true"></span> Loading drilldown diff...
          </div>

          <div v-if="selectedChange && drilldownData" class="drilldown-container">
            <div class="drilldown-topbar">
              <div class="drilldown-title">
                <span class="dot tiny dot-red">●</span>
                <strong :title="basename(selectedChange.filename)">{{ basename(selectedChange.filename) }}</strong>
              </div>
            </div>

            <div class="drilldown-stats">
              <div class="stat"><span class="k">Rows A</span><span class="v">{{ drilldownData.sizeA }}</span></div>
              <div class="stat"><span class="k">Rows B</span><span class="v">{{ drilldownData.sizeB }}</span></div>
              <div class="stat warn"><span class="k">Modified</span><span class="v">{{ drilldownData.modified }}</span></div>
              <div class="stat good"><span class="k">Added</span><span class="v">{{ drilldownData.added }}</span></div>
              <div class="stat bad"><span class="k">Removed</span><span class="v">{{ drilldownData.removed }}</span></div>
            </div>

            <p v-if="drilldownData.truncated" class="truncation-warning">
              ⚠️ Results truncated (too many changes to display)
            </p>

            <div v-if="visibleDiffColumns.length === 0 || (filteredDeltaA.length === 0 && filteredDeltaB.length === 0)" class="empty-diff-block">
              <h5>No meaningful differences after ignoring WHO columns</h5>
              <p>The only detected changes may be in WHO fields, which are excluded from this comparison view.</p>
            </div>

            <div v-else class="delta-tables">
              <!-- A -->
              <div class="delta-side side-a">
                <h5>🅰️ ZIP1 (Side A)</h5>
                <div class="data-table-wrapper scroll-box" ref="scrollContainerA" @scroll="onScrollA">
                  <table class="data-table delta-table" aria-label="Side A diff table">
                    <thead>
                      <tr>
                        <th class="col-narrow sticky-col-1">Kind</th>
                        <th class="col-narrow sticky-col-2">Row#</th>
                        <th v-for="col in visibleDiffColumns" :key="col">{{ col }}</th>
                      </tr>
                    </thead>

                    <tbody>
                      <tr v-for="(row, idx) in filteredDeltaA" :key="idx">
                        <td class="col-narrow sticky-col-1">
                          <span class="kind-badge" :class="'kind-' + (row._kind_ || '').toLowerCase()">{{ row._kind_ }}</span>
                        </td>
                        <td class="col-narrow sticky-col-2">{{ row._rowA_ }}</td>

                        <td
                          v-for="col in visibleDiffColumns"
                          :key="col"
                          :class="[
                            cellClass(row, col, 'A'),
                            { 'clickable-cell': cellHasChange(row, col) }
                          ]"
                          @click="onCellClick(row, col, 'A')"
                          role="button"
                          tabindex="0"
                        >
                          <span
                            v-if="cellHasChange(row, col)"
                            class="cell-dot"
                            :class="cellDotClass(row, col, 'A')"
                            title="Click for details"
                          >
                            ●
                          </span>

                          <span class="cell-value">{{ formatCellValue(row[col]) }}</span>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>

              <!-- B -->
              <div class="delta-side side-b">
                <h5>🅱️ ZIP2 (Side B)</h5>
                <div class="data-table-wrapper scroll-box" ref="scrollContainerB" @scroll="onScrollB">
                  <table class="data-table delta-table" aria-label="Side B diff table">
                    <thead>
                      <tr>
                        <th class="col-narrow sticky-col-1">Kind</th>
                        <th class="col-narrow sticky-col-2">Row#</th>
                        <th v-for="col in visibleDiffColumns" :key="col">{{ col }}</th>
                      </tr>
                    </thead>

                    <tbody>
                      <tr v-for="(row, idx) in filteredDeltaB" :key="idx">
                        <td class="col-narrow sticky-col-1">
                          <span class="kind-badge" :class="'kind-' + (row._kind_ || '').toLowerCase()">{{ row._kind_ }}</span>
                        </td>
                        <td class="col-narrow sticky-col-2">{{ row._rowB_ }}</td>

                        <td
                          v-for="col in visibleDiffColumns"
                          :key="col"
                          :class="[
                            cellClass(row, col, 'B'),
                            { 'clickable-cell': cellHasChange(row, col) }
                          ]"
                          @click="onCellClick(row, col, 'B')"
                          role="button"
                          tabindex="0"
                        >
                          <span
                            v-if="cellHasChange(row, col)"
                            class="cell-dot"
                            :class="cellDotClass(row, col, 'B')"
                            title="Click for details"
                          >
                            ●
                          </span>

                          <span class="cell-value">{{ formatCellValue(row[col]) }}</span>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>

            </div>
          </div>

          <div v-else class="empty-diff">
            <p>Select a mismatched file to view the drilldown diff.</p>
          </div>
        </div>
      </div>
    </div>

    <!-- Cell Detail Modal -->
    <div v-if="showCellModal" class="modal-overlay" @click.self="showCellModal = false">
      <div class="modal-card modal-wide modal-medium">
        <div class="modal-header">
          <div>
            <h4>Cell Change Detail</h4>
            <p class="modal-subtitle">Selected cell difference (A vs B)</p>
          </div>
          <button class="modal-close" @click="showCellModal = false" aria-label="Close modal">×</button>
        </div>

        <div class="modal-body">
          <div class="cell-meta">
            <p><strong>Column:</strong> {{ cellModalData.column }}</p>
            <p><strong>Row A:</strong> {{ cellModalData.rowA }} | <strong>Row B:</strong> {{ cellModalData.rowB }}</p>
            <p>
              <strong>Kind:</strong>
              <span class="kind-badge" :class="'kind-' + (cellModalData.kind || '').toLowerCase()">{{ cellModalData.kind }}</span>
            </p>

            <div class="cell-comparison">
              <div class="cell-side old">
                <h5>🅰️ ZIP1 (A)</h5>
                <div class="cell-content">{{ cellModalData.valueA || '(empty)' }}</div>
              </div>
              <div class="cell-side new">
                <h5>🅱️ ZIP2 (B)</h5>
                <div class="cell-content">{{ cellModalData.valueB || '(empty)' }}</div>
              </div>
            </div>

            <p class="tiny-note" style="margin-top: 10px;">
              Tip: Only changed cells are marked. WHO columns are excluded.
            </p>
          </div>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, reactive, computed, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { errorBody, apiCall, pollJob } from '@/utils/api'
import { useToastStore } from '@/stores/toastStore'
import { getOracleAppName, getOracleBusinessDomain, getDomainColor } from '@/utils/oracleApps'

const toast = useToastStore()
const router = useRouter()
const emit = defineEmits(['comparison-complete'])

/** Inputs */
const options = reactive({ ignoreCase: false, trimWhitespace: true, similarityPairing: true })
const sideA = reactive({ inputType: 'zip', file: null, dragging: false })
const sideB = reactive({ inputType: 'zip', file: null, dragging: false })

/** File input refs */
const inputA = ref(null)
const inputB = ref(null)

/** Run state */
const comparing = ref(false)
const progressStep = ref(0)
const progressPercent = ref(0)
const results = ref(null)

/** Filters */
const searchQuery = ref('')
const statusFilter = ref('') // '', SAME, MODIFIED, ADDED, REMOVED

/** Modals */
const showMismatchModal = ref(false)
const showCellModal = ref(false)

/** Drilldown state */
const selectedMismatchKey = ref('')
const selectedChange = ref(null)
const drilldownData = ref(null)
const changedColumns = ref(new Set())
const diffLoading = ref(false)

/** Scroll sync */
const scrollSyncEnabled = ref(true)
const scrollContainerA = ref(null)
const scrollContainerB = ref(null)

const canCompare = computed(() => !!sideA.file && !!sideB.file)

/** WHO columns ignore handling */
const WHO_COLUMNS = [
  'Created By',
  'Last Updated By',
  'Creation Date',
  'Last Update Date',
  'Last Update Login'
]

function normalizeColName(name) {
  return String(name || '').trim().toLowerCase().replace(/\s+/g, ' ')
}
const WHO_COLUMNS_SET = new Set(WHO_COLUMNS.map(normalizeColName))
function isIgnoredColumn(col) {
  return WHO_COLUMNS_SET.has(normalizeColName(col))
}

/** Helpers */
function basename(p) {
  if (!p) return ''
  const s = String(p).replace(/\\/g, '/')
  const parts = s.split('/')
  return parts[parts.length - 1] || s
}

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

function displayNum(v) {
  return v === null || v === undefined || v === '' ? '-' : v
}

/** Upload handlers */
function onDropA(e) { sideA.dragging = false; if (e.dataTransfer.files?.length) sideA.file = e.dataTransfer.files[0] }
function onDropB(e) { sideB.dragging = false; if (e.dataTransfer.files?.length) sideB.file = e.dataTransfer.files[0] }
function onFileA(e) { if (e.target.files?.length) sideA.file = e.target.files[0] }
function onFileB(e) { if (e.target.files?.length) sideB.file = e.target.files[0] }
function removeFileA() { sideA.file = null }
function removeFileB() { sideB.file = null }

function normalizeChange(c) {
  return { ...c, status: String(c.status || '').toUpperCase() }
}
function keyOf(c) {
  return `${c.group || ''}||${c.filename || ''}`
}

/** ✅ Always-Async Compare: /comparison/run-async -> poll job -> show results */
async function runComparison() {
  if (!canCompare.value) return

  comparing.value = true
  progressStep.value = 1
  progressPercent.value = 10
  results.value = null

  closeAllModals()
  selectedMismatchKey.value = ''
  selectedChange.value = null
  drilldownData.value = null
  changedColumns.value = new Set()

  let ticker = null
  const startTicker = () => {
    if (ticker) return
    ticker = setInterval(() => {
      // Keep moving slowly while polling (cap at 95)
      if (progressPercent.value < 95) progressPercent.value += 1
    }, 1200)
  }
  const stopTicker = () => {
    if (ticker) clearInterval(ticker)
    ticker = null
  }

  try {
    const formData = new FormData()
    formData.append('sideA', sideA.file)
    formData.append('sideB', sideB.file)

    const params = {
      ignore_case: String(!!options.ignoreCase),
      trim_whitespace: String(!!options.trimWhitespace),
      similarity_pairing: String(!!options.similarityPairing),
      sim_threshold: '0.65',
      ignore_columns: WHO_COLUMNS.join(',')
    }

    progressStep.value = 2
    progressPercent.value = 35

    // ✅ Start async job (IMPORTANT: long:true so upload doesn't timeout at 30s)
    const started = await apiCall({
      method: 'post',
      url: '/comparison/run-async',
      data: formData,
      params,
      long: true,
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (evt) => {
        if (!evt || !evt.total) return
        const pct = Math.round((evt.loaded / evt.total) * 25) // 0..25
        progressPercent.value = 35 + pct // 35..60
      }
    })

    const jobId = started?.job_id || started?.jobId || started?.id
    if (!jobId) throw new Error('Async start did not return job_id')

    progressStep.value = 3
    progressPercent.value = Math.max(progressPercent.value, 65)
    startTicker()

    // ✅ Poll until job completes (fast polling)
    const payload = await pollJob(jobId, { intervalMs: 1500, timeoutMs: 60 * 60 * 1000 })
    stopTicker()
    progressPercent.value = 100

    results.value = {
      similarity: payload.similarity || 0,
      same: payload.same || 0,
      modified: payload.modified || 0,
      added: payload.added || 0,
      removed: payload.removed || 0,
      changes: (payload.changes || []).map(normalizeChange)
    }

    // Debug: ensure backend is returning row deltas
    const sample = results.value.changes.find(x => x.status === 'MODIFIED') || results.value.changes[0]
    if (sample) {
      console.debug('[comparison/run-async] sample change:', {
        status: sample.status,
        rows_a: sample.rows_a,
        rows_b: sample.rows_b,
        added_rows: sample.added_rows,
        removed_rows: sample.removed_rows,
        modified_rows: sample.modified_rows,
        csv_path_a: sample.csv_path_a,
        csv_path_b: sample.csv_path_b
      })
    }

    emit('comparison-complete', results.value)
    toast.success('Comparison complete!')

  } catch (e) {
    stopTicker()
    const detail = errorBody(e)?.detail || e?.message || 'Unknown error'
    toast.error('Comparison failed: ' + detail)
    console.error('[comparison/run-async] failed:', e)
  } finally {
    stopTicker()
    comparing.value = false
  }
}

/** ✅ Record-based summary */
const recordSummary = computed(() => {
  const ch = results.value?.changes || []

  const totalRowsA = ch.reduce((sum, x) => sum + (Number(x.rows_a) || 0), 0)
  const totalRowsB = ch.reduce((sum, x) => sum + (Number(x.rows_b) || 0), 0)

  const totalAdded = ch.reduce((sum, x) => sum + (Number(addedRows(x)) || 0), 0)
  const totalRemoved = ch.reduce((sum, x) => sum + (Number(removedRows(x)) || 0), 0)
  const totalModified = ch.reduce((sum, x) => sum + (Number(modifiedRows(x)) || 0), 0)

  return {
    totalRowsA,
    totalRowsB,
    totalAdded,
    totalRemoved,
    totalModified,
    hasAnyDiscrepancy: (totalAdded + totalRemoved + totalModified) > 0
  }
})

/** Per-file totals & deltas */
function rowCountA(c) { return Number(c.rows_a ?? 0) }
function rowCountB(c) { return Number(c.rows_b ?? 0) }

function addedRows(c) {
  const s = String(c.status || '').toUpperCase()
  if (c.added_rows !== undefined && c.added_rows !== null) return Number(c.added_rows)
  if (s === 'ADDED') return rowCountB(c)
  return 0
}
function removedRows(c) {
  const s = String(c.status || '').toUpperCase()
  if (c.removed_rows !== undefined && c.removed_rows !== null) return Number(c.removed_rows)
  if (s === 'REMOVED') return rowCountA(c)
  return 0
}
function modifiedRows(c) {
  if (c.modified_rows !== undefined && c.modified_rows !== null) return Number(c.modified_rows)
  return 0
}

/** Filter changes */
const filteredChanges = computed(() => {
  let ch = [...(results.value?.changes || [])]
  if (statusFilter.value) ch = ch.filter(x => x.status === statusFilter.value)
  if (searchQuery.value) {
    const q = searchQuery.value.toLowerCase()
    ch = ch.filter(x => basename(x.filename).toLowerCase().includes(q))
  }
  const rank = { MODIFIED: 1, ADDED: 2, REMOVED: 2, SAME: 3 }
  ch.sort((a, b) => (rank[a.status] || 99) - (rank[b.status] || 99) || basename(a.filename).localeCompare(basename(b.filename)))
  return ch
})

function toggleQuickFilter(s) {
  statusFilter.value = statusFilter.value === s ? '' : s
}

/** Close modals */
function closeAllModals() {
  showMismatchModal.value = false
  showCellModal.value = false
}

/** Badge + dot */
function badgeClass(status) {
  const s = String(status || '').toUpperCase()
  return s === 'SAME' ? 'badge-success'
    : s === 'MODIFIED' ? 'badge-warning'
    : s === 'ADDED' ? 'badge-info'
    : s === 'REMOVED' ? 'badge-error'
    : ''
}
function statusDotClass(status) {
  const s = String(status || '').toUpperCase()
  if (s === 'SAME') return 'dot-green'
  if (s === 'MODIFIED') return 'dot-red'
  if (s === 'REMOVED') return 'dot-red'
  if (s === 'ADDED') return 'dot-green'
  return 'dot-gray'
}

/** Download report */
function downloadReport() {
  if (!results.value?.changes) return

  const headers = [
    'Status', 'Filename', 'Similarity%',
    'Rows_A', 'Rows_B',
    'Added_Rows', 'Removed_Rows', 'Modified_Rows'
  ]

  const rows = results.value.changes.map(c => [
    c.status,
    basename(c.filename || ''),
    c.similarity ?? '',
    c.rows_a ?? '',
    c.rows_b ?? '',
    addedRows(c),
    removedRows(c),
    modifiedRows(c)
  ])

  const csvContent = [
    `# ZIP Comparison Report (Record/Row focused) - ${new Date().toISOString()}`,
    `# Side A: ${sideA.file?.name || 'N/A'}`,
    `# Side B: ${sideB.file?.name || 'N/A'}`,
    '',
    headers.join(','),
    ...rows.map(r => r.map(v => `"${String(v).replace(/"/g, '""')}"`).join(',')),
  ].join('\n')

  const blob = new Blob([csvContent], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `zip-comparison-records-${new Date().toISOString().slice(0, 10)}.csv`
  a.click()
  URL.revokeObjectURL(url)
  toast.success('Report downloaded')
}

/** ===== Drilldown ===== */
const mismatchItems = computed(() => {
  return (results.value?.changes || [])
    .filter(x => String(x.status || '').toUpperCase() === 'MODIFIED')
    .map(x => ({ key: keyOf(x), name: basename(x.filename), change: x }))
    .sort((a, b) => a.name.localeCompare(b.name))
})

function encodePayloadToBase64(payload) {
  const text = JSON.stringify(payload || {})
  const bytes = new TextEncoder().encode(text)
  let bin = ''
  bytes.forEach((b) => { bin += String.fromCharCode(b) })
  return btoa(bin)
}

function buildDrilldownHref(change) {
  const payload = {
    filename: change?.filename || '',
    csv_path_a: change?.csv_path_a || '',
    csv_path_b: change?.csv_path_b || '',
    options: {
      ignore_case: !!options.ignoreCase,
      trim_whitespace: !!options.trimWhitespace,
      similarity_pairing: !!options.similarityPairing,
      sim_threshold: '0.65',
      ignore_columns: [...WHO_COLUMNS]
    }
  }

  const resolved = router.resolve({
    name: 'compare-drilldown',
    query: {
      filename: basename(change?.filename || ''),
      csv_path_a: payload.csv_path_a || undefined,
      csv_path_b: payload.csv_path_b || undefined,
      ignore_case: String(payload.options.ignore_case),
      trim_whitespace: String(payload.options.trim_whitespace),
      similarity_pairing: String(payload.options.similarity_pairing),
      sim_threshold: payload.options.sim_threshold
    }
  })

  const encoded = encodePayloadToBase64(payload)
  return `${resolved.href}#payload=${encodeURIComponent(encoded)}`
}

async function openDrilldownWindow(change) {
  if (!change) return
  const targetHref = buildDrilldownHref(change)
  const opened = window.open(targetHref, '_blank', 'noopener,noreferrer')

  if (!opened) {
    toast.warning('Popup blocked. Opening drilldown in modal instead.')
    await openDiffModal(change)
    return
  }

  opened.focus?.()
}

async function openDiffModal(change) {
  if (!change) return
  showMismatchModal.value = true
  selectedMismatchKey.value = keyOf(change)
  await nextTick()
  await loadDrilldown(change)
}

async function onMismatchSelected() {
  const item = mismatchItems.value.find(m => m.key === selectedMismatchKey.value)
  if (!item) return
  await loadDrilldown(item.change)
}

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

async function loadDrilldown(change) {
  const hasA = !!change.csv_path_a
  const hasB = !!change.csv_path_b
  if (!hasA && !hasB) {
    toast.warning('Cannot load drilldown: CSV paths not provided by backend')
    return
  }

  selectedChange.value = change
  drilldownData.value = null
  changedColumns.value = new Set()
  diffLoading.value = true

  try {
    const params = new URLSearchParams({
      ignore_case: options.ignoreCase.toString(),
      trim_whitespace: options.trimWhitespace.toString(),
      similarity_pairing: options.similarityPairing.toString(),
      sim_threshold: '0.65'
    })
    params.append('ignore_columns', WHO_COLUMNS.join(','))

    if (hasA) params.append('csv_path_a', change.csv_path_a)
    if (hasB) params.append('csv_path_b', change.csv_path_b)

    const data = await apiCall({
      method: 'post',
      url: `/comparison/drilldown?${params.toString()}`,
      long: false
    })

    if (data?.error) {
      toast.error('Drilldown failed: ' + data.error)
      return
    }

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

    // compute changed columns excluding WHO
    const set = new Set()
    const allRows = [...deltaA, ...deltaB]
    for (const row of allRows) {
      const changed = row._changed_cols_ || []
      for (const c of changed) {
        if (typeof c === 'number' && header[c]) {
          if (!isIgnoredColumn(header[c])) set.add(header[c])
        } else {
          if (!isIgnoredColumn(c)) set.add(c)
        }
      }
      if (row._kind_ === 'ADDED' || row._kind_ === 'REMOVED') {
        header.forEach(h => { if (!isIgnoredColumn(h)) set.add(h) })
      }
    }

    changedColumns.value = set
    toast.success('Drilldown loaded!')
  } catch (e) {
    toast.error('Failed to load drilldown: ' + (errorBody(e)?.detail || e.message))
  } finally {
    diffLoading.value = false
  }
}

/**
 * Cell change detection
 */
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

function cellClass(row, col, side) {
  if (!cellHasChange(row, col)) return ''
  const kind = String(row?._kind_ || '').toUpperCase()
  if (kind === 'REMOVED') return 'cell-old'
  if (kind === 'ADDED') return 'cell-new'
  return side === 'A' ? 'cell-old' : 'cell-new'
}

function cellDotClass(row, col, side) {
  const kind = String(row?._kind_ || '').toUpperCase()
  if (kind === 'REMOVED') return 'dot-red'
  if (kind === 'ADDED') return 'dot-green'
  return side === 'A' ? 'dot-red' : 'dot-green'
}

function formatCellValue(value, maxLen = 40) {
  if (value === null || value === undefined) return ''
  const str = String(value)
  return str.length > maxLen ? str.slice(0, maxLen) + '…' : str
}

/** Cell detail modal */
const cellModalData = ref({ column: '', valueA: '', valueB: '', rowA: '', rowB: '', kind: '' })
function onCellClick(row, col, side) {
  if (!cellHasChange(row, col)) return
  showCellDetail(row, col, side)
}

function showCellDetail(row, col, side) {
  const aRows = drilldownData.value?.deltaA || []
  const bRows = drilldownData.value?.deltaB || []
  let rowA = null
  let rowB = null

  if (side === 'A') {
    rowA = row
    rowB = bRows.find(r => r._rowB_ === row._rowB_ || r._rowA_ === row._rowA_)
  } else {
    rowB = row
    rowA = aRows.find(r => r._rowA_ === row._rowA_ || r._rowB_ === row._rowB_)
  }

  cellModalData.value = {
    column: col,
    valueA: rowA ? rowA[col] : '(not found)',
    valueB: rowB ? rowB[col] : '(not found)',
    rowA: rowA?._rowA_ ?? '-',
    rowB: rowB?._rowB_ ?? '-',
    kind: row?._kind_ || 'MODIFIED'
  }

  showCellModal.value = true
}

/** Scroll sync */
let syncingDrilldown = false
function onScrollA(e) {
  if (!scrollSyncEnabled.value || !scrollContainerB.value) return
  if (syncingDrilldown) return
  syncingDrilldown = true
  requestAnimationFrame(() => {
    scrollContainerB.value.scrollTop = e.target.scrollTop
    scrollContainerB.value.scrollLeft = e.target.scrollLeft
    syncingDrilldown = false
  })
}
function onScrollB(e) {
  if (!scrollSyncEnabled.value || !scrollContainerA.value) return
  if (syncingDrilldown) return
  syncingDrilldown = true
  requestAnimationFrame(() => {
    scrollContainerA.value.scrollTop = e.target.scrollTop
    scrollContainerA.value.scrollLeft = e.target.scrollLeft
    syncingDrilldown = false
  })
}
</script>

<style scoped>
/* =========================
   Enterprise polish baseline
   ========================= */
.comparison-panel { padding: 0; }

/* Header */
.card-header { margin-bottom: var(--space-md); }
.card-title { margin: 0; font-weight: 800; letter-spacing: -0.2px; }
.card-description { color: var(--text-tertiary); margin: 6px 0 0; line-height: 1.35; }

/* Options */
.comparison-options {
  display: flex; flex-wrap: wrap; gap: var(--space-lg);
  align-items: center; padding: var(--space-md);
  background: var(--surface-base);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  margin-bottom: var(--space-lg);
}
.toggle-control { display: inline-flex; align-items: center; gap: var(--space-sm); cursor: pointer; user-select: none; }
.toggle-text { font-weight: 700; color: var(--text-secondary); }

.toggle-input {
  width: 40px; height: 20px;
  appearance: none;
  background: var(--border-medium);
  border-radius: 10px;
  position: relative;
  cursor: pointer;
  outline: none;
  transition: background .2s;
}
.toggle-input:checked { background: var(--brand-primary); }
.toggle-input::before {
  content: '';
  position: absolute;
  width: 16px; height: 16px;
  border-radius: 50%;
  background: #fff;
  top: 2px; left: 2px;
  transition: transform .2s;
}
.toggle-input:checked::before { transform: translateX(20px); }
.toggle-input:focus-visible { box-shadow: 0 0 0 3px rgba(59, 130, 246, .35); }

/* Upload panels */
.sides-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-lg);
  margin-bottom: var(--space-lg);
}
.side-section {
  background: var(--surface-base);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  padding: var(--space-lg);
}
.side-title { font-size: 1.05rem; font-weight: 900; margin-bottom: var(--space-md); }

.form-group { margin-bottom: var(--space-md); }
.form-label { display: block; font-weight: 800; margin-bottom: 6px; color: var(--text-secondary); }
.form-input, .form-select {
  width: 100%;
  padding: 10px 12px;
  border-radius: var(--radius-md);
  border: 1px solid var(--border-light);
  background: var(--surface-elevated);
  outline: none;
}
.form-input:focus-visible, .form-select:focus-visible {
  box-shadow: 0 0 0 3px rgba(59, 130, 246, .25);
  border-color: rgba(59, 130, 246, .6);
}

.radio-group { display: flex; gap: var(--space-lg); flex-wrap: wrap; }
.radio-label { display: inline-flex; align-items: center; gap: var(--space-xs); cursor: pointer; }
.radio-label input { accent-color: var(--brand-primary); }

/* Drop zone */
.file-drop-zone {
  border: 2px dashed var(--border-medium);
  border-radius: var(--radius-md);
  padding: var(--space-lg);
  text-align: center;
  cursor: pointer;
  transition: all .2s;
  min-height: 160px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: var(--surface-base);
}
.file-drop-zone:hover,
.file-drop-zone.dragging {
  border-color: var(--brand-primary);
  background: var(--brand-subtle);
}
.file-drop-zone.has-file {
  border-style: solid;
  border-color: var(--success);
  background: linear-gradient(to bottom, rgba(34,197,94,.08), transparent);
}
.drop-empty .drop-title { font-weight: 800; margin: 6px 0 0; }
.drop-icon { font-size: 2rem; margin-bottom: var(--space-sm); }
.drop-hint { font-size: .85rem; color: var(--text-tertiary); margin-top: 4px; }

.file-info { display: flex; align-items: center; gap: var(--space-sm); flex-wrap: wrap; justify-content: center; }
.file-icon { font-size: 1.3rem; }
.file-name { font-weight: 800; max-width: 260px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.file-size { color: var(--text-tertiary); font-size: .85rem; }

.btn-remove {
  background: var(--error);
  color: #fff;
  border: none;
  border-radius: 999px;
  width: 28px;
  height: 28px;
  cursor: pointer;
  font-size: 1.2rem;
  line-height: 1;
}
.btn-remove:hover { filter: brightness(0.95); }
.browse-btn { margin-top: var(--space-sm); }

/* Buttons */
.btn { border: 1px solid var(--border-light); border-radius: var(--radius-md); padding: 10px 14px; font-weight: 900; cursor: pointer; }
.btn:disabled { opacity: .6; cursor: not-allowed; }
.btn-primary { background: var(--brand-primary); color: #111; border-color: var(--brand-primary); }
.btn-secondary { background: var(--surface-elevated); }
.btn-lg { padding: 12px 18px; }
.btn-sm { padding: 7px 10px; font-size: .85rem; border-radius: 10px; }
.btn:hover:not(:disabled) { filter: brightness(0.98); }
.btn:focus-visible { box-shadow: 0 0 0 3px rgba(59, 130, 246, .25); }

/* Compare action */
.compare-action { text-align: center; margin-bottom: var(--space-xl); }
.compare-btn { min-width: 280px; }
.compare-hint { color: var(--text-tertiary); margin-top: var(--space-sm); }

/* Progress */
.progress-section { margin-bottom: var(--space-xl); }
.progress-steps { display: flex; flex-direction: column; gap: var(--space-xs); margin-bottom: var(--space-md); }
.progress-step { padding: var(--space-sm); border-radius: var(--radius-sm); background: var(--surface-base); color: var(--text-tertiary); border: 1px solid var(--border-light); }
.progress-step.active { background: var(--brand-subtle); color: var(--text-body); border-color: rgba(59, 130, 246, .2); }
.progress-step.done { color: var(--success); }
.progress-bar { height: 8px; background: var(--surface-base); border-radius: 4px; overflow: hidden; border: 1px solid var(--border-light); }
.progress-fill { height: 100%; background: linear-gradient(90deg, var(--brand-primary), var(--brand-light)); transition: width .3s; }

/* Cards */
.results-section { margin-top: var(--space-xl); }
.dashboard-card {
  background: var(--surface-base);
  border-radius: var(--radius-md);
  padding: var(--space-lg);
  margin-bottom: var(--space-lg);
  border: 1px solid var(--border-light);
}
.dashboard-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: var(--space-md); gap: var(--space-md); flex-wrap: wrap; }
.section-title { font-size: 1rem; font-weight: 900; margin: 0; }

.summary-table-wrapper { overflow-x: auto; }
.tiny-note { margin-top: 10px; font-size: .85rem; color: var(--text-tertiary); }

/* Dots */
.dot-btn { background: transparent; border: none; cursor: default; padding: 0; }
.dot { font-size: 1.35rem; line-height: 1; }
.dot.tiny { font-size: 1rem; }
.dot-green { color: #22c55e; }
.dot-red { color: #ef4444; }
.dot-gray { color: #9ca3af; }

/* Toolbar rows */
.section-header-row { display: flex; justify-content: space-between; align-items: flex-start; gap: var(--space-md); flex-wrap: wrap; margin-top: 8px; }
.right-actions { display: flex; gap: var(--space-md); align-items: center; flex-wrap: wrap; }
.search-filter-inline .form-input { min-width: 240px; }

.chip-row { display: flex; gap: 8px; flex-wrap: wrap; }
.chip {
  border: 1px solid var(--border-medium);
  padding: 6px 10px;
  border-radius: 999px;
  font-weight: 800;
  background: var(--surface-elevated);
  cursor: pointer;
}
.chip.active { background: var(--brand-primary); border-color: var(--brand-primary); color: #000; }
.chip.warn.active { background: #f59e0b; border-color: #f59e0b; color: #111; }
.chip.danger.active { background: #ef4444; border-color: #ef4444; color: #fff; }
.chip.info.active { background: #10b981; border-color: #10b981; color: #111; }

/* Tables */
.data-table-wrapper { overflow-x: auto; }
.data-table { width: 100%; border-collapse: collapse; }
.data-table th, .data-table td {
  padding: 10px;
  border-bottom: 1px solid var(--border-light);
  vertical-align: top;
}
.data-table thead th {
  background: var(--surface-base);
  color: var(--text-secondary);
  font-weight: 900;
  position: sticky;
  top: 0;
  z-index: 1;
}
.row-hover:hover { background: rgba(59, 130, 246, .04); }

.file-cell { max-width: 320px; }
.file-name-only { font-weight: 900; max-width: 320px; display: inline-block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.muted { color: var(--text-tertiary); }

.oracle-cell { white-space: nowrap; }
.oracle-module-chip { font-size: 0.78rem; font-weight: 600; color: var(--text-primary); margin-right: 4px; }
.domain-dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; vertical-align: middle; }
.no-data { text-align: center; color: var(--text-tertiary); font-style: italic; padding: 18px; }

.compare-action-cell {
  display: inline-flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
}

.action-subtle {
  font-size: 0.75rem;
}

/* numeric styling */
.num { text-align: right; font-variant-numeric: tabular-nums; font-weight: 900; }
.num.added { color: #16a34a; }
.num.removed { color: #dc2626; }
.num.modified { color: #d97706; }

/* Status badges */
.status-badge {
  padding: 4px 10px;
  border-radius: 999px;
  font-weight: 900;
  font-size: .75rem;
  display: inline-block;
  border: 1px solid transparent;
}
.badge-success { background: #dcfce7; color: #166534; border-color: #bbf7d0; }
.badge-warning { background: #fef3c7; color: #92400e; border-color: #fde68a; }
.badge-info { background: #d1fae5; color: #065f46; border-color: #a7f3d0; }
.badge-error { background: #fee2e2; color: #991b1b; border-color: #fecaca; }

/* Modals */
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,.6); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.modal-card {
  background: var(--surface-elevated);
  border-radius: var(--radius-lg);
  width: 92%;
  max-width: 900px;
  box-shadow: var(--shadow-heavy);
  overflow: hidden;
  border: 1px solid rgba(255,255,255,.06);
}
.modal-card.modal-wide {
  width: 98vw;
  height: 94vh;
  max-width: 1800px;
  display: flex;
  flex-direction: column;
}
.modal-card.modal-medium { max-width: 1200px; }

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-md) var(--space-lg);
  background: var(--surface-base);
  border-bottom: 1px solid var(--border-light);
}
.modal-header.sticky { position: sticky; top: 0; z-index: 5; }
.modal-close { background: transparent; border: none; font-size: 1.6rem; cursor: pointer; color: var(--text-secondary); }
.modal-close:hover { color: var(--text-heading); }
.modal-subtitle { margin: 4px 0 0; color: var(--text-tertiary); font-size: .95rem; }

.modal-body { padding: var(--space-lg); max-height: 80vh; overflow: auto; }
.modal-body-fill { flex: 1; max-height: none; overflow: auto; }

.modal-toolbar-row { display: flex; gap: 12px; align-items: flex-end; justify-content: space-between; flex-wrap: wrap; }
.form-group.compact { margin: 0; min-width: 320px; }

.scroll-sync-toggle { display: inline-flex; align-items: center; gap: 8px; font-size: .9rem; cursor: pointer; user-select: none; }
.scroll-sync-toggle input { accent-color: var(--brand-primary); }

.who-note {
  margin: 10px 0 0;
  padding: 10px;
  background: var(--surface-base);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  font-size: .85rem;
  color: var(--text-secondary);
}
.who-note code { margin-left: 6px; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; }

.loading-note { margin-top: 12px; display: inline-flex; align-items: center; gap: 10px; color: var(--text-secondary); }

.drilldown-container { margin-top: 14px; border-top: 1px solid var(--border-light); padding-top: 14px; }
.drilldown-topbar { display: flex; justify-content: space-between; align-items: center; gap: 10px; margin-bottom: 12px; flex-wrap: wrap; }
.drilldown-title { display: inline-flex; align-items: center; gap: 10px; }

.drilldown-stats { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 10px; }
.stat { padding: 8px 10px; background: var(--surface-base); border-radius: var(--radius-md); min-width: 90px; text-align: center; border: 1px solid var(--border-light); }
.stat .k { display: block; font-size: .75rem; color: var(--text-tertiary); }
.stat .v { display: block; font-size: 1.1rem; font-weight: 900; }
.stat.warn { border-left: 4px solid #f59e0b; }
.stat.good { border-left: 4px solid #22c55e; }
.stat.bad { border-left: 4px solid #ef4444; }

.truncation-warning { color: #d97706; font-weight: 900; background: #fff7ed; border: 1px solid #fed7aa; padding: 10px; border-radius: var(--radius-md); }

.empty-diff-block {
  margin-top: 12px;
  padding: 14px;
  border-radius: var(--radius-md);
  border: 1px solid var(--border-light);
  background: var(--surface-base);
}
.empty-diff-block h5 { margin: 0 0 6px; }
.empty-diff-block p { margin: 0; color: var(--text-tertiary); }

/* Side-by-side diff overflow safety */
.delta-tables {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: var(--space-lg);
  width: 100%;
}
.delta-side { min-width: 0; overflow: hidden; }
.delta-side h5 { margin: 0 0 8px; }
.delta-side.side-a h5 { color: #dc2626; }
.delta-side.side-b h5 { color: #16a34a; }

.scroll-box {
  max-height: 72vh;
  overflow-x: auto;
  overflow-y: auto;
  max-width: 100%;
  overscroll-behavior: contain;
  -webkit-overflow-scrolling: touch;
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  background: var(--surface-base);
}

.delta-table { width: max-content; min-width: 100%; border-collapse: collapse; }
.delta-table th, .delta-table td { white-space: nowrap; }
.delta-table thead th {
  position: sticky;
  top: 0;
  z-index: 4;
  background: var(--surface-base);
}

.col-narrow { width: 64px; max-width: 64px; }
.sticky-col-1 { position: sticky; left: 0; z-index: 5; background: var(--surface-base); box-shadow: 1px 0 0 var(--border-light); }
.sticky-col-2 { position: sticky; left: 64px; z-index: 5; background: var(--surface-base); box-shadow: 1px 0 0 var(--border-light); }

/* Kind badges */
.kind-badge { display: inline-block; padding: 2px 8px; border-radius: 6px; font-size: .75rem; font-weight: 900; border: 1px solid transparent; }
.kind-modified { background: #fef3c7; color: #92400e; border-color: #fde68a; }
.kind-added { background: #d1fae5; color: #065f46; border-color: #a7f3d0; }
.kind-removed { background: #fee2e2; color: #991b1b; border-color: #fecaca; }

/* Only changed cells get color */
.cell-old { background: rgba(239, 68, 68, 0.12); }
.cell-new { background: rgba(34, 197, 94, 0.12); }

/* Dot styling */
.cell-dot { cursor: pointer; font-size: 1rem; margin-right: 6px; transition: transform .15s; }
.cell-dot:hover { transform: scale(1.2); }
.cell-dot.dot-red { color: #ef4444; }
.cell-dot.dot-green { color: #22c55e; }
.cell-value { font-size: .85rem; }

/* Only changed cells appear clickable */
.clickable-cell { cursor: pointer; }

.cell-meta p { margin: 8px 0; }
.cell-comparison { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 10px; }
.cell-side { padding: 12px; border-radius: var(--radius-md); border: 2px solid transparent; }
.cell-side.old { background: #fef2f2; border-color: #fecaca; }
.cell-side.new { background: #f0fdf4; border-color: #bbf7d0; }
.cell-content {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  white-space: pre-wrap;
  word-break: break-word;
  background: #fff;
  padding: 10px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-light);
  max-height: 220px;
  overflow: auto;
}

.spinner {
  display: inline-block;
  width: 16px;
  height: 16px;
  border: 2px solid transparent;
  border-top-color: currentColor;
  border-radius: 50%;
  animation: spin .8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

@media (max-width: 900px) {
  .sides-grid { grid-template-columns: 1fr; }
  .delta-tables { grid-template-columns: 1fr; }
  .modal-card.modal-wide { width: 98vw; height: 96vh; }
  .scroll-box { max-height: 55vh; }
  .form-group.compact { min-width: 240px; }
  .search-filter-inline .form-input { min-width: 180px; }
}
</style>