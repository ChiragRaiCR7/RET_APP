<template>
  <div class="main-view">
    <!-- Tab Navigation -->
    <div class="tab-list" role="tablist">
      <button 
        v-for="(tab, idx) in tabs" 
        :key="idx"
        class="tab-button"
        :class="{ active: activeTab === idx }"
        @click="activeTab = idx"
        role="tab"
        :aria-selected="activeTab === idx"
      >
        <span class="tab-icon">{{ tab.icon }}</span>
        {{ tab.label }}
      </button>
    </div>

    <!-- TAB 0: Convert & Download -->
    <section v-show="activeTab === 0" class="enterprise-card" role="tabpanel">
      <div class="card-header">
        <div class="card-title-group">
          <h3 class="card-title">📁 Utility Workflow</h3>
        </div>
      </div>
      
      <!-- Workflow Steps -->
      <div class="workflow-steps">
        <p><strong>Steps</strong></p>
        <ol>
          <li>Upload one ZIP (scans nested ZIPs for XML files only) - Max 10GB</li>
          <li>Convert ALL extracted XML → CSV once (saved in session) - Parallel processing</li>
          <li>Download by group OR Download ALL (Preserve Structure) - ZIP or individual files</li>
          <li>(Optional) Enable <strong>Edit Mode</strong> to modify/add/remove CSVs (session-only) and download Modified ZIP</li>
        </ol>
      </div>

      <!-- Controls Section -->
      <div class="controls-section">
        <h4 class="section-title">⚙️ Controls</h4>
        <div class="controls-grid">
          <div class="control-group">
            <label class="form-label">Output format (downloads)</label>
            <div class="radio-group">
              <label class="radio-label">
                <input type="radio" v-model="workflow.outputFormat" value="csv" />
                <span>CSV</span>
              </label>
              <label class="radio-label">
                <input type="radio" v-model="workflow.outputFormat" value="xlsx" />
                <span>Excel (.xlsx)</span>
              </label>
            </div>
          </div>
          
          <div class="control-group">
            <SwitchGroup>
              <div class="edit-mode-toggle">
                <Switch
                  v-model="workflow.editMode"
                  :class="[
                    workflow.editMode ? 'toggle-active' : 'toggle-inactive',
                    'toggle-switch'
                  ]"
                >
                  <span
                    :class="[
                      workflow.editMode ? 'toggle-knob-on' : 'toggle-knob-off',
                      'toggle-knob'
                    ]"
                    aria-hidden="true"
                  />
                </Switch>
                <div class="toggle-labels">
                  <SwitchLabel class="toggle-label">Edit Mode</SwitchLabel>
                  <span class="toggle-subtext">Session-only edits, modify CSVs in-memory</span>
                </div>
                <span v-if="workflow.editMode" class="edit-mode-badge">Active</span>
              </div>
            </SwitchGroup>
          </div>
        </div>

        <div class="controls-actions">
          <button class="btn btn-secondary" @click="cleanupSession">
            🧹 Cleanup Session
          </button>
          <button class="btn btn-secondary" @click="clearAllEdits" :disabled="!workflow.editMode">
            Clear Edits
          </button>
          <span class="idle-info">Session auto-cleanup: 60 min</span>
        </div>

        <div class="parser-option">
          <label class="checkbox-label">
            <input type="checkbox" v-model="workflow.fastParser" />
            <span>🚀 Fast XML parser (lxml) - Use high-performance parser for large files</span>
          </label>
        </div>
      </div>

      <!-- Upload Section -->
      <div class="upload-section">
        <h4 class="section-title">📦 Upload a ZIP containing XMLs</h4>
        <FileUploader 
          @uploaded="onUploaded" 
          @files-added="onFilesAdded"
          :show-scan-results="false"
        />
        
        <div class="upload-actions">
          <button class="btn btn-secondary" @click="clearWorkflow">Clear</button>
          <button 
            class="btn btn-warning" 
            @click="bulkConvert" 
            :disabled="!workflow.scannedGroups.length || converting"
          >
            <span v-if="converting" class="spinner"></span>
            {{ converting ? 'Converting...' : 'Bulk Convert ALL' }}
          </button>
        </div>
        
        <p class="upload-hint">Upload → Scan ZIP → Bulk Convert. Then preview/download here (rendered in Part 3).</p>

        <!-- Embedding Status Indicator -->
        <div v-if="embeddingStatus" class="embedding-status" :class="'status-' + embeddingStatus">
          <span v-if="embeddingStatus === 'embedding'" class="spinner"></span>
          <span v-if="embeddingStatus === 'embedding'">Embedding data for AI chat...</span>
          <span v-else-if="embeddingStatus === 'done'">AI embedding complete - ready for chat</span>
          <span v-else-if="embeddingStatus === 'error'">Embedding failed</span>
        </div>
      </div>

      <!-- Files Indexed Dropdown -->
      <div v-if="workflow.converted && conversionData.files.length" class="files-section">
        <h4 class="section-title">📁 Files Indexed (Grouped by Prefix)</h4>
        <div class="download-actions">
          <button class="btn btn-primary" @click="downloadAll">
            📥 Download Document (Preserve Structure)
          </button>
          <button class="btn btn-warning" @click="downloadModifiedZip" :disabled="!workflow.editMode">
            📥 Download Modified Document
          </button>
          <button class="btn btn-secondary" @click="downloadPatchLog">
            📥 Download Patch Log
          </button>
        </div>
        <p class="edit-hint">Total files: {{ conversionData.files.length }} | Tip: Enable Edit Mode to modify/add/remove files.</p>
      </div>

      <!-- Group Selection & Preview -->
      <div v-if="workflow.converted" class="preview-section">
        <div class="selection-bar">
          <button class="btn btn-sm btn-primary" @click="selectAllGroups">Select All</button>
          <button class="btn btn-sm btn-secondary" @click="clearGroupSelection">Clear</button>
          <div class="search-groups">
            <label>Search groups</label>
            <input v-model="groupSearch" type="text" class="form-input" placeholder="Type to filter groups" />
          </div>
        </div>

        <!-- Group Selection Dropdown -->
        <div class="group-selection-section">
          <Listbox v-model="selectedGroups" multiple>
            <div class="listbox-wrapper">
              <ListboxButton class="listbox-button">
                <span class="listbox-label">{{ selectedGroups.length ? `${selectedGroups.length} group(s) selected` : 'Select groups...' }}</span>
                <span class="listbox-chevron" aria-hidden="true">&#9662;</span>
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
                      class="form-input"
                      placeholder="Search groups..."
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
                    <li :class="['listbox-option', { 'option-active': active, 'option-selected': selected }]">
                      <span class="option-check" v-if="selected">&#10003;</span>
                      <span class="option-check option-empty" v-else></span>
                      <span class="option-label">{{ group.name }}</span>
                      <span class="option-meta">{{ group.files?.length || group.file_count || 0 }} files</span>
                    </li>
                  </ListboxOption>
                  <li v-if="filteredGroups.length === 0" class="listbox-empty">No groups match "{{ groupSearch }}"</li>
                </ListboxOptions>
              </transition>
            </div>
          </Listbox>
        </div>

        <div class="active-group-section">
          <div class="form-group">
            <label class="form-label">Active group</label>
            <select v-model="activeGroup" class="form-select" @change="loadGroupFiles">
              <option value="">Choose options</option>
              <option v-for="g in conversionData.groups" :key="g.name" :value="g.name">
                {{ g.name }}
              </option>
            </select>
          </div>
        </div>

        <!-- Preview & Download Section -->
        <div v-if="activeGroup" class="group-preview">
          <h4 class="section-title">Preview & Download — Group: {{ activeGroup }} ({{ groupFiles.length }} files)</h4>
          
          <div class="form-group">
            <label class="form-label">{{ activeGroup }} files</label>
            <select v-model="activeFile" class="form-select" @change="loadFilePreview">
              <option v-for="f in groupFiles" :key="f.filename" :value="f.filename">
                {{ f.filename }}
              </option>
            </select>
          </div>

          <div v-if="preview" class="preview-info">
            <p><strong>Record Basis:</strong> {{ preview.record_basis || 'AUTO:AccountRuleLevelRow' }} | <strong>Rows:</strong> {{ preview.total_rows }} | <strong>Columns:</strong> {{ preview.headers?.length }}</p>
          </div>

          <div v-if="workflow.editMode" class="edit-save-bar">
            <span>{{ pendingChangesCount }} pending change(s)</span>
            <button class="btn btn-sm btn-primary" @click="saveCellEdits" :disabled="pendingChangesCount === 0">
              💾 Save edits to CSV
            </button>
          </div>

          <!-- Data Preview Table -->
          <div v-if="preview" class="data-table-wrapper preview-table">
            <table class="data-table">
              <thead>
                <tr>
                  <th v-for="(header, idx) in preview.headers" :key="idx">
                    <span class="header-edit" v-if="workflow.editMode">📝</span>
                    {{ header }}
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(row, rowIdx) in preview.rows" :key="rowIdx">
                  <td v-for="(cell, colIdx) in row" :key="colIdx">
                    <template v-if="workflow.editMode">
                      <input 
                        v-model="preview.rows[rowIdx][colIdx]" 
                        class="cell-input"
                        @change="markCellChanged(rowIdx, colIdx)"
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

          <div class="file-download-actions">
            <button class="btn btn-secondary" @click="downloadCurrentFile">
              📥 Download CSV — {{ activeFile }}
            </button>
            <button class="btn btn-primary" @click="downloadGroupZip">
              📥 Download Group ZIP — {{ activeGroup }} • {{ groupFiles.length }} files
            </button>
          </div>
        </div>
      </div>

      <!-- AI Indexing Section -->
      <div v-if="workflow.converted && conversionData.groups.length" class="ai-index-section">
        <h4 class="section-title">🤖 Quick AI Indexing</h4>
        <p class="section-desc">
          Index selected groups for AI-powered search and chat. 
          This enables asking questions about your converted data using natural language.
          AI will provide citations and source references.
        </p>
        
        <div class="ai-index-controls">
          <div class="group-select-grid">
            <label 
              v-for="group in conversionData.groups" 
              :key="group.name"
              class="checkbox-label ai-group-item"
              :class="{ 'indexed': indexedGroups.includes(group.name), 'auto-indexed': isAutoIndexedGroup(group.name) }"
            >
              <input 
                type="checkbox" 
                :value="group.name"
                v-model="aiSelectedGroups"
                :disabled="aiIndexing"
              />
              <span class="group-name">{{ group.name }}</span>
              <span class="group-meta">{{ group.file_count || 0 }} files</span>
              <span v-if="isAutoIndexedGroup(group.name)" class="auto-badge">Auto</span>
              <span v-if="indexedGroups.includes(group.name)" class="indexed-badge">✅ Indexed</span>
            </label>
          </div>
          
          <div class="ai-index-actions">
            <button class="btn btn-sm btn-secondary" @click="selectAllAIGroups" :disabled="aiIndexing">
              Select All
            </button>
            <button class="btn btn-sm btn-secondary" @click="selectAutoAIGroups" :disabled="aiIndexing">
              Select Auto Groups
            </button>
            <button class="btn btn-sm btn-secondary" @click="clearAIGroups" :disabled="aiIndexing">
              Clear
            </button>
          </div>

          <button 
            class="btn btn-primary ai-index-btn" 
            @click="startAIIndexing" 
            :disabled="aiIndexing || aiSelectedGroups.length === 0"
          >
            <span v-if="aiIndexing" class="spinner"></span>
            {{ aiIndexing ? 'Indexing for AI...' : `🚀 Index ${aiSelectedGroups.length} Group(s) for AI` }}
          </button>
          
          <p v-if="indexedGroups.length" class="index-status">
            ✅ {{ indexedGroups.length }} group(s) indexed — 
            <button class="btn-link" @click="activeTab = 2">Open AI Chat →</button>
          </p>
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

    <!-- TAB 1: Compare -->
    <section v-show="activeTab === 1" class="enterprise-card" role="tabpanel">
      <ComparisonPanel 
        @comparison-complete="onComparisonComplete"
      />
    </section>

    <!-- TAB 2: Ask RET AI -->
    <section v-show="activeTab === 2" class="enterprise-card" role="tabpanel">
      <AIPanel 
        :session-id="workflow.sessionId"
        :scanned-groups="workflow.scannedGroups"
        @groups-indexed="onGroupsIndexed"
      />
    </section>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch } from 'vue'
import { Switch, SwitchGroup, SwitchLabel, Listbox, ListboxButton, ListboxOptions, ListboxOption } from '@headlessui/vue'
import FileUploader from '@/components/workspace/FileUploader.vue'
import ComparisonPanel from '@/components/workspace/ComparisonPanel.vue'
import AIPanel from '@/components/workspace/AIPanel.vue'
import EditModePanel from '@/components/workspace/EditModePanel.vue'
import api from '@/utils/api'
import { useToastStore } from '@/stores/toastStore'

const toast = useToastStore()
const activeTab = ref(0)
const tabs = [
  { icon: '📁', label: 'Utility' },
  { icon: '📊', label: 'Compare (ZIP/XML/CSV)' },
  { icon: '🤖', label: 'Ask RET (Advanced RAG)' }
]

// Workflow state
const workflow = reactive({
  sessionId: null,
  outputFormat: 'csv',
  editMode: false,
  fastParser: true,
  uploadedFiles: [],
  scannedGroups: [],
  scanSummary: null,
  converted: false
})

const converting = ref(false)
const embeddingStatus = ref(null) // null | 'embedding' | 'done' | 'error'
const embeddingProgress = ref(null)
const groupSearch = ref('')
const selectedGroups = ref([])
const activeGroup = ref('')
const activeFile = ref('')
const preview = ref(null)
const groupFiles = ref([])
const pendingCellEdits = ref(new Map())

// Conversion data
const conversionData = reactive({
  groups: [],
  files: [],
  totalFiles: 0
})

// AI Indexing state
const aiSelectedGroups = ref([])
const indexedGroups = ref([])
const aiIndexing = ref(false)
const autoIndexedGroups = ref([])

// Computed
const filteredGroups = computed(() => {
  if (!groupSearch.value) return conversionData.groups
  const search = groupSearch.value.toLowerCase()
  return conversionData.groups.filter(g => g.name.toLowerCase().includes(search))
})

const pendingChangesCount = computed(() => pendingCellEdits.value.size)

watch(() => workflow.editMode, (enabled) => {
  if (!enabled) pendingCellEdits.value = new Map()
})

// Helper functions
function formatSize(bytes) {
  if (!bytes) return '0'
  if (typeof bytes === 'string') return bytes
  const mb = bytes / (1024 * 1024)
  return mb.toFixed(2)
}

function formatCellValue(value, maxLen = 50) {
  if (value === null || value === undefined) return ''
  const str = String(value)
  return str.length > maxLen ? str.substring(0, maxLen) + '...' : str
}

function onFilesAdded(filesList) {
  workflow.uploadedFiles.push(...filesList)
}

function onUploaded(data) {
  if (Array.isArray(data)) {
    workflow.uploadedFiles.push(...data)
  } else if (data && data.sessionId) {
    workflow.sessionId = data.sessionId
    const groups = (data.groups || []).map(g => ({
      name: g.name,
      file_count: g.file_count || g.fileCount || 0,
      size: g.size || 0,
      files: g.files || []
    }))
    workflow.scannedGroups = groups
    workflow.scanSummary = {
      totalGroups: groups.length,
      totalFiles: data.xmlCount || 0,
      totalSize: '—'
    }
  }
}

function clearWorkflow() {
  workflow.sessionId = null
  workflow.uploadedFiles = []
  workflow.scannedGroups = []
  workflow.scanSummary = null
  workflow.converted = false
  conversionData.groups = []
  conversionData.files = []
  activeGroup.value = ''
  activeFile.value = ''
  preview.value = null
   pendingCellEdits.value = new Map()
}

async function bulkConvert() {
  if (!workflow.sessionId) {
    toast.warning('No session. Please scan ZIP file first.')
    return
  }

  converting.value = true
  try {
    const formData = new FormData()
    formData.append('session_id', workflow.sessionId)
    formData.append('output_format', workflow.outputFormat)
    formData.append('auto_embed', 'true')
    workflow.scannedGroups.forEach(g => formData.append('groups', g.name))

    const res = await api.post('/conversion/convert', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })

    if (res.data.success) {
      workflow.converted = true
      toast.success(`Conversion complete! ${res.data.stats?.success || 0} files converted.`)
      await loadConvertedFiles()

      if (res.data.embedding_status === 'started') {
        toast.info('AI embedding started in background...')
        pollEmbeddingStatus()
      }
    }
  } catch (e) {
    toast.error('Conversion failed: ' + (e.response?.data?.detail || e.message))
  } finally {
    converting.value = false
  }
}

let embeddingPollTimer = null
function pollEmbeddingStatus() {
  embeddingStatus.value = 'embedding'
  if (embeddingPollTimer) clearInterval(embeddingPollTimer)
  embeddingPollTimer = setInterval(async () => {
    try {
      const res = await api.get(`/v2/ai/index/status/${workflow.sessionId}`)
      embeddingProgress.value = res.data
      const totalGroups = Object.keys(res.data.groups || {}).length
      const indexedGroups = Object.values(res.data.groups || {}).filter(g => g.indexed > 0).length
      if (totalGroups > 0 && indexedGroups >= totalGroups) {
        embeddingStatus.value = 'done'
        toast.success('AI embedding complete! You can now chat with your data.')
        clearInterval(embeddingPollTimer)
        embeddingPollTimer = null
      }
    } catch (e) {
      // Status endpoint may not be ready yet, keep polling
      console.debug('Embedding status poll:', e.message)
    }
  }, 3000)
}

async function loadConvertedFiles() {
  if (!workflow.sessionId) return
  
  try {
    const res = await api.get(`/conversion/files/${workflow.sessionId}`)
    conversionData.groups = res.data.groups || []
    conversionData.files = res.data.files || []
    conversionData.totalFiles = res.data.total_files || 0
    await loadAutoIndexConfig()
    
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
  } catch (e) {
    console.error('Failed to load preview:', e)
    preview.value = null
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
    toast.error('No active file to save edits')
    return
  }

  const changes = Array.from(pendingCellEdits.value.values())
  if (!changes.length) {
    toast.info('No pending cell edits')
    return
  }

  try {
    await api.post(`/conversion/update-cells/${workflow.sessionId}`, {
      filename: activeFile.value,
      changes
    })
    toast.success(`Saved ${changes.length} change(s) to ${activeFile.value}`)
    pendingCellEdits.value = new Map()
    await loadFilePreview()
  } catch (e) {
    toast.error('Failed to save edits: ' + (e.response?.data?.detail || e.message))
  }
}

async function downloadAll() {
  if (!workflow.sessionId) return
  
  try {
    const res = await api.get(`/conversion/download/${workflow.sessionId}`, {
      responseType: 'blob'
    })
    downloadBlob(res.data, 'converted_output.zip')
    toast.success('Download complete!')
  } catch (e) {
    toast.error('Download failed: ' + (e.response?.data?.detail || e.message))
  }
}

async function downloadModifiedZip() {
  if (!workflow.sessionId || !workflow.editMode) return
  
  try {
    const res = await api.get(`/conversion/download-modified/${workflow.sessionId}`, {
      responseType: 'blob'
    })
    downloadBlob(res.data, 'modified_output.zip')
    toast.success('Modified ZIP downloaded!')
  } catch (e) {
    toast.error('Download failed: ' + (e.response?.data?.detail || e.message))
  }
}

async function downloadPatchLog() {
  toast.info('Patch log download not implemented yet')
}

async function downloadCurrentFile() {
  if (!activeFile.value || !workflow.sessionId) return
  
  try {
    const res = await api.get(`/conversion/download-file/${workflow.sessionId}/${activeFile.value}`, {
      responseType: 'blob'
    })
    downloadBlob(res.data, activeFile.value)
  } catch (e) {
    toast.error('Download failed: ' + (e.response?.data?.detail || e.message))
  }
}

async function downloadGroupZip() {
  if (!activeGroup.value || !workflow.sessionId) return
  
  try {
    const res = await api.get(`/conversion/download-group/${workflow.sessionId}/${activeGroup.value}`, {
      responseType: 'blob'
    })
    downloadBlob(res.data, `${activeGroup.value}_group.zip`)
    toast.success(`Group ${activeGroup.value} downloaded!`)
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
    toast.warning('No active session to cleanup')
    return
  }
  
  try {
    await api.post(`/conversion/cleanup/${workflow.sessionId}`)
    toast.success('Session data cleaned up')
    clearWorkflow()
  } catch (e) {
    toast.error('Cleanup failed: ' + (e.response?.data?.detail || e.message))
  }
}

function clearAllEdits() {
  toast.info('All edits cleared')
}

function onComparisonComplete(results) {
  toast.success('Comparison complete!')
}

// AI Indexing functions
function selectAllAIGroups() {
  aiSelectedGroups.value = conversionData.groups.map(g => g.name)
}

function clearAIGroups() {
  aiSelectedGroups.value = []
}

function selectAutoAIGroups() {
  aiSelectedGroups.value = conversionData.groups
    .map(g => g.name)
    .filter(name => isAutoIndexedGroup(name) && !indexedGroups.value.includes(name))
}

async function startAIIndexing() {
  if (!workflow.sessionId || aiSelectedGroups.value.length === 0) {
    toast.error('No session or groups selected')
    return
  }

  aiIndexing.value = true

  try {
    const res = await api.post('/v2/ai/index/groups', {
      session_id: workflow.sessionId,
      groups: aiSelectedGroups.value
    })

    const indexed = res.data.indexed_groups || res.data.groups || aiSelectedGroups.value
    indexedGroups.value = [...new Set([...indexedGroups.value, ...indexed])]

    const count = res.data.indexed_count || res.data.files_indexed || indexed.length
    toast.success(`${count} group(s) indexed successfully for AI!`)

  } catch (e) {
    toast.error('AI indexing failed: ' + (e.response?.data?.detail || e.message))
  } finally {
    aiIndexing.value = false
  }
}

function onGroupsIndexed(groups) {
  indexedGroups.value = [...new Set([...indexedGroups.value, ...(groups || [])])]
  toast.success(`${groups.length} groups indexed for AI`)
}

async function loadAutoIndexConfig() {
  try {
    const res = await api.get('/v2/ai/config')
    autoIndexedGroups.value = res.data.auto_indexed_groups || []
  } catch {
    autoIndexedGroups.value = []
  }
}

function isAutoIndexedGroup(name) {
  return autoIndexedGroups.value.some(g => name?.toUpperCase().includes(g.toUpperCase()))
}

function onFileUpdated(file) {
  loadConvertedFiles()
}

function onFileAdded(file) {
  loadConvertedFiles()
}

function onFileRemoved(filename) {
  loadConvertedFiles()
}

</script>

<style scoped>
.main-view {
  padding: 0;
}

.workflow-steps {
  background: var(--surface-base);
  border-radius: var(--radius-md);
  padding: var(--space-md);
  margin-bottom: var(--space-lg);
}

.workflow-steps ol {
  margin: var(--space-sm) 0 0 var(--space-lg);
}

.workflow-steps li {
  margin-bottom: var(--space-xs);
  color: var(--text-secondary);
}

.controls-section {
  background: var(--surface-base);
  border-radius: var(--radius-md);
  padding: var(--space-lg);
  margin-bottom: var(--space-lg);
}

.section-title {
  font-size: 1rem;
  font-weight: 700;
  margin-bottom: var(--space-md);
  color: var(--text-heading);
}

.controls-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: var(--space-lg);
  margin-bottom: var(--space-md);
}

.control-group {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}

.control-group.full-width {
  grid-column: 1 / -1;
}

.radio-group {
  display: flex;
  gap: var(--space-lg);
}

.radio-label {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
  cursor: pointer;
}

.toggle-control {
  display: flex;
  align-items: center;
  gap: var(--space-md);
  cursor: pointer;
  padding: var(--space-md);
  border-radius: 8px;
  background: var(--surface-secondary);
  border: 1px solid var(--border-light);
  transition: all 0.2s ease;
}

.toggle-control:hover {
  background: var(--surface-hover);
  border-color: var(--brand-primary);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

/* Edit Mode Toggle Switch — HeadlessUI Switch */
.edit-mode-toggle {
  display: flex;
  align-items: center;
  gap: var(--space-md);
  padding: var(--space-lg);
  background: linear-gradient(135deg, var(--surface-secondary) 0%, var(--surface) 100%);
  border-radius: var(--radius-lg);
  border: 2px solid var(--border-light);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}

.edit-mode-toggle:hover {
  border-color: var(--brand-primary);
  box-shadow: 0 4px 16px rgba(255, 192, 0, 0.15);
  transform: translateY(-1px);
}

.toggle-switch {
  position: relative;
  width: 56px;
  height: 32px;
  border-radius: 999px;
  border: 2px solid transparent;
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.06);
}

.toggle-switch:focus-visible {
  outline: 3px solid var(--brand-primary);
  outline-offset: 3px;
}

.toggle-switch:active {
  transform: scale(0.96);
}

.toggle-active {
  background: linear-gradient(135deg, var(--brand-primary) 0%, #FFD700 100%);
  border-color: var(--brand-primary);
  box-shadow: 0 4px 12px rgba(255, 192, 0, 0.4), inset 0 1px 2px rgba(255, 255, 255, 0.3);
}

.toggle-inactive {
  background: linear-gradient(135deg, #E5E7EB 0%, #D1D5DB 100%);
  border-color: #D1D5DB;
}

.toggle-knob {
  display: block;
  width: 24px;
  height: 24px;
  background: linear-gradient(180deg, #FFFFFF 0%, #F9FAFB 100%);
  border-radius: 50%;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 0 3px 8px rgba(0, 0, 0, 0.25), 0 1px 3px rgba(0, 0, 0, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.5);
}

.toggle-knob-on {
  transform: translateX(24px);
}

.toggle-knob-off {
  transform: translateX(3px);
}

.toggle-active .toggle-knob {
  box-shadow: 0 3px 10px rgba(255, 192, 0, 0.5), 0 1px 4px rgba(0, 0, 0, 0.2);
}

.toggle-labels {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
}

.toggle-label {
  font-weight: 700;
  font-size: 1rem;
  color: var(--text-primary);
  letter-spacing: -0.01em;
  display: flex;
  align-items: center;
  gap: 8px;
}

.toggle-label::before {
  content: '✏️';
  font-size: 1.1rem;
}

.toggle-subtext {
  font-size: 0.8rem;
  color: var(--text-tertiary);
  line-height: 1.3;
}

.edit-mode-badge {
  padding: 6px 14px;
  background: linear-gradient(135deg, var(--success) 0%, #10B981 100%);
  color: white;
  font-size: 0.8rem;
  font-weight: 700;
  border-radius: var(--radius-full);
  animation: pulse 2s infinite;
  box-shadow: 0 2px 8px rgba(34, 197, 94, 0.3);
  letter-spacing: 0.02em;
  text-transform: uppercase;
}

@keyframes pulse {
  0%, 100% { 
    opacity: 1; 
    transform: scale(1);
  }
  50% { 
    opacity: 0.85; 
    transform: scale(0.98);
  }
}


.controls-actions {
  display: flex;
  gap: var(--space-md);
  align-items: center;
  flex-wrap: wrap;
}

.idle-info {
  color: var(--text-tertiary);
  font-size: 0.85rem;
}

.parser-option {
  margin-top: var(--space-md);
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  cursor: pointer;
}

.upload-section {
  margin-bottom: var(--space-xl);
}

.upload-actions {
  display: flex;
  gap: var(--space-md);
  margin-top: var(--space-md);
}

.upload-hint {
  color: var(--text-tertiary);
  font-size: 0.85rem;
  margin-top: var(--space-sm);
}

.embedding-status {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 0.85rem;
  margin-top: var(--space-sm);
}
.embedding-status.status-embedding {
  background: var(--color-info-bg, #e8f4fd);
  color: var(--color-info, #1976d2);
  border: 1px solid var(--color-info, #1976d2);
}
.embedding-status.status-done {
  background: var(--color-success-bg, #e8f5e9);
  color: var(--color-success, #2e7d32);
  border: 1px solid var(--color-success, #2e7d32);
}
.embedding-status.status-error {
  background: var(--color-error-bg, #fce4ec);
  color: var(--color-error, #c62828);
  border: 1px solid var(--color-error, #c62828);
}

.files-section {
  margin-top: var(--space-xl);
}

.download-actions {
  display: flex;
  gap: var(--space-md);
  margin-top: var(--space-lg);
  flex-wrap: wrap;
  align-items: center;
}

.edit-hint {
  color: var(--text-tertiary);
  font-size: 0.85rem;
}

.preview-section {
  margin-top: var(--space-xl);
}

.selection-bar {
  display: flex;
  gap: var(--space-md);
  align-items: center;
  margin-bottom: var(--space-md);
}

.search-groups {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  margin-left: auto;
}

.search-groups .form-input {
  width: 200px;
}

.groups-badges {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-xs);
  margin-bottom: var(--space-lg);
}

/* Group Selection Dropdown — HeadlessUI Listbox */
.group-selection-section {
  margin-bottom: var(--space-lg);
  padding: var(--space-md);
  background: var(--surface-secondary);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-light);
}

.listbox-wrapper {
  position: relative;
}

.listbox-button {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 10px 14px;
  background: var(--surface-base);
  border: 1px solid var(--border-medium);
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: 0.95rem;
  color: var(--text-primary);
  transition: border-color 0.2s;
}

.listbox-button:hover {
  border-color: var(--brand-primary);
}

.listbox-button:focus-visible {
  outline: 2px solid var(--brand-primary);
  outline-offset: 2px;
}

.listbox-label {
  flex: 1;
  text-align: left;
}

.listbox-chevron {
  font-size: 0.75rem;
  color: var(--text-tertiary);
}

.listbox-options {
  position: absolute;
  z-index: 50;
  width: 100%;
  max-height: 280px;
  overflow-y: auto;
  margin-top: 4px;
  background: var(--surface-elevated);
  border: 1px solid var(--border-medium);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-lg);
  list-style: none;
  padding: 0;
}

.listbox-search {
  padding: 8px;
  border-bottom: 1px solid var(--border-light);
  position: sticky;
  top: 0;
  background: var(--surface-elevated);
  z-index: 1;
}

.listbox-search .form-input {
  width: 100%;
  padding: 6px 10px;
  font-size: 0.85rem;
}

.listbox-option {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  padding: 8px 12px;
  cursor: pointer;
  font-size: 0.9rem;
  transition: background-color 0.15s;
}

.listbox-option.option-active {
  background: var(--brand-subtle);
}

.listbox-option.option-selected {
  font-weight: 600;
}

.option-check {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  border: 2px solid var(--border-medium);
  font-size: 0.7rem;
  font-weight: 700;
  color: white;
}

.option-selected .option-check {
  background: var(--brand-primary);
  border-color: var(--brand-primary);
}

.option-empty {
  background: transparent;
}

.option-label {
  flex: 1;
  color: var(--text-primary);
}

.option-meta {
  font-size: 0.75rem;
  color: var(--text-tertiary);
}

.listbox-empty {
  padding: 12px;
  text-align: center;
  color: var(--text-tertiary);
  font-size: 0.85rem;
}

/* Listbox transitions */
.listbox-enter-active,
.listbox-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}

.listbox-enter-from,
.listbox-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

.listbox-enter-to,
.listbox-leave-from {
  opacity: 1;
  transform: translateY(0);
}

.group-multi-select {
  min-height: 170px;
  background: var(--surface-base);
}

.btn-sm {
  padding: 4px 12px;
  font-size: 0.85rem;
}

.btn-ghost {
  background: transparent;
  border: 1px solid var(--border-medium);
  color: var(--text-secondary);
}

.btn-ghost:hover {
  background: var(--surface-hover);
  color: var(--text-primary);
}

.group-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  border-radius: var(--radius-full);
  background: var(--brand-primary);
  color: #000;
  font-size: 0.85rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.group-badge:hover {
  filter: brightness(0.9);
}

.group-badge.selected {
  background: var(--success);
  color: white;
}

.active-group-section {
  margin-bottom: var(--space-lg);
}

.group-preview {
  background: var(--surface-base);
  border-radius: var(--radius-md);
  padding: var(--space-lg);
}

.preview-info {
  margin: var(--space-md) 0;
  padding: var(--space-sm);
  background: var(--surface-hover);
  border-radius: var(--radius-sm);
}

.edit-save-bar {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  margin: var(--space-sm) 0;
  padding: var(--space-sm) var(--space-md);
  background: var(--surface-hover);
  border-radius: var(--radius-sm);
  font-size: 0.9rem;
}

.preview-table {
  max-height: 400px;
  overflow: auto;
}

.header-edit {
  cursor: pointer;
  margin-right: 4px;
}

.cell-input {
  width: 100%;
  padding: 4px 8px;
  border: 1px solid var(--border-medium);
  border-radius: var(--radius-sm);
  font-size: 0.85rem;
}

.file-download-actions {
  display: flex;
  gap: var(--space-md);
  margin-top: var(--space-lg);
}

.tab-icon {
  margin-right: var(--space-xs);
}

.btn-warning {
  background: linear-gradient(135deg, var(--brand-primary) 0%, var(--brand-secondary) 100%);
  color: #000;
  border-color: var(--brand-primary);
}

.btn-warning:hover:not(:disabled) {
  filter: brightness(1.1);
  box-shadow: var(--shadow-md);
}

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

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* AI Indexing Section */
.ai-index-section {
  background: linear-gradient(145deg, var(--surface-base), var(--surface-elevated));
  border-radius: var(--radius-md);
  padding: var(--space-lg);
  margin-top: var(--space-lg);
  border: 1px solid var(--border-light);
}

.ai-index-section .section-desc {
  font-size: 0.9rem;
  color: var(--text-secondary);
  margin-bottom: var(--space-md);
}

.ai-index-controls {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.group-select-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: var(--space-sm);
  max-height: 200px;
  overflow-y: auto;
  padding: var(--space-sm);
  background: var(--surface-base);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-light);
}

.ai-group-item {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  padding: var(--space-sm);
  background: var(--surface-elevated);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all 0.2s;
}

.ai-group-item:hover {
  background: var(--brand-subtle);
}

.ai-group-item.indexed {
  border-left: 3px solid var(--success);
}

.ai-group-item.auto-indexed {
  border-left: 3px solid var(--brand-primary);
}

.ai-group-item .group-name {
  font-weight: 600;
  flex: 1;
}

.ai-group-item .group-meta {
  font-size: 0.75rem;
  color: var(--text-tertiary);
}

.ai-group-item .indexed-badge {
  font-size: 0.7rem;
  color: var(--success);
}

.ai-group-item .auto-badge {
  font-size: 0.7rem;
  color: #000;
  background: var(--brand-primary);
  border-radius: var(--radius-full);
  padding: 2px 6px;
}

.ai-index-actions {
  display: flex;
  gap: var(--space-sm);
}

.ai-index-btn {
  align-self: flex-start;
}

.index-status {
  font-size: 0.9rem;
  color: var(--success);
  margin-top: var(--space-sm);
}

.btn-link {
  background: none;
  border: none;
  color: var(--brand-primary);
  cursor: pointer;
  text-decoration: underline;
  padding: 0;
  font-size: inherit;
}

.btn-link:hover {
  color: var(--brand-light);
}
</style>
