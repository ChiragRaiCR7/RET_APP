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
            <label class="label">Edit Mode</label>
            <EditModeToggle v-model="workflow.editMode" />
            <p class="field-help">
              Make session-only changes to outputs, then download the modified package.
            </p>
          </div>
          <div class="field">
            <label class="label">Preview Mode</label>
            <label class="toggle-inline">
              <input
                type="checkbox"
                :checked="simplifiedPreview"
                @change="onSimplifiedToggle(($event.target as HTMLInputElement).checked)"
                style="accent-color: var(--brand-primary)"
              />
              <span>Simplified</span>
            </label>

            <label v-if="simplifiedPreview" class="toggle-inline nested-toggle">
              <input
                type="checkbox"
                :checked="hideLowValueColumns"
                @change="hideLowValueColumns = ($event.target as HTMLInputElement).checked"
                style="accent-color: var(--brand-primary)"
              />
              <span>Hide low-value columns</span>
            </label>

            <p class="field-help">
              Keep important columns first and move low-value columns to the end.
              Works in both Preview and Edit Mode.
            </p>
            <p v-if="simplifiedPreview" class="field-help">
              Low-value columns include mostly empty, constant, trivial boolean, and low-variance flag data.
            </p>
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
            <span class="muted-text">High-performance mode enabled — optimized for large archives.</span>
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
          <div class="field slim">
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
          </div>

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
              <div v-if="selectedGroups.length" class="selected-summary" aria-label="Selected groups summary">
                <span v-for="group in selectedGroups" :key="group" class="selected-chip">{{ group }}</span>
              </div>
              <p class="field-help">Use selection to narrow results and focus on relevant groups.</p>
            </div>

            <!-- Active group -->
            <div class="field slim">
              <label class="label">Active group</label>
              <select v-model="activeGroup" class="select" @change="loadGroupFiles">
                <option value="">Select a group…</option>
                <option v-for="g in activeGroupOptions" :key="g.name" :value="g.name">
                  {{ g.name }}
                </option>
              </select>
              <p class="field-help">Choose a group from the current selection to load its files and preview.</p>
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
                  {{ f.filename }}
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

            <div
              v-if="preview && simplifiedPreview && (preview.headers?.length || 0) > 0"
              class="simplified-summary"
              role="status"
              aria-live="polite"
            >
              <div class="muted-text">
                Showing <strong>{{ visibleColumnIndexes.length }}</strong> of
                <strong>{{ preview.headers?.length || 0 }}</strong> columns.
                <span v-if="hideLowValueColumns && hiddenLowValueCount > 0">
                  {{ hiddenLowValueCount }} low-value column(s) hidden.
                </span>
              </div>
              <button
                class="btn btn-sm btn-secondary"
                type="button"
                @click="hideLowValueColumns = !hideLowValueColumns"
                :disabled="lowValueColumnCount === 0"
              >
                {{ hideLowValueColumns ? `Show low-value columns (${lowValueColumnCount})` : 'Hide low-value columns' }}
              </button>
            </div>

            <div v-if="preview && simplifiedPreview && lowValueColumnDetails.length" class="low-value-guide">
              <details>
                <summary>
                  Low-value column details ({{ lowValueColumnCount }})
                </summary>
                <ul>
                  <li v-for="col in lowValueColumnDetails" :key="`lv-${col.idx}`">
                    <code>{{ col.header }}</code> — {{ formatLowValueReason(col.reason) }}
                  </li>
                </ul>
              </details>
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

                <div class="field slim grid-search">
                  <label class="label">Column filter</label>
                  <input
                    v-model="valueFilter"
                    class="input"
                    :disabled="workflow.editMode"
                    placeholder="Search column names…"
                    aria-label="Search column names"
                  />
                  <select
                    v-model="selectedColumnFilter"
                    class="select"
                    :disabled="workflow.editMode"
                    aria-label="Select visible column"
                    style="margin-top: 8px;"
                  >
                    <option value="">All matching columns</option>
                    <option v-for="col in filteredColumnOptions" :key="`col-${col.idx}`" :value="col.idx">
                      {{ col.header }}
                    </option>
                  </select>
                  <p class="field-help">Searches column names only. Row values stay untouched.</p>
                </div>
              </div>

              <div class="grid-right">
                <button class="btn btn-sm btn-secondary" @click="clearTableControls" :disabled="workflow.editMode">
                  Clear filters
                </button>
                <button class="btn btn-sm btn-secondary" @click="selectedColumnFilter = ''" :disabled="workflow.editMode">
                  Show all columns
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
              <span v-if="workflow.editMode" class="muted-text">
                Edit Mode on: sorting, search, and column filters are disabled to keep row mapping safe.
              </span>
              <span v-else class="muted-text">
                Tip: Click a column header to sort. Column finder only narrows visible column names.
              </span>
            </div>

            <!-- ✅ Preview table -->
            <div v-if="preview && visibleColumnIndexes.length" class="table-wrap" aria-label="Preview table">
              <table class="table">
                <thead>
                  <tr>
                    <th
                      v-for="colIdx in visibleColumnIndexes"
                      :key="colIdx"
                      class="sortable"
                      :class="{ sorted: sortCol === colIdx, 'low-value': isLowValueColumn(colIdx) }"
                      @click="toggleSort(colIdx)"
                      :title="columnTitle(colIdx)"
                    >
                      <div class="th-inner">
                        <span>{{ preview.headers[colIdx] }}</span>
                        <span class="sort-ind" aria-hidden="true">
                          <template v-if="sortCol === colIdx">
                            {{ sortDir === 'asc' ? '▲' : '▼' }}
                          </template>
                          <template v-else>⇅</template>
                        </span>
                      </div>
                    </th>
                  </tr>
                </thead>

                <tbody>
                  <tr v-for="(row, rowIdx) in displayRows" :key="rowIdx">
                    <td v-for="colIdx in visibleColumnIndexes" :key="colIdx">
                      <template v-if="workflow.editMode">
                        <!-- In edit mode we keep using original preview rows (no sorting/filtering). -->
                        <input
                          v-model="preview!.rows[rowIdx]![colIdx]"
                          class="cell"
                          @change="markCellChanged(rowIdx, colIdx)"
                          :aria-label="`Edit row ${rowIdx + 1}, column ${preview.headers?.[colIdx] || colIdx + 1}`"
                        />
                      </template>
                      <template v-else>
                        {{ formatCellValue(row[colIdx]) }}
                      </template>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div v-else-if="preview && !visibleColumnIndexes.length" class="empty-state">
              <div class="empty-title">No columns matched</div>
              <div class="empty-text">Try a broader column name search or show all columns.</div>
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
          <p class="card-subtitle">5-layer organization hierarchy derived from converted CSV contents.</p>
        </div>
      </div>
      <BusinessStructurePanel
        :session-id="workflow.sessionId"
        :converted="workflow.converted"
        :business-structure="businessStructure"
        :loading-structure="loadingBusinessStructure"
        @refresh="fetchBusinessStructure"
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

<script setup lang="ts">
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
import api, { errorBody, longApi, pollJob } from '@/utils/api'
import { groupEquals } from '@/utils/groups'
import { useToastStore } from '@/stores/toastStore'
import type {
  BusinessStructureResponse,
  ConversionFileEntry,
  ConversionFilesResponse,
  ConversionGroupEntry,
  FilePreviewResponse,
  ScannedFileEntry
} from '@/types/api'

interface ScannedGroup {
  name: string
  file_count: number
  size: number
}

interface UploadedScan {
  sessionId?: string
  session_id?: string
  uploaded_filename?: string
  original_filename?: string
  filename?: string
  name?: string
  files?: ScannedFileEntry[]
  scanned_files?: ScannedFileEntry[]
  scannedFiles?: ScannedFileEntry[]
  groups?: { name: string; file_count?: number; fileCount?: number; size?: number }[]
  file_count?: number | null
  xml_count?: number
  xmlCount?: number
  summary?: { totalSize?: number }
}

interface CellEdit {
  row_index: number
  column: string
  value: string | undefined
}

/** Result of the async conversion job (GET /jobs/{id} -> result). */
interface ConversionJobResult {
  error?: string
  message?: string
  stats?: { success?: number }
  embedding_status?: string
  embedding_error?: string
  embedding?: string | { status?: string; state?: string; message?: string }
}

interface AutoEmbedProgress {
  status?: string
  processed?: number
  total?: number
  error?: string | null
  message?: string
}

type EmbeddingUiStatus = 'embedding' | 'done' | 'error' | null

const EMBED_PROGRESS_POLL_MS = 3000
// Give up on progress checks after this many consecutive failures (e.g. server restarted).
const EMBED_PROGRESS_MAX_ERRORS = 10

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
  sessionId: null as string | null,
  outputFormat: 'csv',
  editMode: false,
  fastParser: true,
  uploadedFiles: [] as File[],
  uploadedFilename: '',
  scannedFiles: [] as ScannedFileEntry[],
  scannedGroups: [] as ScannedGroup[],
  scanSummary: null as { totalGroups: number; totalFiles: number; totalSize: number | string } | null,
  converted: false
})

const converting = ref(false)
const embeddingStatus = ref<EmbeddingUiStatus>(null)
const embeddingProgress = ref<AutoEmbedProgress | null>(null)
const embeddingMessage = ref('')

const groupSearch = ref('')
const selectedGroups = ref<string[]>([])
const activeGroup = ref('')
const activeFile = ref('')
const preview = ref<FilePreviewResponse | null>(null)
const groupFiles = ref<ConversionFileEntry[]>([])
const pendingCellEdits = ref(new Map<string, CellEdit>())
const simplifiedPreview = ref(false)
const hideLowValueColumns = ref(true)

const conversionData = reactive({
  groups: [] as ConversionGroupEntry[],
  files: [] as ConversionFileEntry[],
  totalFiles: 0
})

const businessStructure = ref<BusinessStructureResponse | null>(null)
const loadingBusinessStructure = ref(false)

const indexedGroups = ref<string[]>([])

// Computed helpers
const filteredGroups = computed(() => {
  if (!groupSearch.value) return conversionData.groups
  const search = groupSearch.value.toLowerCase()
  return conversionData.groups.filter(g => (g.name || '').toLowerCase().includes(search))
})

const activeGroupOptions = computed(() => {
  if (!selectedGroups.value.length) return conversionData.groups
  const allowed = new Set(selectedGroups.value)
  return conversionData.groups.filter(g => allowed.has(g.name))
})

const filteredColumnOptions = computed(() => {
  const headers = preview.value?.headers || []
  const q = valueFilter.value.trim().toLowerCase()

  return headers
    .map((header, idx) => ({ header, idx }))
    .filter(col => !q || String(col.header || '').toLowerCase().includes(q))
})

const lowValueColumnIndexes = computed(() => {
  const meta = preview.value?.column_meta || []
  if (!Array.isArray(meta) || !meta.length) return []
  return meta
    .map((entry, idx) => ({ entry, idx }))
    .filter(({ entry }) => entry?.classification === 'low_value')
    .map(({ idx }) => idx)
})

const lowValueColumnCount = computed(() => lowValueColumnIndexes.value.length)

const lowValueColumnDetails = computed(() => {
  const headers = preview.value?.headers || []
  const meta = preview.value?.column_meta || []
  if (!Array.isArray(meta) || !meta.length) return []

  return meta
    .map((entry, idx) => ({
      idx,
      header: headers[idx] || `Column ${idx + 1}`,
      classification: entry?.classification,
      reason: entry?.reason || ''
    }))
    .filter(entry => entry.classification === 'low_value')
})

const hiddenLowValueCount = computed(() => {
  if (!simplifiedPreview.value || !hideLowValueColumns.value) return 0
  return lowValueColumnCount.value
})

const visibleColumnIndexes = computed(() => {
  const headers = preview.value?.headers || []
  if (!headers.length) return []

  if (selectedColumnFilter.value !== '') {
    const idx = Number(selectedColumnFilter.value)
    return Number.isInteger(idx) && idx >= 0 && idx < headers.length ? [idx] : []
  }

  // Base index set (filtered by column name search or all)
  let baseIndexes: number[]
  if (!valueFilter.value.trim()) {
    baseIndexes = headers.map((_, idx) => idx)
  } else {
    baseIndexes = filteredColumnOptions.value.map(col => col.idx)
  }

  // In simplified mode, reorder so high-value columns come first
  if (simplifiedPreview.value && preview.value?.simplified_order) {
    const orderSet = new Set(baseIndexes)
    const ordered = preview.value.simplified_order.filter(idx => orderSet.has(idx))
    if (hideLowValueColumns.value) {
      const lowSet = new Set(lowValueColumnIndexes.value)
      return ordered.filter(idx => !lowSet.has(idx))
    }
    return ordered
  }

  return baseIndexes
})

function isLowValueColumn(colIdx: number): boolean {
  if (!simplifiedPreview.value) return false
  const meta = preview.value?.column_meta
  return !!meta && meta[colIdx]?.classification === 'low_value'
}

function columnTitle(colIdx: number): string {
  const meta = preview.value?.column_meta?.[colIdx]
  const reasonLabel = formatLowValueReason(meta?.reason)

  if (simplifiedPreview.value && meta?.classification === 'low_value') {
    if (workflow.editMode) {
      return `Low-value column (${reasonLabel}). Sorting disabled in Edit Mode.`
    }
    return `Low-value column (${reasonLabel}). Click to sort.`
  }

  if (workflow.editMode) return 'Sorting disabled in Edit Mode'

  return 'Click to sort'
}

function formatLowValueReason(reason: string | undefined): string {
  const reasons: Record<string, string> = {
    mostly_empty: 'mostly empty values',
    all_same: 'same value in all rows',
    trivial_boolean: 'boolean-like flag values',
    low_variance_flag: 'low-variance small numeric flag'
  }
  return (reason && reasons[reason]) || reason || 'low significance pattern'
}

function onSimplifiedToggle(enabled: boolean) {
  simplifiedPreview.value = enabled
  if (enabled) {
    hideLowValueColumns.value = true
  }
  resetTableControls()
}

const pendingChangesCount = computed(() => pendingCellEdits.value.size)

const canConvert = computed(() => {
  return !!workflow.sessionId && workflow.scannedGroups.length > 0 && !converting.value
})

watch(() => workflow.editMode, (enabled) => {
  if (!enabled) pendingCellEdits.value = new Map()
  // Reset table controls when toggling edit mode
  resetTableControls()
})

watch(selectedGroups, async () => {
  const options = activeGroupOptions.value

  if (!options.length) {
    activeGroup.value = ''
    activeFile.value = ''
    preview.value = null
    groupFiles.value = []
    return
  }

  const stillValid = options.some(g => groupEquals(g.name, activeGroup.value))
  if (!stillValid) {
    activeGroup.value = options[0]!.name
    await loadGroupFiles()
  }
}, { deep: true })

/** -----------------------------
 * ✅ Excel-like table controls (search/sort/filter)
 * ------------------------------ */
const tableSearch = ref('')
const selectedColumnFilter = ref('')
const valueFilter = ref('')
const sortCol = ref<number | null>(null)
const sortDir = ref<'asc' | 'desc'>('asc')

function resetTableControls() {
  tableSearch.value = ''
  selectedColumnFilter.value = ''
  valueFilter.value = ''
  sortCol.value = null
  sortDir.value = 'asc'
}

function clearTableControls() {
  if (workflow.editMode) return
  resetTableControls()
}

function toggleSort(colIdx: number) {
  if (workflow.editMode) return
  if (sortCol.value === colIdx) {
    sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortCol.value = colIdx
    sortDir.value = 'asc'
  }
}

function isNumeric(v: unknown): boolean {
  if (v === null || v === undefined) return false
  const s = String(v).trim()
  if (!s) return false
  return !Number.isNaN(Number(s))
}

function compareCells(a: unknown, b: unknown): number {
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

  const q = tableSearch.value.trim().toLowerCase()

  // apply row search only — column controls now search header names, not cell values
  let filtered = rows.filter(r => {
    if (q) {
      const hay = (r || []).join(' ').toLowerCase()
      if (!hay.includes(q)) return false
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
function formatCellValue(value: unknown, maxLen = 50): string {
  if (value === null || value === undefined) return ''
  const str = String(value)
  return str.length > maxLen ? str.substring(0, maxLen) + '…' : str
}

function onFilesAdded(filesList: File[]) {
  workflow.uploadedFiles.push(...filesList)
  if (!workflow.uploadedFilename && filesList?.length) {
    workflow.uploadedFilename = filesList[0]?.name || ''
  }
}

/**
 * FileUploader emits scan result payload.
 * Supports both sessionId and session_id.
 */
function onUploaded(data: UploadedScan | File[]) {
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

    const payload = await pollJob<ConversionJobResult>(jobId, {
      intervalMs: 1500,
      timeoutMs: 60 * 60 * 1000
    })

    if (payload && !payload.error) {
      workflow.converted = true
      toast.success(`Conversion complete. ${payload.stats?.success || 0} file(s) converted.`)

      await loadConvertedFiles(true)
      handleEmbeddingMetadata(payload)
      fetchBusinessStructure()
    } else {
      throw new Error(payload?.message || payload?.error || 'Conversion failed')
    }
  } catch (e) {
    toast.error('Conversion failed: ' + (errorBody(e)?.detail || (e as Error).message))
  } finally {
    converting.value = false
  }
}

let embeddingPollTimer: ReturnType<typeof setInterval> | null = null

function stopEmbeddingPolling() {
  if (embeddingPollTimer) {
    clearInterval(embeddingPollTimer)
    embeddingPollTimer = null
  }
}

function resolveEmbeddingStatus(payload: ConversionJobResult = {}): string {
  const top = payload?.embedding_status
  const embedding = typeof payload?.embedding === 'object' ? payload.embedding : undefined
  const nested = embedding?.status || embedding?.state
  const legacy = typeof payload?.embedding === 'string' ? payload.embedding : ''
  return String(top || nested || legacy || '').toLowerCase()
}

function handleEmbeddingMetadata(payload: ConversionJobResult = {}) {
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
    const embedding = typeof payload?.embedding === 'object' ? payload.embedding : undefined
    embeddingMessage.value = embedding?.message || payload?.embedding_error || 'Embedding did not complete.'
    return
  }

  if (status === 'no_eligible_groups' || status === 'no_inventory' || status === 'disabled') {
    // Silent — do not display any banner for these states
    embeddingStatus.value = null
    embeddingMessage.value = ''
    return
  }

  if (status === 'suppressed' || status === 'stopped') {
    embeddingStatus.value = null
    embeddingMessage.value = ''
    return
  }

  // Unknown status: keep UI non-disruptive.
  embeddingStatus.value = null
  embeddingMessage.value = ''
}

function pollEmbeddingStatus() {
  embeddingStatus.value = 'embedding'
  stopEmbeddingPolling()

  let consecutiveErrors = 0
  embeddingPollTimer = setInterval(async () => {
    try {
      const res = await api.get<AutoEmbedProgress>(`/v2/ai/auto-embed/progress/${workflow.sessionId}`)
      consecutiveErrors = 0
      embeddingProgress.value = res.data

      const status = String(res?.data?.status || '').toLowerCase()

      if (status === 'failed') {
        embeddingStatus.value = 'error'
        embeddingMessage.value = res?.data?.error || res?.data?.message || 'Embedding failed.'
        stopEmbeddingPolling()
        return
      }

      if (
        status === 'disabled' ||
        status === 'no_eligible_groups' ||
        status === 'no_inventory' ||
        status === 'suppressed' ||
        status === 'stopped' ||
        status === 'idle'
      ) {
        // Silent — stop polling without showing a banner
        embeddingStatus.value = null
        embeddingMessage.value = ''
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
    } catch (e) {
      consecutiveErrors += 1
      console.warn('Embedding progress check failed:', (e as Error).message)
      if (consecutiveErrors >= EMBED_PROGRESS_MAX_ERRORS) {
        stopEmbeddingPolling()
        embeddingStatus.value = 'error'
        embeddingMessage.value = 'Lost contact with the embedding job. Check the AI tab for its status.'
      }
    }
  }, EMBED_PROGRESS_POLL_MS)
}

/**
 * Load output listing; use longApi for large sessions
 */
async function loadConvertedFiles(useLong = false) {
  if (!workflow.sessionId) return

  try {
    const client = useLong ? longApi : api
    const res = await client.get<ConversionFilesResponse>(`/conversion/files/${workflow.sessionId}`, {
      timeout: useLong ? 15 * 60 * 1000 : 30_000
    })

    conversionData.groups = res.data.groups || []
    conversionData.files = res.data.files || []
    conversionData.totalFiles = res.data.total_files || 0

    if (conversionData.groups.length > 0) {
      activeGroup.value = conversionData.groups[0]!.name
      await loadGroupFiles()
    }
  } catch (e) {
    console.error('Failed to load converted files:', e)
  }
}

async function fetchBusinessStructure() {
  if (!workflow.sessionId || !workflow.converted) return
  loadingBusinessStructure.value = true
  try {
    const res = await api.get<BusinessStructureResponse>(`/conversion/business-structure/${workflow.sessionId}`)
    businessStructure.value = res.data
  } catch (e) {
    console.error('Failed to load business structure:', e)
    businessStructure.value = null
  } finally {
    loadingBusinessStructure.value = false
  }
}

async function loadGroupFiles() {
  if (!activeGroup.value) return

  groupFiles.value = conversionData.files.filter(f => groupEquals(f.group, activeGroup.value))

  if (groupFiles.value.length > 0) {
    activeFile.value = groupFiles.value[0]!.filename
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
    const res = await api.get<FilePreviewResponse>(`/conversion/preview/${workflow.sessionId}/${encodeURIComponent(activeFile.value)}`, {
      params: { max_rows: 100 }
    })
    preview.value = res.data
    pendingCellEdits.value = new Map()

    resetTableControls()
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

function markCellChanged(rowIdx: number, colIdx: number) {
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
    toast.error('Failed to save: ' + (errorBody(e)?.detail || (e as Error).message))
  }
}

async function downloadAll() {
  if (!workflow.sessionId) return
  try {
    const res = await api.get(`/conversion/download/${workflow.sessionId}`, { responseType: 'blob' })
    downloadBlob(res.data, 'converted_output.zip')
    toast.success('Download started.')
  } catch (e) {
    toast.error('Download failed: ' + (errorBody(e)?.detail || (e as Error).message))
  }
}

async function downloadModifiedZip() {
  if (!workflow.sessionId || !workflow.editMode) return
  try {
    const res = await api.get(`/conversion/download-modified/${workflow.sessionId}`, { responseType: 'blob' })
    downloadBlob(res.data, 'modified_output.zip')
    toast.success('Download started.')
  } catch (e) {
    toast.error('Download failed: ' + (errorBody(e)?.detail || (e as Error).message))
  }
}

async function downloadPatchLog() {
  toast.info('Change log download is not available yet.')
}

async function downloadCurrentFile() {
  if (!activeFile.value || !workflow.sessionId) return
  try {
    const res = await api.get(`/conversion/download-file/${workflow.sessionId}/${encodeURIComponent(activeFile.value)}`, {
      responseType: 'blob'
    })
    // download file with its real name (extension needed for OS)
    downloadBlob(res.data, activeFile.value)
  } catch (e) {
    toast.error('Download failed: ' + (errorBody(e)?.detail || (e as Error).message))
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
    toast.error('Download failed: ' + (errorBody(e)?.detail || (e as Error).message))
  }
}

function downloadBlob(data: BlobPart, filename: string) {
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
    toast.error('Cleanup failed: ' + (errorBody(e)?.detail || (e as Error).message))
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

function onGroupsIndexed(groups: string[]) {
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

.main-view {
  padding: 16px 0 28px;
  color: var(--text-body);
}

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
  background: linear-gradient(180deg, var(--surface-base), var(--surface-raised));
  border: 1px solid var(--border-medium);
  color: var(--text-body);
  font-size: 0.85rem;
  white-space: nowrap;
  box-shadow: var(--shadow-xs);
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
  padding: 11px 14px;
  border-radius: 12px;
  border: 1px solid var(--border-medium);
  background: linear-gradient(180deg, var(--surface-base), var(--surface-raised));
  color: var(--text-body);
  cursor: pointer;
  box-shadow: var(--shadow-xs);
  transition: transform var(--transition-fast), box-shadow var(--transition-fast), border-color var(--transition-fast), background var(--transition-fast), color var(--transition-fast);
}
.tab:hover {
  border-color: var(--brand-primary);
  background: var(--surface-hover);
  color: var(--text-heading);
  box-shadow: var(--shadow-sm);
  transform: translateY(-1px);
}
.tab.active {
  border-color: var(--brand-primary);
  background: linear-gradient(145deg, color-mix(in srgb, var(--brand-subtle), var(--surface-base) 30%), var(--surface-elevated));
  color: var(--text-heading);
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
  background: linear-gradient(180deg, color-mix(in srgb, var(--surface-elevated), var(--bg-primary) 8%), var(--surface-elevated));
  border: 1px solid var(--border-light);
  border-radius: 18px;
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
  background: linear-gradient(145deg, color-mix(in srgb, var(--brand-subtle), var(--surface-base) 18%), var(--surface-elevated));
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
  background: linear-gradient(180deg, var(--surface-base), var(--surface-raised));
  border: 1px solid var(--border-light);
  border-radius: 14px;
  padding: 12px;
  box-shadow: var(--shadow-xs);
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
  border: 1px solid var(--border-medium);
  background: var(--surface-elevated);
  cursor: pointer;
  box-shadow: var(--shadow-xs);
}
.seg-option input { accent-color: var(--brand-primary); }

/* Input fields */

.input,
.select {
  width: 100%;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid var(--border-medium);
  background: var(--surface-elevated);
  color: var(--text-body);
  box-shadow: inset 0 1px 0 color-mix(in srgb, var(--surface-hover), transparent 35%);
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
  background: linear-gradient(180deg, var(--surface-base), var(--surface-raised));
  border: 1px solid var(--border-light);
  border-radius: 16px;
  padding: 14px;
  margin-top: 10px;
  box-shadow: var(--shadow-sm);
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
  background: linear-gradient(180deg, var(--surface-elevated), var(--surface-raised));
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
  border-color: var(--info-border);
  background: var(--info-bg);
  color: var(--info);
}
.status-done {
  border-color: var(--success-border);
  background: var(--success-bg);
  color: var(--success);
}
.status-error {
  border-color: var(--error-border);
  background: var(--error-bg);
  color: var(--error);
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
  background: linear-gradient(180deg, var(--surface-base), var(--surface-raised));
  border: 1px solid var(--border-light);
  border-radius: 16px;
  padding: 14px;
  box-shadow: var(--shadow-xs);
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
  color: var(--text-body);
  cursor: pointer;
  box-shadow: inset 0 1px 0 color-mix(in srgb, var(--surface-hover), transparent 35%);
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

.selected-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}

.selected-chip {
  display: inline-flex;
  align-items: center;
  padding: 0.32rem 0.68rem;
  border-radius: 999px;
  background: var(--brand-subtle);
  border: 1px solid color-mix(in srgb, var(--brand-primary), var(--border-light) 65%);
  color: var(--text-body);
  font-size: 0.82rem;
  font-weight: 700;
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

.simplified-summary {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin: 8px 0 12px;
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid color-mix(in srgb, var(--brand-primary), var(--border-light) 62%);
  background: color-mix(in srgb, var(--brand-subtle), var(--surface-elevated) 35%);
}

.low-value-guide {
  margin: 0 0 12px;
}

.low-value-guide details {
  border-radius: 12px;
  border: 1px solid var(--border-light);
  background: var(--surface-base);
  padding: 10px 12px;
}

.low-value-guide summary {
  cursor: pointer;
  font-weight: 800;
  color: var(--text-primary);
}

.low-value-guide ul {
  margin: 10px 0 0;
  padding-left: 18px;
  display: grid;
  gap: 6px;
}

.nested-toggle {
  margin-top: 10px;
}

.edit-banner {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border-radius: 12px;
  background: color-mix(in srgb, var(--brand-subtle), var(--surface-elevated) 30%);
  border: 1px solid color-mix(in srgb, var(--brand-primary), var(--border-light) 60%);
  margin-bottom: 10px;
}

.grid-controls {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.grid-left {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 12px;
  flex: 1 1 700px;
}

.grid-right {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  flex-wrap: wrap;
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
  background: linear-gradient(180deg, var(--surface-base), var(--surface-raised));
  border-bottom: 1px solid var(--border-light);
  padding: 10px;
  text-align: left;
  font-weight: 900;
  color: var(--text-heading);
  white-space: nowrap;
}

.table thead th.low-value {
  opacity: 0.55;
  font-weight: 600;
}

.table tbody td {
  border-bottom: 1px solid var(--border-light);
  padding: 8px 10px;
  color: var(--text-body);
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
  border-radius: 12px;
  border: 1px solid var(--border-medium);
  padding: 10px 14px;
  cursor: pointer;
  font-weight: 800;
  box-shadow: var(--shadow-xs);
  transition: transform 0.08s ease, box-shadow 0.15s ease, filter 0.15s ease, border-color 0.15s ease, background 0.15s ease;
}
.btn:disabled { opacity: 0.55; cursor: not-allowed; }
.btn:active:not(:disabled) { transform: translateY(1px); }

.btn-primary {
  background: linear-gradient(135deg, var(--brand-primary), var(--brand-secondary));
  border-color: color-mix(in srgb, var(--brand-primary), #000 8%);
  color: var(--brand-on);
  box-shadow: var(--shadow-sm);
}
.btn-primary:hover:not(:disabled) { filter: brightness(1.05); box-shadow: var(--shadow-md); }

.btn-secondary {
  background: linear-gradient(180deg, var(--surface-elevated), var(--surface-raised));
  color: var(--text-body);
}
.btn-secondary:hover:not(:disabled) {
  background: var(--surface-hover);
  border-color: color-mix(in srgb, var(--brand-primary), var(--border-medium) 50%);
  box-shadow: var(--shadow-sm);
}

.btn-warning {
  background: linear-gradient(135deg, var(--brand-primary) 0%, var(--brand-secondary) 100%);
  border-color: color-mix(in srgb, var(--brand-primary), #000 8%);
  color: var(--brand-on);
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
  border-radius: 16px;
  border: 1px solid var(--border-light);
  background: linear-gradient(145deg, color-mix(in srgb, var(--brand-subtle), var(--surface-base) 20%), var(--surface-elevated));
  box-shadow: var(--shadow-sm);
}
.ai-actions {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}

:deep(.toggle-inline) {
  width: 100%;
  justify-content: flex-start;
}

:deep(.toggle-inline span) {
  color: var(--text-body);
}

@media (max-width: 900px) {
  .page-header,
  .card-header,
  .sub-head,
  .ai-card,
  .grid-controls {
    flex-direction: column;
    align-items: stretch;
  }

  .preview-meta {
    flex-direction: column;
  }

  .grid-right {
    width: 100%;
  }
}
</style>