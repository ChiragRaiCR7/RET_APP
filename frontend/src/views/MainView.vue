<template>
  <div class="main-view">
    <!-- Page Header -->
    <header class="page-header">
      <div class="page-title">
        <h2 class="title">RET Workspace</h2>
        <p class="subtitle">
          Upload a ZIP, convert files, review results, and download outputs with confidence.
        </p>
      </div>

      <!-- Session status -->
      <div class="session-chip" :class="{ muted: !workflow.sessionId }" role="status" aria-live="polite">
        <span class="dot" :class="workflow.sessionId ? 'dot-success' : 'dot-muted'" aria-hidden="true"></span>
        <span>{{ workflow.sessionId ? 'Session active' : 'No active session' }}</span>
      </div>
    </header>

    <!-- Tabs -->
    <nav class="tabs" role="tablist" aria-label="Workspace sections">
      <button
        v-for="(tab, idx) in tabs"
        :key="idx"
        class="tab"
        :class="{ active: activeTab === idx }"
        @click="activeTab = idx"
        role="tab"
        :aria-selected="activeTab === idx"
        :aria-controls="`panel-${idx}`"
        :id="`tab-${idx}`"
      >
        <span class="tab-icon" aria-hidden="true">{{ tab.icon }}</span>
        <span class="tab-label">{{ tab.label }}</span>
      </button>
    </nav>

    <!-- TAB 0: Utility -->
    <section
      v-show="activeTab === 0"
      class="card"
      role="tabpanel"
      :id="'panel-0'"
      :aria-labelledby="'tab-0'"
    >
      <div class="card-header">
        <div>
          <h3 class="card-title">Utility</h3>
          <p class="card-subtitle">
            Convert ZIP contents, preview outputs, and download by file, group, or as a complete package.
          </p>
        </div>

        <div class="header-actions">
          <button class="btn btn-secondary" @click="cleanupSession" :disabled="!workflow.sessionId">
            Cleanup
          </button>
          <button class="btn btn-secondary" @click="clearWorkflow">
            Reset
          </button>
        </div>
      </div>

      <!-- Quick Start Banner -->
      <div class="info-banner" role="note">
        <div class="info-left">
          <span class="badge">Quick start</span>
          <ol class="steps">
            <li><strong>Upload</strong> a ZIP file</li>
            <li><strong>Convert</strong> the detected files</li>
            <li><strong>Review</strong> preview and <strong>download</strong> outputs</li>
          </ol>
        </div>
        <div class="info-right">
          <p class="hint">
            Tip: Enable <strong>Edit Mode</strong> only if you need to adjust outputs before downloading.
          </p>
        </div>
      </div>

      <!-- Settings -->
      <div class="section">
        <div class="section-head">
          <h4 class="section-title">Settings</h4>
          <p class="section-help">Choose output format and optional editing before conversion.</p>
        </div>

        <div class="settings-grid">
          <div class="field">
            <label class="label">Download format</label>
            <div class="segmented" role="group" aria-label="Download format selection">
              <label class="seg-option">
                <input type="radio" v-model="workflow.outputFormat" value="csv" />
                <span>CSV</span>
              </label>
              <label class="seg-option">
                <input type="radio" v-model="workflow.outputFormat" value="xlsx" />
                <span>Excel (.xlsx)</span>
              </label>
            </div>
            <p class="field-help">This applies to downloads after conversion.</p>
          </div>

          <div class="field">
            <label class="label">Edit Mode</label>
            <EditModeToggle v-model="workflow.editMode" />
            <p class="field-help">
              Make session-only changes to outputs, then download the modified package.
            </p>
          </div>

          <div class="field">
            <label class="label">Performance</label>
            <div class="perf-pill" role="status" aria-label="Performance mode enabled">
              🚀 High-performance mode <strong>(enabled)</strong>
            </div>
            <p class="field-help">Optimized for large archives. No action required.</p>
          </div>
        </div>

        <div class="actions-row">
          <button class="btn btn-secondary" @click="clearAllEdits" :disabled="!workflow.editMode">
            Clear edits
          </button>
          <span class="muted-text">Sessions auto-expire after 60 minutes of inactivity.</span>
        </div>
      </div>

      <!-- Upload & Convert -->
      <div class="section">
        <div class="section-head">
          <h4 class="section-title">Upload & Convert</h4>
          <p class="section-help">Upload a ZIP to scan contents. Then convert in one click.</p>
        </div>

        <div class="upload-card">
          <FileUploader
            @uploaded="onUploaded"
            @files-added="onFilesAdded"
            :show-scan-results="false"
          />

          <!-- Scan Summary -->
          <div v-if="workflow.scanSummary" class="summary" aria-label="Scan summary">
            <div class="summary-item">
              <div class="summary-label">Groups found</div>
              <div class="summary-value">{{ workflow.scanSummary.totalGroups }}</div>
            </div>
            <div class="summary-item">
              <div class="summary-label">Files found</div>
              <div class="summary-value">{{ workflow.scanSummary.totalFiles }}</div>
            </div>
          </div>

          <div class="cta-row">
            <button class="btn btn-primary" @click="bulkConvert" :disabled="!canConvert">
              <span v-if="converting" class="spinner" aria-hidden="true"></span>
              {{ converting ? 'Converting…' : 'Convert all' }}
            </button>

            <span class="muted-text">
              Upload → Scan → Convert. Preview and downloads appear below.
            </span>
          </div>

          <!-- Background status -->
          <div
            v-if="embeddingStatus"
            class="status-banner"
            :class="'status-' + embeddingStatus"
            role="status"
            aria-live="polite"
          >
            <span v-if="embeddingStatus === 'embedding'" class="spinner" aria-hidden="true"></span>

            <div class="status-text">
              <strong v-if="embeddingStatus === 'embedding'">Preparing AI chat…</strong>
              <strong v-else-if="embeddingStatus === 'done'">AI chat is ready.</strong>
              <strong v-else-if="embeddingStatus === 'error'">AI preparation failed.</strong>
              <strong v-else-if="embeddingStatus === 'info'">AI preparation skipped.</strong>

              <span v-if="embeddingStatus === 'embedding'" class="muted-text">
                You can continue working while this completes.
              </span>
              <span v-else-if="embeddingMessage" class="muted-text">
                {{ embeddingMessage }}
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- Downloads -->
      <div v-if="workflow.converted && conversionData.files.length" class="section">
        <div class="section-head">
          <h4 class="section-title">Downloads</h4>
          <p class="section-help">Download everything at once, or download by group and file.</p>
        </div>

        <div class="download-bar">
          <button class="btn btn-primary" @click="downloadAll" :disabled="!workflow.sessionId">
            Download full package
          </button>

          <button
            class="btn btn-warning"
            @click="downloadModifiedZip"
            :disabled="!workflow.sessionId || !workflow.editMode"
            title="Enable Edit Mode to download modified package"
          >
            Download modified package
          </button>

          <button class="btn btn-secondary" @click="downloadPatchLog">
            Download change log
          </button>

          <span class="muted-text">
            Total files: <strong>{{ conversionData.files.length }}</strong>
          </span>
        </div>
      </div>

      <!-- Browse & Preview -->
      <div v-if="workflow.converted" class="section">
        <div class="section-head">
          <h4 class="section-title">Browse & Preview</h4>
          <p class="section-help">
            Group selection is above. Preview is below (full-width for large column files).
          </p>
        </div>

        <div class="browse-stack">
          <!-- Groups -->
          <div class="card-sub">
            <div class="sub-head">
              <h5 class="sub-title">Groups</h5>
              <div class="sub-actions">
                <button class="btn btn-sm btn-secondary" @click="selectAllGroups">
                  Select all
                </button>
                <button class="btn btn-sm btn-secondary" @click="clearGroupSelection">
                  Clear
                </button>
              </div>
            </div>

            <div class="search">
              <label class="label">Search</label>
              <input
                v-model="groupSearch"
                type="text"
                class="input"
                placeholder="Type to filter groups"
              />
            </div>

            <!-- Group selection (Listbox) -->
            <div class="field slim">
              <label class="label">Group selection</label>
              <Listbox v-model="selectedGroups" multiple>
                <div class="listbox">
                  <ListboxButton class="listbox-button">
                    <span>
                      {{ selectedGroups.length ? `${selectedGroups.length} selected` : 'Select groups…' }}
                    </span>
                    <span class="chev" aria-hidden="true">▾</span>
                  </ListboxButton>

                  <transition
                    enter-active-class="listbox-enter-active"
                    enter-from-class="listbox-enter-from"
                    enter-to-class="listbox-enter-to"
                    leave-active-class="listbox-leave-active"
                    leave-from-class="listbox-leave-from"
                    leave-to-class="listbox-leave-to"
                  >
                    <ListboxOptions class="listbox-options">
                      <div class="listbox-search">
                        <input
                          v-model="groupSearch"
                          type="text"
                          class="input"
                          placeholder="Search groups…"
                          @click.stop
                        />
                      </div>

                      <ListboxOption
                        v-for="group in filteredGroups"
                        :key="group.name"
                        :value="group.name"
                        v-slot="{ active, selected }"
                        as="template"
                      >
                        <li :class="['listbox-option', { active, selected }]">
                          <span class="tick" aria-hidden="true">{{ selected ? '✓' : '' }}</span>
                          <span class="name">{{ group.name }}</span>
                          <span class="meta">{{ group.file_count || 0 }} files</span>
                        </li>
                      </ListboxOption>

                      <li v-if="filteredGroups.length === 0" class="empty">
                        No results for “{{ groupSearch }}”
                      </li>
                    </ListboxOptions>
                  </transition>
                </div>
              </Listbox>
              <p class="field-help">Use selection to narrow results and focus on relevant groups.</p>
            </div>

            <!-- Active group -->
            <div class="field slim">
              <label class="label">Active group</label>
              <select v-model="activeGroup" class="select" @change="loadGroupFiles">
                <option value="">Select a group…</option>
                <option v-for="g in conversionData.groups" :key="g.name" :value="g.name">
                  {{ g.name }}
                </option>
              </select>
              <p class="field-help">Choose a group to load its files and preview.</p>
            </div>
          </div>

          <!-- Preview -->
          <div class="card-sub">
            <div class="sub-head">
              <h5 class="sub-title">Preview</h5>

              <span v-if="activeGroup" class="pill">
                {{ activeGroup }} • {{ groupFiles.length }} file(s)
              </span>
              <span v-else class="muted-text">Select a group to begin.</span>
            </div>

            <div v-if="activeGroup" class="field slim">
              <label class="label">File</label>

              <!-- value keeps REAL filename, label hides extension -->
              <select v-model="activeFile" class="select" @change="loadFilePreview">
                <option v-for="f in groupFiles" :key="f.filename" :value="f.filename">
                  {{ displayFileName(f.filename) }}
                </option>
              </select>

              <p class="field-help">
                Preview shows a sample of rows to validate formatting before download.
              </p>
            </div>

            <div v-if="preview" class="preview-meta">
              <div class="meta-item">
                <div class="meta-k">Rows</div>
                <div class="meta-v">{{ preview.total_rows }}</div>
              </div>
              <div class="meta-item">
                <div class="meta-k">Columns</div>
                <div class="meta-v">{{ preview.headers?.length }}</div>
              </div>
            </div>

            <!-- ✅ Excel-style controls (Search / Filter / Sort) -->
            <div v-if="preview" class="grid-controls">
              <div class="grid-left">
                <div class="field slim grid-search">
                  <label class="label">Search rows</label>
                  <input
                    v-model="tableSearch"
                    class="input"
                    :disabled="workflow.editMode"
                    placeholder="Search across all columns…"
                    aria-label="Search rows in preview table"
                  />
                  <p class="field-help" v-if="workflow.editMode">
                    Search / sort / filter are disabled in Edit Mode to keep row mapping safe.
                  </p>
                </div>
              </div>

              <div class="grid-right">
                <button class="btn btn-sm btn-secondary" @click="clearTableControls" :disabled="workflow.editMode">
                  Clear search/filter
                </button>
                <button
                  class="btn btn-sm btn-secondary"
                  @click="showColumnFilters = !showColumnFilters"
                  :disabled="workflow.editMode"
                >
                  {{ showColumnFilters ? 'Hide filters' : 'Show filters' }}
                </button>
              </div>
            </div>

            <div v-if="workflow.editMode && activeGroup && preview" class="edit-banner">
              <div>
                <strong>{{ pendingChangesCount }}</strong> change(s) pending
                <span class="muted-text">— Save to apply changes.</span>
              </div>
              <button
                class="btn btn-sm btn-primary"
                @click="saveCellEdits"
                :disabled="pendingChangesCount === 0"
              >
                Save changes
              </button>
            </div>

            <div v-if="preview" class="table-hint">
              <span class="muted-text">
                Tip: Click a column header to sort. Use filters to narrow results.
              </span>
            </div>

            <!-- ✅ Preview table -->
            <div v-if="preview" class="table-wrap" aria-label="Preview table">
              <table class="table">
                <thead>
                  <tr>
                    <th
                      v-for="(header, idx) in preview.headers"
                      :key="idx"
                      class="sortable"
                      :class="{ sorted: sortCol === idx }"
                      @click="toggleSort(idx)"
                      :title="workflow.editMode ? 'Sorting disabled in Edit Mode' : 'Click to sort'"
                    >
                      <div class="th-inner">
                        <span>{{ header }}</span>
                        <span class="sort-ind" aria-hidden="true">
                          <template v-if="sortCol === idx">
                            {{ sortDir === 'asc' ? '▲' : '▼' }}
                          </template>
                          <template v-else>⇅</template>
                        </span>
                      </div>
                    </th>
                  </tr>

                  <!-- Column filters row -->
                  <tr v-if="showColumnFilters && !workflow.editMode" class="filter-row">
                    <th v-for="(header, idx) in preview.headers" :key="'f-' + idx">
                      <input
                        v-model="columnFilters[idx]"
                        class="filter-input"
                        type="text"
                        :placeholder="`Filter ${header}…`"
                        @click.stop
                      />
                    </th>
                  </tr>
                </thead>

                <tbody>
                  <tr v-for="(row, rowIdx) in displayRows" :key="rowIdx">
                    <td v-for="(cell, colIdx) in row" :key="colIdx">
                      <template v-if="workflow.editMode">
                        <!-- In edit mode we keep using original preview rows (no sorting/filtering). -->
                        <input
                          v-model="preview.rows[rowIdx][colIdx]"
                          class="cell"
                          @change="markCellChanged(rowIdx, colIdx)"
                          :aria-label="`Edit row ${rowIdx + 1}, column ${preview.headers?.[colIdx] || colIdx + 1}`"
                        />
                      </template>
                      <template v-else>
                        {{ formatCellValue(cell) }}
                      </template>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div v-else-if="activeGroup" class="empty-state">
              <div class="empty-title">No preview loaded</div>
              <div class="empty-text">Select a file to load a preview.</div>
            </div>

            <div v-if="activeGroup" class="download-row">
              <button class="btn btn-secondary" @click="downloadCurrentFile" :disabled="!activeFile">
                Download this file
              </button>
              <button class="btn btn-primary" @click="downloadGroupZip" :disabled="!activeGroup">
                Download group package
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- AI section -->
      <div v-if="workflow.converted && conversionData.groups.length" class="section">
        <div class="ai-card">
          <div>
            <h4 class="section-title">AI Search & Chat</h4>
            <p class="section-help">
              Ask questions across your converted outputs using the AI tab.
            </p>
          </div>

          <div class="ai-actions">
            <button class="btn btn-secondary" @click="activeTab = 3">
              Open AI tab
            </button>
            <span v-if="indexedGroups.length" class="muted-text">
              Indexed: <strong>{{ indexedGroups.length }}</strong> group(s)
            </span>
          </div>
        </div>
      </div>

      <!-- Edit Mode Panel -->
      <EditModePanel
        v-if="workflow.editMode && workflow.sessionId"
        :session-id="workflow.sessionId"
        :files="conversionData.files"
        @file-updated="onFileUpdated"
        @file-added="onFileAdded"
        @file-removed="onFileRemoved"
      />
    </section>

    <!-- TAB 1: Business Structure -->
    <section
      v-show="activeTab === 1"
      class="card"
      role="tabpanel"
      :id="'panel-1'"
      :aria-labelledby="'tab-1'"
    >
      <div class="card-header">
        <div>
          <h3 class="card-title">Business Structure</h3>
          <p class="card-subtitle">Explore organization hierarchy from the current scanned session.</p>
        </div>
      </div>
      <BusinessStructurePanel
        :session-id="workflow.sessionId"
        :uploaded-filename="workflow.uploadedFilename"
        :scan-summary="workflow.scanSummary"
        :scanned-files="workflow.scannedFiles"
        :scanned-groups="workflow.scannedGroups"
      />
    </section>

    <!-- TAB 2: Compare -->
    <section
      v-show="activeTab === 2"
      class="card"
      role="tabpanel"
      :id="'panel-2'"
      :aria-labelledby="'tab-2'"
    >
      <div class="card-header">
        <div>
          <h3 class="card-title">Compare</h3>
          <p class="card-subtitle">Compare files side-by-side to validate outputs and differences.</p>
        </div>
      </div>
      <ComparisonPanel @comparison-complete="onComparisonComplete" />
    </section>

    <!-- TAB 3: AI -->
    <section
      v-show="activeTab === 3"
      class="card"
      role="tabpanel"
      :id="'panel-3'"
      :aria-labelledby="'tab-3'"
    >
      <div class="card-header">
        <div>
          <h3 class="card-title">AI</h3>
          <p class="card-subtitle">Search and ask questions across your converted outputs.</p>
        </div>
      </div>
      <AIPanel
        :session-id="workflow.sessionId"
        :scanned-groups="workflow.scannedGroups"
        @groups-indexed="onGroupsIndexed"
      />
    </section>
  </div>
</template>

<script setup>
/**
 * MainView.vue — RET Workspace
 * Tabs:
 *  0 — Utility: Upload → Convert → Preview → Download
 *  1 — Business Structure
 *  2 — Compare
 *  3 — AI
 */
import { ref, reactive, computed, watch, onUnmounted, defineAsyncComponent } from 'vue'
import { Listbox, ListboxButton, ListboxOptions, ListboxOption } from '@headlessui/vue'
import FileUploader from '@/components/workspace/FileUploader.vue'
import EditModeToggle from '@/components/workspace/EditModeToggle.vue'
import api, { longApi, pollJob } from '@/utils/api'
import { useToastStore } from '@/stores/toastStore'

const BusinessStructurePanel = defineAsyncComponent(() => import('@/components/workspace/BusinessStructurePanel.vue'))
const ComparisonPanel = defineAsyncComponent(() => import('@/components/workspace/ComparisonPanel.vue'))
const AIPanel = defineAsyncComponent(() => import('@/components/workspace/AIPanel.vue'))
const EditModePanel = defineAsyncComponent(() => import('@/components/workspace/EditModePanel.vue'))

const toast = useToastStore()
const activeTab = ref(0)

const tabs = [
  { icon: '📁', label: 'Utility' },
  { icon: '🏢', label: 'Business Structure' },
  { icon: '📊', label: 'Compare' },
  { icon: '✨', label: 'AI' }
]

// Workflow state
const workflow = reactive({
  sessionId: null,
  outputFormat: 'csv',
  editMode: false,
  fastParser: true,
  uploadedFiles: [],
  uploadedFilename: '',
  scannedFiles: [],
  scannedGroups: [],
  scanSummary: null,
  converted: false
})

const converting = ref(false)
const embeddingStatus = ref(null)
const embeddingProgress = ref(null)
const embeddingMessage = ref('')

const groupSearch = ref('')
const selectedGroups = ref([])
const activeGroup = ref('')
const activeFile = ref('')
const preview = ref(null)
const groupFiles = ref([])
const pendingCellEdits = ref(new Map())

const conversionData = reactive({
  groups: [],
  files: [],
  totalFiles: 0
})

const indexedGroups = ref([])

/** -----------------------------
 * ✅ Hide extensions in UI
 * Removes: .xml.gz, .xml, .csv, .xlsx, .xls, .xlf (case-insensitive)
 * Leaves the original filename intact for backend operations.
 * ------------------------------ */
function displayFileName(name) {
  if (!name) return ''
  return String(name)
    .replace(/\.(xml\.gz|xml|csv|xlsx|xls|xlf)$/i, '')
    .toUpperCase()
}

// Computed helpers
const filteredGroups = computed(() => {
  if (!groupSearch.value) return conversionData.groups
  const search = groupSearch.value.toLowerCase()
  return conversionData.groups.filter(g => (g.name || '').toLowerCase().includes(search))
})

const pendingChangesCount = computed(() => pendingCellEdits.value.size)

const canConvert = computed(() => {
  return !!workflow.sessionId && workflow.scannedGroups.length > 0 && !converting.value
})

watch(() => workflow.editMode, (enabled) => {
  if (!enabled) pendingCellEdits.value = new Map()
  // Reset table controls when toggling edit mode
  resetTableControls()
})

/** -----------------------------
 * ✅ Excel-like table controls (search/sort/filter)
 * ------------------------------ */
const tableSearch = ref('')
const showColumnFilters = ref(false)
const sortCol = ref(null) // number | null
const sortDir = ref('asc') // 'asc' | 'desc'
const columnFilters = reactive({}) // key: colIndex -> string

function resetTableControls() {
  tableSearch.value = ''
  showColumnFilters.value = false
  sortCol.value = null
  sortDir.value = 'asc'
  // keep keys but clear values
  Object.keys(columnFilters).forEach(k => (columnFilters[k] = ''))
}

function clearTableControls() {
  if (workflow.editMode) return
  tableSearch.value = ''
  Object.keys(columnFilters).forEach(k => (columnFilters[k] = ''))
}

function toggleSort(colIdx) {
  if (workflow.editMode) return
  if (sortCol.value === colIdx) {
    sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortCol.value = colIdx
    sortDir.value = 'asc'
  }
}

function isNumeric(v) {
  if (v === null || v === undefined) return false
  const s = String(v).trim()
  if (!s) return false
  return !Number.isNaN(Number(s))
}

function compareCells(a, b) {
  // numeric if both are numeric
  if (isNumeric(a) && isNumeric(b)) return Number(a) - Number(b)
  // string compare fallback
  return String(a ?? '').localeCompare(String(b ?? ''), undefined, { numeric: true, sensitivity: 'base' })
}

/**
 * displayRows is the final view for preview table in non-edit mode.
 * In edit mode: returns preview.rows directly (so editing remains correct).
 */
const displayRows = computed(() => {
  if (!preview.value?.rows || !preview.value?.headers) return []

  // In Edit Mode: avoid sort/filter/search to keep indices stable
  if (workflow.editMode) return preview.value.rows

  const rows = preview.value.rows
  const headers = preview.value.headers

  const q = tableSearch.value.trim().toLowerCase()

  // apply global search and per-column filters
  let filtered = rows.filter(r => {
    // Global search
    if (q) {
      const hay = (r || []).join(' ').toLowerCase()
      if (!hay.includes(q)) return false
    }

    // Column filters
    for (let i = 0; i < headers.length; i++) {
      const f = (columnFilters[i] || '').trim().toLowerCase()
      if (!f) continue
      const cell = String((r || [])[i] ?? '').toLowerCase()
      if (!cell.includes(f)) return false
    }
    return true
  })

  // sort
  if (sortCol.value !== null) {
    const c = sortCol.value
    filtered = [...filtered].sort((ra, rb) => {
      const a = (ra || [])[c]
      const b = (rb || [])[c]
      const cmp = compareCells(a, b)
      return sortDir.value === 'asc' ? cmp : -cmp
    })
  }

  return filtered
})

/** -----------------------------
 * Existing helpers
 * ------------------------------ */
function formatCellValue(value, maxLen = 50) {
  if (value === null || value === undefined) return ''
  const str = String(value)
  return str.length > maxLen ? str.substring(0, maxLen) + '…' : str
}

function onFilesAdded(filesList) {
  workflow.uploadedFiles.push(...filesList)
  if (!workflow.uploadedFilename && filesList?.length) {
    workflow.uploadedFilename = filesList[0]?.name || ''
  }
}

/**
 * FileUploader emits scan result payload.
 * Supports both sessionId and session_id.
 */
function onUploaded(data) {
  if (Array.isArray(data)) {
    workflow.uploadedFiles.push(...data)
    if (!workflow.uploadedFilename && data.length) {
      workflow.uploadedFilename = data[0]?.name || ''
    }
    return
  }

  const sid = data?.sessionId || data?.session_id
  if (!sid) return

  workflow.sessionId = sid
  workflow.uploadedFilename =
    data?.uploaded_filename ||
    data?.original_filename ||
    data?.filename ||
    data?.name ||
    workflow.uploadedFiles?.[0]?.name ||
    ''

  workflow.scannedFiles =
    data?.files ||
    data?.scanned_files ||
    data?.scannedFiles ||
    []

  const groups = (data.groups || []).map(g => ({
    name: g.name,
    file_count: g.file_count || g.fileCount || 0,
    size: g.size || 0
  }))

  workflow.scannedGroups = groups

  workflow.scanSummary = {
    totalGroups: groups.length,
    totalFiles: data.file_count || data.xml_count || data.xmlCount || workflow.scannedFiles.length || 0,
    totalSize: data.summary?.totalSize || '—'
  }
}

function clearWorkflow() {
  workflow.sessionId = null
  workflow.uploadedFiles = []
  workflow.uploadedFilename = ''
  workflow.scannedFiles = []
  workflow.scannedGroups = []
  workflow.scanSummary = null
  workflow.converted = false

  conversionData.groups = []
  conversionData.files = []
  conversionData.totalFiles = 0

  activeGroup.value = ''
  activeFile.value = ''
  preview.value = null
  groupFiles.value = []
  selectedGroups.value = []
  groupSearch.value = ''
  pendingCellEdits.value = new Map()

  embeddingStatus.value = null
  embeddingProgress.value = null
  embeddingMessage.value = ''
  stopEmbeddingPolling()

  resetTableControls()
}

// ✅ Convert using longApi (prevents 30s timeout)
function buildConversionIdempotencyKey() {
  const groups = (workflow.scannedGroups || [])
    .map(g => String(g?.name || '').toUpperCase().trim())
    .filter(Boolean)
    .sort()
    .join(',')

  return `convert:${workflow.sessionId}:${String(workflow.outputFormat || 'csv').toLowerCase()}:${groups}`
}

async function bulkConvert() {
  if (!workflow.sessionId) {
    toast.warning('Please upload and scan a ZIP first.')
    return
  }

  converting.value = true
  try {
    const formData = new FormData()
    formData.append('session_id', workflow.sessionId)
    formData.append('output_format', workflow.outputFormat)
    formData.append('idempotency_key', buildConversionIdempotencyKey())

    // Convert all scanned groups by default
    workflow.scannedGroups.forEach(g => formData.append('groups', g.name))

    const started = await longApi.post('/conversion/convert-async', formData, {
      timeout: 60_000
    })

    const jobId = started?.data?.job_id || started?.data?.jobId || started?.data?.id
    if (!jobId) {
      throw new Error('Async conversion start did not return job_id')
    }

    const payload = await pollJob(jobId, {
      intervalMs: 1500,
      timeoutMs: 60 * 60 * 1000
    })

    if (payload && !payload.error) {
      workflow.converted = true
      toast.success(`Conversion complete. ${payload.stats?.success || 0} file(s) converted.`)

      await loadConvertedFiles(true)
      handleEmbeddingMetadata(payload)
    } else {
      throw new Error(payload?.message || payload?.error || 'Conversion failed')
    }
  } catch (e) {
    toast.error('Conversion failed: ' + (e.response?.data?.detail || e.message))
  } finally {
    converting.value = false
  }
}

let embeddingPollTimer = null

function stopEmbeddingPolling() {
  if (embeddingPollTimer) {
    clearInterval(embeddingPollTimer)
    embeddingPollTimer = null
  }
}

function infoTextForEmbeddingStatus(status) {
  if (status === 'no_eligible_groups') return 'No eligible groups found for embedding in this session.'
  if (status === 'no_inventory') return 'No inventory metadata is available for embedding.'
  if (status === 'disabled') return 'Auto-embedding is disabled by administrator configuration.'
  return ''
}

function resolveEmbeddingStatus(payload = {}) {
  const top = payload?.embedding_status
  const nested = payload?.embedding?.status || payload?.embedding?.state
  const legacy = typeof payload?.embedding === 'string' ? payload.embedding : ''
  return String(top || nested || legacy || '').toLowerCase()
}

function handleEmbeddingMetadata(payload = {}) {
  const status = resolveEmbeddingStatus(payload)

  if (!status) {
    // Backward compatible fallback for legacy payloads.
    if (payload?.embedding_status === 'started') {
      embeddingStatus.value = 'embedding'
      embeddingMessage.value = ''
      pollEmbeddingStatus()
    }
    return
  }

  if (status === 'started' || status === 'already_running') {
    embeddingStatus.value = 'embedding'
    embeddingMessage.value = status === 'already_running'
      ? 'Embedding is already running in the background.'
      : ''
    pollEmbeddingStatus()
    return
  }

  stopEmbeddingPolling()

  if (status === 'already_indexed') {
    embeddingStatus.value = 'done'
    embeddingMessage.value = 'Selected groups are already indexed for AI.'
    return
  }

  if (status === 'failed') {
    embeddingStatus.value = 'error'
    embeddingMessage.value = payload?.embedding?.message || payload?.embedding_error || 'Embedding did not complete.'
    return
  }

  if (status === 'no_eligible_groups' || status === 'no_inventory' || status === 'disabled') {
    embeddingStatus.value = 'info'
    embeddingMessage.value = infoTextForEmbeddingStatus(status)
    return
  }

  // Unknown status: keep UI non-disruptive.
  embeddingStatus.value = null
  embeddingMessage.value = ''
}

function pollEmbeddingStatus() {
  embeddingStatus.value = 'embedding'
  stopEmbeddingPolling()

  embeddingPollTimer = setInterval(async () => {
    try {
      const res = await api.get(`/v2/ai/embedding/status/${workflow.sessionId}`)
      embeddingProgress.value = res.data

      const status = String(res?.data?.status || res?.data?.embedding_status || '').toLowerCase()

      if (status === 'failed') {
        embeddingStatus.value = 'error'
        embeddingMessage.value = res?.data?.message || 'Embedding failed.'
        stopEmbeddingPolling()
        return
      }

      if (status === 'disabled' || status === 'no_eligible_groups' || status === 'no_inventory') {
        embeddingStatus.value = 'info'
        embeddingMessage.value = infoTextForEmbeddingStatus(status)
        stopEmbeddingPolling()
        return
      }

      if (['done', 'completed', 'succeeded', 'success', 'already_indexed'].includes(status)) {
        embeddingStatus.value = 'done'
        embeddingMessage.value = ''
        toast.success('AI is ready. You can use the AI tab now.')
        stopEmbeddingPolling()
        return
      }

      const totalGroups = Object.keys(res.data.groups || {}).length
      const doneCount = Object.values(res.data.groups || {}).filter(g => g.indexed > 0).length

      if (totalGroups > 0 && doneCount >= totalGroups) {
        embeddingStatus.value = 'done'
        embeddingMessage.value = ''
        toast.success('AI is ready. You can use the AI tab now.')
        stopEmbeddingPolling()
      }
    } catch (e) {
      console.debug('Embedding status poll:', e.message)
    }
  }, 3000)
}

/**
 * Load output listing; use longApi for large sessions
 */
async function loadConvertedFiles(useLong = false) {
  if (!workflow.sessionId) return

  try {
    const client = useLong ? longApi : api
    const res = await client.get(`/conversion/files/${workflow.sessionId}`, {
      timeout: useLong ? 15 * 60 * 1000 : 30_000
    })

    conversionData.groups = res.data.groups || []
    conversionData.files = res.data.files || []
    conversionData.totalFiles = res.data.total_files || 0

    if (conversionData.groups.length > 0) {
      activeGroup.value = conversionData.groups[0].name
      await loadGroupFiles()
    }
  } catch (e) {
    console.error('Failed to load converted files:', e)
  }
}

async function loadGroupFiles() {
  if (!activeGroup.value) return

  groupFiles.value = conversionData.files.filter(f => f.group === activeGroup.value)

  if (groupFiles.value.length > 0) {
    activeFile.value = groupFiles.value[0].filename
    pendingCellEdits.value = new Map()
    await loadFilePreview()
  } else {
    activeFile.value = ''
    preview.value = null
    resetTableControls()
  }
}

async function loadFilePreview() {
  if (!activeFile.value || !workflow.sessionId) return

  try {
    const res = await api.get(`/conversion/preview/${workflow.sessionId}/${activeFile.value}`, {
      params: { max_rows: 100 }
    })
    preview.value = res.data
    pendingCellEdits.value = new Map()

    // init/reset table controls + column filters based on header count
    resetTableControls()
    if (preview.value?.headers?.length) {
      preview.value.headers.forEach((_, idx) => {
        if (columnFilters[idx] === undefined) columnFilters[idx] = ''
      })
      // also remove old keys if new file has fewer cols
      Object.keys(columnFilters).forEach(k => {
        const i = Number(k)
        if (i >= preview.value.headers.length) delete columnFilters[k]
      })
    }
  } catch (e) {
    console.error('Failed to load preview:', e)
    preview.value = null
    resetTableControls()
  }
}

function selectAllGroups() {
  selectedGroups.value = conversionData.groups.map(g => g.name)
}

function clearGroupSelection() {
  selectedGroups.value = []
}

function markCellChanged(rowIdx, colIdx) {
  if (!preview.value || !workflow.editMode) return
  const column = preview.value.headers?.[colIdx]
  if (!column) return

  const value = preview.value.rows?.[rowIdx]?.[colIdx]
  const key = `${rowIdx}::${column}`

  const next = new Map(pendingCellEdits.value)
  next.set(key, { row_index: rowIdx, column, value })
  pendingCellEdits.value = next
}

async function saveCellEdits() {
  if (!workflow.sessionId || !activeFile.value) {
    toast.error('No file selected to save.')
    return
  }

  const changes = Array.from(pendingCellEdits.value.values())
  if (!changes.length) {
    toast.info('No changes to save.')
    return
  }

  try {
    await api.post(`/conversion/update-cells/${workflow.sessionId}`, {
      filename: activeFile.value,
      changes
    })

    toast.success(`Saved ${changes.length} change(s).`)
    pendingCellEdits.value = new Map()
    await loadFilePreview()
  } catch (e) {
    toast.error('Failed to save: ' + (e.response?.data?.detail || e.message))
  }
}

async function downloadAll() {
  if (!workflow.sessionId) return
  try {
    const res = await api.get(`/conversion/download/${workflow.sessionId}`, { responseType: 'blob' })
    downloadBlob(res.data, 'converted_output.zip')
    toast.success('Download started.')
  } catch (e) {
    toast.error('Download failed: ' + (e.response?.data?.detail || e.message))
  }
}

async function downloadModifiedZip() {
  if (!workflow.sessionId || !workflow.editMode) return
  try {
    const res = await api.get(`/conversion/download-modified/${workflow.sessionId}`, { responseType: 'blob' })
    downloadBlob(res.data, 'modified_output.zip')
    toast.success('Download started.')
  } catch (e) {
    toast.error('Download failed: ' + (e.response?.data?.detail || e.message))
  }
}

async function downloadPatchLog() {
  toast.info('Change log download is not available yet.')
}

async function downloadCurrentFile() {
  if (!activeFile.value || !workflow.sessionId) return
  try {
    const res = await api.get(`/conversion/download-file/${workflow.sessionId}/${activeFile.value}`, {
      responseType: 'blob'
    })
    // download file with its real name (extension needed for OS)
    downloadBlob(res.data, activeFile.value)
  } catch (e) {
    toast.error('Download failed: ' + (e.response?.data?.detail || e.message))
  }
}

/**
 * Download group package:
 * POST /conversion/download-custom/{session_id}
 */
async function downloadGroupZip() {
  if (!activeGroup.value || !workflow.sessionId) return
  try {
    const formData = new FormData()
    formData.append('output_format', workflow.outputFormat || 'csv')
    formData.append('preserve_structure', 'false')
    formData.append('groups', activeGroup.value)

    const res = await longApi.post(`/conversion/download-custom/${workflow.sessionId}`, formData, {
      responseType: 'blob',
      timeout: 30 * 60 * 1000
    })

    downloadBlob(res.data, `${activeGroup.value}_group.zip`)
    toast.success('Download started.')
  } catch (e) {
    toast.error('Download failed: ' + (e.response?.data?.detail || e.message))
  }
}

function downloadBlob(data, filename) {
  const url = window.URL.createObjectURL(new Blob([data]))
  const link = document.createElement('a')
  link.href = url
  link.setAttribute('download', filename)
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.URL.revokeObjectURL(url)
}

async function cleanupSession() {
  if (!workflow.sessionId) {
    toast.warning('No active session to clean up.')
    return
  }
  try {
    await api.post(`/conversion/cleanup/${workflow.sessionId}`)
    toast.success('Session cleaned up.')
    clearWorkflow()
  } catch (e) {
    toast.error('Cleanup failed: ' + (e.response?.data?.detail || e.message))
  }
}

async function clearAllEdits() {
  pendingCellEdits.value = new Map()
  toast.info('Unsaved edits cleared.')
  if (workflow.sessionId && activeFile.value) await loadFilePreview()
}

function onComparisonComplete() {
  toast.success('Comparison complete.')
}

function onGroupsIndexed(groups) {
  indexedGroups.value = [...new Set([...indexedGroups.value, ...(groups || [])])]
  toast.success(`${(groups || []).length} group(s) indexed.`)
}

function onFileUpdated() { loadConvertedFiles(true) }
function onFileAdded() { loadConvertedFiles(true) }
function onFileRemoved() { loadConvertedFiles(true) }

onUnmounted(() => {
  stopEmbeddingPolling()
})
</script>

<style scoped>
/* -------------------------------------------------------
   Enterprise UI styling
------------------------------------------------------- */

.main-view { padding: 16px 0; }

/* Header */
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  padding: 8px 4px 16px 4px;
}

.title {
  margin: 0;
  font-size: 1.35rem;
  font-weight: 850;
  color: var(--text-heading);
}

.subtitle {
  margin: 6px 0 0 0;
  color: var(--text-secondary);
  font-size: 0.95rem;
  line-height: 1.35;
  max-width: 72ch;
}

.session-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 999px;
  background: var(--surface-base);
  border: 1px solid var(--border-light);
  color: var(--text-secondary);
  font-size: 0.85rem;
  white-space: nowrap;
}
.session-chip.muted { opacity: 0.9; }

.dot { width: 8px; height: 8px; border-radius: 999px; }
.dot-success { background: var(--success, #2e7d32); }
.dot-muted { background: var(--border-medium, #9aa4b2); }

/* Tabs */
.tabs {
  display: flex;
  gap: 8px;
  padding: 0 4px 16px 4px;
  flex-wrap: wrap;
}

.tab {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid var(--border-light);
  background: var(--surface-base);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s ease;
}
.tab:hover {
  border-color: var(--brand-primary);
  background: var(--surface-hover);
  color: var(--text-primary);
}
.tab.active {
  border-color: var(--brand-primary);
  background: linear-gradient(145deg, var(--surface-base), var(--surface-elevated));
  color: var(--text-primary);
  box-shadow: var(--shadow-md);
}
.tab:focus-visible {
  outline: 2px solid var(--brand-primary);
  outline-offset: 2px;
}
.tab-icon { opacity: 0.95; }
.tab-label { font-weight: 700; }

/* Cards */
.card {
  background: var(--surface-elevated);
  border: 1px solid var(--border-light);
  border-radius: 14px;
  padding: 18px;
  box-shadow: var(--shadow-sm);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 14px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border-light);
}

.card-title {
  margin: 0;
  font-size: 1.1rem;
  font-weight: 850;
  color: var(--text-heading);
}
.card-subtitle {
  margin: 6px 0 0 0;
  font-size: 0.92rem;
  color: var(--text-secondary);
}

.header-actions { display: flex; gap: 10px; flex-wrap: wrap; }

/* Info banner */
.info-banner {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  padding: 14px;
  border-radius: 12px;
  border: 1px solid var(--border-light);
  background: linear-gradient(145deg, var(--surface-base), var(--surface-elevated));
  margin-bottom: 16px;
}
.badge {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 0.8rem;
  font-weight: 800;
  color: var(--text-primary);
  background: var(--brand-subtle);
  border: 1px solid var(--border-light);
  margin-bottom: 8px;
}
.steps {
  margin: 0;
  padding-left: 18px;
  color: var(--text-secondary);
  font-size: 0.92rem;
}
.steps li { margin: 4px 0; }
.hint { margin: 0; color: var(--text-secondary); font-size: 0.9rem; }

/* Sections */
.section { margin-top: 18px; }
.section-head { margin-bottom: 10px; }
.section-title {
  margin: 0;
  font-size: 1rem;
  font-weight: 850;
  color: var(--text-heading);
}
.section-help {
  margin: 6px 0 0 0;
  color: var(--text-secondary);
  font-size: 0.9rem;
}

/* Form layout */
.settings-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(220px, 1fr));
  gap: 14px;
  margin-top: 12px;
}
@media (max-width: 980px) { .settings-grid { grid-template-columns: 1fr; } }

.field {
  background: var(--surface-base);
  border: 1px solid var(--border-light);
  border-radius: 12px;
  padding: 12px;
}
.field.slim { padding: 10px 12px; }

.label {
  display: block;
  font-weight: 800;
  color: var(--text-primary);
  font-size: 0.9rem;
  margin-bottom: 8px;
}

.field-help {
  margin: 8px 0 0 0;
  color: var(--text-tertiary);
  font-size: 0.85rem;
  line-height: 1.3;
}

.segmented {
  display: inline-flex;
  gap: 8px;
  flex-wrap: wrap;
}
.seg-option {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 10px;
  border: 1px solid var(--border-light);
  background: var(--surface-elevated);
  cursor: pointer;
}
.seg-option input { accent-color: var(--brand-primary); }

/* Performance pill */
.perf-pill {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 999px;
  background: var(--color-success-bg, #e8f5e9);
  border: 1px solid var(--color-success, #2e7d32);
  color: #1f5d24;
  font-size: 0.88rem;
  font-weight: 700;
}

.input,
.select {
  width: 100%;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid var(--border-medium);
  background: var(--surface-elevated);
  color: var(--text-primary);
}
.input:focus-visible,
.select:focus-visible {
  outline: 2px solid var(--brand-primary);
  outline-offset: 2px;
}

.actions-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-top: 12px;
}

.muted-text { color: var(--text-tertiary); font-size: 0.88rem; }

/* Upload card */
.upload-card {
  background: var(--surface-base);
  border: 1px solid var(--border-light);
  border-radius: 14px;
  padding: 14px;
  margin-top: 10px;
}

.summary {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  margin-top: 12px;
}
.summary-item {
  flex: 1;
  min-width: 180px;
  border-radius: 12px;
  border: 1px solid var(--border-light);
  background: var(--surface-elevated);
  padding: 10px 12px;
}
.summary-label { font-size: 0.8rem; color: var(--text-tertiary); }
.summary-value { font-size: 1.05rem; font-weight: 900; color: var(--text-heading); margin-top: 2px; }

.cta-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-top: 14px;
}

/* Status banner */
.status-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 12px;
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid var(--border-light);
  background: var(--surface-elevated);
}
.status-text {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.status-embedding {
  border-color: var(--color-info, #1976d2);
  background: var(--color-info-bg, #e8f4fd);
  color: #0d3c73;
}
.status-done {
  border-color: var(--color-success, #2e7d32);
  background: var(--color-success-bg, #e8f5e9);
  color: #1f5d24;
}
.status-error {
  border-color: var(--color-error, #c62828);
  background: var(--color-error-bg, #fce4ec);
  color: #7b1b1b;
}

.status-info {
  border-color: var(--color-info, #1976d2);
  background: rgba(25, 118, 210, 0.10);
  color: #0d3c73;
}

/* Downloads */
.download-bar {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  align-items: center;
  margin-top: 10px;
}

/* stacked browse layout */
.browse-stack {
  display: flex;
  flex-direction: column;
  gap: 14px;
  margin-top: 12px;
}

.card-sub {
  background: var(--surface-base);
  border: 1px solid var(--border-light);
  border-radius: 14px;
  padding: 14px;
}

.sub-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  margin-bottom: 12px;
}

.sub-title {
  margin: 0;
  font-weight: 900;
  color: var(--text-heading);
}

.sub-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.pill {
  display: inline-flex;
  align-items: center;
  padding: 6px 10px;
  border-radius: 999px;
  background: var(--surface-elevated);
  border: 1px solid var(--border-light);
  font-size: 0.85rem;
  color: var(--text-secondary);
}

/* Listbox */
.listbox { position: relative; }
.listbox-button {
  width: 100%;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid var(--border-medium);
  background: var(--surface-elevated);
  cursor: pointer;
}
.chev { color: var(--text-tertiary); }

.listbox-options {
  position: absolute;
  z-index: 50;
  width: 100%;
  max-height: 320px;
  overflow: auto;
  margin-top: 6px;
  padding: 0;
  list-style: none;
  border-radius: 12px;
  border: 1px solid var(--border-medium);
  background: var(--surface-elevated);
  box-shadow: var(--shadow-lg);
}
.listbox-search {
  padding: 10px;
  border-bottom: 1px solid var(--border-light);
  position: sticky;
  top: 0;
  background: var(--surface-elevated);
}
.listbox-option {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  cursor: pointer;
  border-bottom: 1px solid var(--border-light);
}
.listbox-option:last-child { border-bottom: none; }
.listbox-option.active { background: var(--brand-subtle); }
.listbox-option.selected .name { font-weight: 900; }
.tick {
  width: 18px;
  display: inline-flex;
  justify-content: center;
  color: var(--brand-primary);
  font-weight: 900;
}
.name { flex: 1; color: var(--text-primary); }
.meta { font-size: 0.8rem; color: var(--text-tertiary); }
.empty {
  padding: 12px;
  text-align: center;
  color: var(--text-tertiary);
  font-size: 0.9rem;
}

/* Transitions */
.listbox-enter-active,
.listbox-leave-active {
  transition: opacity 0.12s ease, transform 0.12s ease;
}
.listbox-enter-from,
.listbox-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

/* Preview meta + edit banner */
.preview-meta {
  display: flex;
  gap: 10px;
  margin: 10px 0 12px 0;
}
.meta-item {
  flex: 1;
  min-width: 140px;
  border-radius: 12px;
  border: 1px solid var(--border-light);
  background: var(--surface-elevated);
  padding: 10px 12px;
}
.meta-k { font-size: 0.8rem; color: var(--text-tertiary); }
.meta-v { font-size: 1.0rem; font-weight: 900; color: var(--text-heading); }

.edit-banner {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border-radius: 12px;
  background: var(--surface-elevated);
  border: 1px solid var(--border-light);
  margin-bottom: 10px;
}

.table-hint {
  display: flex;
  justify-content: flex-end;
  padding: 0 2px 8px 2px;
}

.table-wrap {
  max-height: 520px;
  overflow: auto;
  border-radius: 12px;
  border: 1px solid var(--border-light);
  background: var(--surface-elevated);
  -webkit-overflow-scrolling: touch;
}

.table {
  width: max-content;
  min-width: 100%;
  border-collapse: collapse;
  font-size: 0.9rem;
}

.table thead th {
  position: sticky;
  top: 0;
  z-index: 2;
  background: var(--surface-base);
  border-bottom: 1px solid var(--border-light);
  padding: 10px;
  text-align: left;
  font-weight: 900;
  color: var(--text-primary);
  white-space: nowrap;
}

.table tbody td {
  border-bottom: 1px solid var(--border-light);
  padding: 8px 10px;
  color: var(--text-secondary);
  vertical-align: top;
  white-space: nowrap;
}

.table tbody tr:nth-child(even) { background: var(--surface-hover); }

.cell {
  width: 100%;
  min-width: 140px;
  padding: 6px 8px;
  border-radius: 10px;
  border: 1px solid var(--border-medium);
  background: var(--surface-base);
}

.empty-state {
  border: 1px dashed var(--border-medium);
  border-radius: 12px;
  padding: 18px;
  text-align: center;
  background: var(--surface-base);
  color: var(--text-secondary);
}
.empty-title { font-weight: 900; color: var(--text-primary); }
.empty-text { margin-top: 6px; font-size: 0.9rem; color: var(--text-tertiary); }

.download-row {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 12px;
}

/* Buttons */
.btn {
  border-radius: 10px;
  border: 1px solid var(--border-medium);
  padding: 10px 12px;
  cursor: pointer;
  font-weight: 800;
  transition: transform 0.08s ease, box-shadow 0.15s ease, filter 0.15s ease;
}
.btn:disabled { opacity: 0.55; cursor: not-allowed; }
.btn:active:not(:disabled) { transform: translateY(1px); }

.btn-primary {
  background: var(--brand-primary);
  border-color: var(--brand-primary);
  color: #0b0b0b;
  box-shadow: var(--shadow-sm);
}
.btn-primary:hover:not(:disabled) { filter: brightness(1.05); box-shadow: var(--shadow-md); }

.btn-secondary { background: var(--surface-elevated); color: var(--text-primary); }
.btn-secondary:hover:not(:disabled) { background: var(--surface-hover); }

.btn-warning {
  background: linear-gradient(135deg, var(--brand-primary) 0%, var(--brand-secondary) 100%);
  border-color: var(--brand-primary);
  color: #0b0b0b;
}
.btn-warning:hover:not(:disabled) { filter: brightness(1.08); box-shadow: var(--shadow-md); }

.btn-sm { padding: 7px 10px; font-size: 0.85rem; border-radius: 10px; }

/* Spinner */
.spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid transparent;
  border-top-color: currentColor;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin-right: 8px;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* AI Card */
.ai-card {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 14px;
  padding: 14px;
  border-radius: 14px;
  border: 1px solid var(--border-light);
  background: linear-gradient(145deg, var(--surface-base), var(--surface-elevated));
}
.ai-actions {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}
</style>