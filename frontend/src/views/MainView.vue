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
          <li>Upload one ZIP (scans nested ZIPs for XML files only).</li>
          <li>Convert ALL extracted XML → CSV once (saved in session).</li>
          <li>Download by group OR Download ALL (Preserve Structure).</li>
          <li>(Optional) Enable <strong>Edit Mode</strong> to modify/add/remove CSVs (session-only) and download Modified ZIP.</li>
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
            <div class="edit-mode-toggle">
              <label class="toggle-switch">
                <input type="checkbox" v-model="workflow.editMode" />
                <span class="toggle-slider" aria-hidden="true"></span>
              </label>
              <div class="toggle-labels">
                <span class="toggle-label">✏️ Edit Mode</span>
                <span class="toggle-subtext">Session-only edits</span>
              </div>
              <span v-if="workflow.editMode" class="edit-mode-badge">Active</span>
            </div>
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
            <span>🚀 Fast XML parser (lxml)</span>
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
          <div class="form-group">
            <label class="form-label">📂 Select Groups ({{ selectedGroups.length }} selected)</label>
            <select
              v-model="selectedGroups"
              class="form-select group-multi-select"
              multiple
              size="6"
            >
              <option 
                v-for="group in filteredGroups" 
                :key="group.name" 
                :value="group.name"
              >
                {{ group.name }} ({{ group.files?.length || 0 }} files)
              </option>
            </select>
            <p class="form-hint">Tip: Use Ctrl/⌘ + click to select multiple groups.</p>
          </div>
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
          This enables asking questions about your converted data.
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
    workflow.scannedGroups.forEach(g => formData.append('groups', g.name))
    
    const res = await api.post('/conversion/convert', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
    
    if (res.data.success) {
      workflow.converted = true
      toast.success(`Conversion complete! ${res.data.stats?.success || 0} files converted.`)
      await loadConvertedFiles()
    }
  } catch (e) {
    toast.error('Conversion failed: ' + (e.response?.data?.detail || e.message))
  } finally {
    converting.value = false
  }
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
    // Try v2 endpoint first
    let res
    try {
      res = await api.post('/v2/ai/index/groups', {
        session_id: workflow.sessionId,
        groups: aiSelectedGroups.value
      })
    } catch (v2Error) {
      // Fallback to legacy endpoint
      const formData = new FormData()
      formData.append('session_id', workflow.sessionId)
      formData.append('groups', aiSelectedGroups.value.join(','))
      
      res = await api.post('/ai/index-session', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      })
    }
    
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

/* Edit Mode Toggle Switch */
.edit-mode-toggle {
  display: flex;
  align-items: center;
  gap: var(--space-md);
  padding: var(--space-md);
  background: var(--surface-secondary);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-light);
}

.toggle-switch {
  position: relative;
  width: 48px;
  height: 28px;
  display: inline-flex;
  align-items: center;
}

.toggle-switch input {
  appearance: none;
  width: 48px;
  height: 28px;
  border-radius: 999px;
  background: #e5e7eb;
  border: 2px solid #d1d5db;
  cursor: pointer;
  transition: all 0.2s ease;
}

.toggle-switch input:checked {
  background: var(--brand-primary);
  border-color: var(--brand-primary);
}

.toggle-slider {
  position: absolute;
  width: 20px;
  height: 20px;
  background: #fff;
  border-radius: 50%;
  left: 4px;
  transition: transform 0.2s ease;
  pointer-events: none;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.2);
}

.toggle-switch input:checked + .toggle-slider {
  transform: translateX(20px);
}

.toggle-labels {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.toggle-label {
  font-weight: 600;
  font-size: 0.95rem;
  color: var(--text-primary);
}

.toggle-subtext {
  font-size: 0.75rem;
  color: var(--text-tertiary);
}

.edit-mode-badge {
  padding: 2px 10px;
  background: var(--success);
  color: white;
  font-size: 0.75rem;
  font-weight: 600;
  border-radius: var(--radius-full);
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.7; }
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

/* Group Selection Dropdown */
.group-selection-section {
  margin-bottom: var(--space-lg);
  padding: var(--space-md);
  background: var(--surface-secondary);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-light);
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
