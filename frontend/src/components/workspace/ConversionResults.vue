<template>
  <div class="conversion-results">
    <!-- Results Header -->
    <div class="results-header">
      <h3 class="card-title">📊 Conversion Results</h3>
      <p class="card-description">
        {{ totalFiles }} files converted in {{ groups.length }} groups
      </p>
    </div>

    <!-- Download Controls -->
    <div class="download-controls">
      <div class="form-group">
        <label class="form-label">Output Format</label>
        <select v-model="outputFormat" class="form-select">
          <option value="csv">CSV</option>
          <option value="xlsx">Excel (XLSX)</option>
        </select>
      </div>
      <button class="btn btn-primary" @click="downloadAll" :disabled="downloading">
        <span v-if="downloading" class="spinner"></span>
        {{ downloading ? 'Downloading...' : '📥 Download All' }}
      </button>
      <button class="btn btn-secondary" @click="downloadSelected" :disabled="!selectedGroup || downloading">
        📥 Download Group
      </button>
      
      <!-- Edit Mode Toggle -->
      <div class="edit-mode-toggle">
        <label class="toggle-label">
          <input type="checkbox" v-model="editMode" class="toggle-input">
          <span class="toggle-slider"></span>
          <span class="toggle-text">✏️ Edit Mode</span>
        </label>
      </div>
    </div>

    <!-- Groups Selection -->
    <div class="selection-grid">
      <div class="form-group">
        <label class="form-label">Select Group</label>
        <select v-model="selectedGroup" class="form-select" @change="onGroupChange">
          <option value="">All Groups</option>
          <option v-for="g in groups" :key="g.name" :value="g.name">
            {{ g.name }} ({{ g.file_count }} files, {{ g.total_rows }} rows)
          </option>
        </select>
      </div>
    </div>

    <!-- Groups Summary Table -->
    <div class="enterprise-card" style="margin-top: var(--space-lg)">
      <h4 class="card-title">Groups Summary</h4>
      <div class="data-table-wrapper">
        <table class="data-table">
          <thead>
            <tr>
              <th>Group</th>
              <th>Files</th>
              <th>Total Rows</th>
              <th>Size</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="g in groups" :key="g.name" :class="{ selected: selectedGroup === g.name }">
              <td><strong>{{ g.name }}</strong></td>
              <td>{{ g.file_count }}</td>
              <td>{{ g.total_rows.toLocaleString() }}</td>
              <td>{{ formatSize(g.total_size) }}</td>
              <td>
                <button class="btn btn-sm btn-primary" @click="selectGroup(g.name)">
                  View Files
                </button>
                <button class="btn btn-sm btn-secondary" @click="downloadGroup(g.name)">
                  Download
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- File Tabs Section -->
    <div v-if="filteredFiles.length > 0" class="enterprise-card file-tabs-section" style="margin-top: var(--space-lg)">
      <h4 class="card-title">
        Files {{ selectedGroup ? `in ${selectedGroup}` : '(All)' }}
      </h4>
      
      <!-- Tab Navigation -->
      <div class="file-tabs">
        <button 
          v-for="(f, idx) in filteredFiles" 
          :key="f.filename"
          class="file-tab"
          :class="{ active: activeFileIndex === idx }"
          @click="selectFileByIndex(idx)"
          :title="f.filename"
        >
          {{ getShortName(f.filename) }}
          <span class="tab-meta">{{ f.rows }}r × {{ f.columns }}c</span>
        </button>
      </div>

      <!-- Active File Info Bar -->
      <div v-if="activeFile" class="file-info-bar">
        <span class="file-name">📄 {{ activeFile.filename }}</span>
        <span class="file-stats">{{ activeFile.rows }} rows × {{ activeFile.columns }} columns</span>
        <div class="file-actions">
          <button class="btn btn-sm btn-primary" @click="refreshPreview" :disabled="loadingPreview">
            🔄 Refresh
          </button>
          <button class="btn btn-sm btn-secondary" @click="downloadFile(activeFile.filename)">
            ⬇️ Download
          </button>
          <button v-if="editMode && hasChanges" class="btn btn-sm btn-success" @click="saveAllChanges">
            💾 Save Changes
          </button>
        </div>
      </div>

      <!-- Spreadsheet View -->
      <div class="spreadsheet-container" :class="{ 'edit-mode-active': editMode }">
        <div v-if="loadingPreview" class="loading-overlay">
          <span class="spinner"></span> Loading preview...
        </div>
        
        <div v-else-if="preview" class="spreadsheet-wrapper">
          <table class="spreadsheet">
            <thead>
              <tr>
                <th class="row-number">#</th>
                <th 
                  v-for="(header, idx) in preview.headers" 
                  :key="idx"
                  class="header-cell"
                  :title="header"
                >
                  {{ header }}
                </th>
                <th v-if="editMode" class="row-actions-header">Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, rowIdx) in editableRows" :key="rowIdx">
                <td class="row-number">{{ rowIdx + 1 }}</td>
                <td 
                  v-for="(header, colIdx) in preview.headers" 
                  :key="colIdx"
                  class="data-cell"
                  :class="{ 
                    'cell-modified': isCellModified(rowIdx, header),
                    'cell-editing': editingCell?.row === rowIdx && editingCell?.col === colIdx
                  }"
                >
                  <!-- Edit Mode -->
                  <template v-if="editMode">
                    <input
                      v-if="editingCell?.row === rowIdx && editingCell?.col === colIdx"
                      :value="row[colIdx]"
                      @input="e => onCellInput(rowIdx, colIdx, header, e.target.value)"
                      @blur="onCellBlur"
                      @keydown.enter="onCellEnter"
                      @keydown.escape="onCellEscape"
                      @keydown.tab="e => onCellTab(e, rowIdx, colIdx)"
                      class="cell-input"
                      autofocus
                    />
                    <div 
                      v-else 
                      class="cell-display editable"
                      @dblclick="startEditing(rowIdx, colIdx)"
                    >
                      {{ formatCellValue(row[colIdx]) }}
                    </div>
                  </template>
                  
                  <!-- View Mode -->
                  <template v-else>
                    <div class="cell-display" :title="String(row[colIdx] || '')">
                      {{ formatCellValue(row[colIdx]) }}
                    </div>
                  </template>
                </td>
                
                <!-- Row Actions (Edit Mode) -->
                <td v-if="editMode" class="row-actions">
                  <button class="btn-icon" @click="deleteRow(rowIdx)" title="Delete row">🗑️</button>
                </td>
              </tr>
            </tbody>
          </table>
          
          <!-- Add Row Button (Edit Mode) -->
          <div v-if="editMode" class="add-row-section">
            <button class="btn btn-sm btn-primary" @click="addNewRow">➕ Add Row</button>
          </div>
        </div>
        
        <div v-else class="no-preview">
          Select a file tab to view its contents
        </div>
      </div>
      
      <!-- Pagination / Stats -->
      <div v-if="preview" class="preview-footer">
        <span class="preview-stats">
          Showing {{ preview.preview_rows }} of {{ preview.total_rows }} rows
          <template v-if="editMode && hasChanges">
            • <span class="changes-indicator">{{ pendingChanges.size }} cell(s) modified</span>
          </template>
        </span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, nextTick } from 'vue'
import api from '@/utils/api'

const props = defineProps({
  sessionId: {
    type: String,
    required: true
  }
})

const emit = defineEmits(['download-started', 'download-complete', 'error'])

// State
const loading = ref(false)
const loadingPreview = ref(false)
const downloading = ref(false)
const outputFormat = ref('csv')
const selectedGroup = ref('')
const activeFileIndex = ref(0)
const groups = ref([])
const files = ref([])
const preview = ref(null)
const totalFiles = ref(0)
const editMode = ref(false)

// Editing state
const editingCell = ref(null)
const pendingChanges = ref(new Map()) // Map of "rowIdx:colName" -> newValue
const editableRows = ref([])

// Computed
const filteredFiles = computed(() => {
  if (!selectedGroup.value) return files.value
  return files.value.filter(f => f.group === selectedGroup.value)
})

const activeFile = computed(() => {
  return filteredFiles.value[activeFileIndex.value] || null
})

const hasChanges = computed(() => {
  return pendingChanges.value.size > 0
})

// Methods
function formatSize(bytes) {
  if (!bytes) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  let idx = 0
  let size = bytes
  while (size >= 1024 && idx < units.length - 1) {
    size /= 1024
    idx++
  }
  return `${size.toFixed(1)} ${units[idx]}`
}

function getShortName(filename) {
  if (!filename) return ''
  const name = filename.replace(/\.csv$/i, '')
  return name.length > 20 ? name.substring(0, 18) + '...' : name
}

function formatCellValue(value, maxLen = 100) {
  if (value === null || value === undefined) return ''
  const str = String(value)
  return str.length > maxLen ? str.substring(0, maxLen) + '...' : str
}

function isCellModified(rowIdx, header) {
  const key = `${rowIdx}:${header}`
  return pendingChanges.value.has(key)
}

async function loadConvertedFiles() {
  if (!props.sessionId) return
  
  loading.value = true
  try {
    const res = await api.get(`/conversion/files/${props.sessionId}`)
    groups.value = res.data.groups || []
    files.value = res.data.files || []
    totalFiles.value = res.data.total_files || 0
    
    // Auto-select first file if available
    if (filteredFiles.value.length > 0) {
      activeFileIndex.value = 0
      await loadFilePreview(filteredFiles.value[0].filename)
    }
  } catch (e) {
    console.error('Failed to load converted files:', e)
    emit('error', e.response?.data?.detail || e.message)
  } finally {
    loading.value = false
  }
}

function onGroupChange() {
  activeFileIndex.value = 0
  preview.value = null
  pendingChanges.value.clear()
  
  if (filteredFiles.value.length > 0) {
    loadFilePreview(filteredFiles.value[0].filename)
  }
}

function selectGroup(groupName) {
  selectedGroup.value = groupName
  onGroupChange()
}

function selectFileByIndex(idx) {
  if (hasChanges.value) {
    if (!confirm('You have unsaved changes. Discard them?')) {
      return
    }
  }
  activeFileIndex.value = idx
  pendingChanges.value.clear()
  if (filteredFiles.value[idx]) {
    loadFilePreview(filteredFiles.value[idx].filename)
  }
}

async function loadFilePreview(filename) {
  loadingPreview.value = true
  try {
    const res = await api.get(`/conversion/preview/${props.sessionId}/${filename}`, {
      params: { max_rows: 200 }
    })
    preview.value = res.data
    // Clone rows for editing
    editableRows.value = res.data.rows.map(row => [...row])
  } catch (e) {
    console.error('Failed to preview file:', e)
    emit('error', e.response?.data?.detail || e.message)
  } finally {
    loadingPreview.value = false
  }
}

async function refreshPreview() {
  if (activeFile.value) {
    pendingChanges.value.clear()
    await loadFilePreview(activeFile.value.filename)
  }
}

// Cell Editing
function startEditing(rowIdx, colIdx) {
  editingCell.value = { row: rowIdx, col: colIdx }
}

function onCellInput(rowIdx, colIdx, header, value) {
  editableRows.value[rowIdx][colIdx] = value
  const key = `${rowIdx}:${header}`
  const originalValue = preview.value?.rows[rowIdx]?.[colIdx]
  
  if (value !== originalValue) {
    pendingChanges.value.set(key, { rowIdx, header, value, colIdx })
  } else {
    pendingChanges.value.delete(key)
  }
}

function onCellBlur() {
  editingCell.value = null
}

function onCellEnter() {
  editingCell.value = null
}

function onCellEscape() {
  // Revert changes for this cell
  if (editingCell.value) {
    const { row, col } = editingCell.value
    const originalValue = preview.value?.rows[row]?.[col]
    editableRows.value[row][col] = originalValue
    const header = preview.value?.headers[col]
    pendingChanges.value.delete(`${row}:${header}`)
  }
  editingCell.value = null
}

function onCellTab(e, rowIdx, colIdx) {
  e.preventDefault()
  const totalCols = preview.value?.headers?.length || 0
  const totalRows = editableRows.value.length
  
  let nextCol = colIdx + 1
  let nextRow = rowIdx
  
  if (nextCol >= totalCols) {
    nextCol = 0
    nextRow = rowIdx + 1
  }
  
  if (nextRow < totalRows) {
    editingCell.value = null
    nextTick(() => {
      startEditing(nextRow, nextCol)
    })
  }
}

async function saveAllChanges() {
  if (!activeFile.value || pendingChanges.value.size === 0) return
  
  const filename = activeFile.value.filename
  
  try {
    // Save each changed cell
    for (const [key, change] of pendingChanges.value) {
      const formData = new FormData()
      formData.append('row_index', change.rowIdx.toString())
      formData.append('column', change.header)
      formData.append('value', change.value)
      
      await api.post(`/conversion/update-cell/${props.sessionId}/${filename}`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      })
    }
    
    // Clear pending changes and refresh
    pendingChanges.value.clear()
    await loadFilePreview(filename)
    emit('download-complete') // Reuse this to indicate success
  } catch (e) {
    console.error('Failed to save changes:', e)
    emit('error', e.response?.data?.detail || e.message)
  }
}

async function addNewRow() {
  if (!activeFile.value || !preview.value) return
  
  const filename = activeFile.value.filename
  const headers = preview.value.headers
  const rowData = {}
  headers.forEach(h => rowData[h] = '')
  
  try {
    const formData = new FormData()
    formData.append('row_data', JSON.stringify(rowData))
    
    await api.post(`/conversion/add-row/${props.sessionId}/${filename}`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
    
    await loadFilePreview(filename)
  } catch (e) {
    console.error('Failed to add row:', e)
    emit('error', e.response?.data?.detail || e.message)
  }
}

async function deleteRow(rowIdx) {
  if (!activeFile.value) return
  if (!confirm(`Delete row ${rowIdx + 1}?`)) return
  
  const filename = activeFile.value.filename
  
  try {
    await api.delete(`/conversion/delete-row/${props.sessionId}/${filename}/${rowIdx}`)
    await loadFilePreview(filename)
    pendingChanges.value.clear()
  } catch (e) {
    console.error('Failed to delete row:', e)
    emit('error', e.response?.data?.detail || e.message)
  }
}

// Download Functions
async function downloadAll() {
  downloading.value = true
  emit('download-started')
  
  try {
    const formData = new FormData()
    formData.append('output_format', outputFormat.value)
    formData.append('preserve_structure', 'false')
    
    const res = await api.post(`/conversion/download-custom/${props.sessionId}`, formData, {
      responseType: 'blob',
      headers: { 'Content-Type': 'multipart/form-data' }
    })
    
    triggerDownload(res.data, `converted_${outputFormat.value}.zip`)
    emit('download-complete')
  } catch (e) {
    console.error('Download failed:', e)
    emit('error', e.response?.data?.detail || e.message)
  } finally {
    downloading.value = false
  }
}

async function downloadGroup(groupName) {
  downloading.value = true
  emit('download-started')
  
  try {
    const formData = new FormData()
    formData.append('output_format', outputFormat.value)
    formData.append('groups', groupName)
    formData.append('preserve_structure', 'false')
    
    const res = await api.post(`/conversion/download-custom/${props.sessionId}`, formData, {
      responseType: 'blob',
      headers: { 'Content-Type': 'multipart/form-data' }
    })
    
    triggerDownload(res.data, `${groupName}_${outputFormat.value}.zip`)
    emit('download-complete')
  } catch (e) {
    console.error('Download failed:', e)
    emit('error', e.response?.data?.detail || e.message)
  } finally {
    downloading.value = false
  }
}

async function downloadSelected() {
  if (selectedGroup.value) {
    await downloadGroup(selectedGroup.value)
  }
}

async function downloadFile(filename) {
  try {
    const res = await api.get(`/conversion/download-file/${props.sessionId}/${filename}`, {
      params: { format: outputFormat.value },
      responseType: 'blob'
    })
    
    const ext = outputFormat.value === 'xlsx' ? '.xlsx' : '.csv'
    const baseName = filename.replace(/\.csv$/i, '')
    triggerDownload(res.data, `${baseName}${ext}`)
  } catch (e) {
    console.error('Download failed:', e)
    emit('error', e.response?.data?.detail || e.message)
  }
}

function triggerDownload(blob, filename) {
  const url = window.URL.createObjectURL(new Blob([blob]))
  const link = document.createElement('a')
  link.href = url
  link.setAttribute('download', filename)
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.URL.revokeObjectURL(url)
}

// Watch for session changes
watch(() => props.sessionId, (newVal) => {
  if (newVal) {
    loadConvertedFiles()
  }
}, { immediate: true })

// Lifecycle
onMounted(() => {
  if (props.sessionId) {
    loadConvertedFiles()
  }
})

// Expose refresh method
defineExpose({
  refresh: loadConvertedFiles
})
</script>

<style scoped>
.conversion-results {
  padding: var(--space-md);
}

.results-header {
  margin-bottom: var(--space-lg);
}

.download-controls {
  display: flex;
  gap: var(--space-md);
  align-items: flex-end;
  margin-bottom: var(--space-lg);
  flex-wrap: wrap;
}

.download-controls .form-group {
  min-width: 150px;
}

.edit-mode-toggle {
  margin-left: auto;
}

.toggle-label {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  cursor: pointer;
  user-select: none;
}

.toggle-input {
  position: absolute;
  opacity: 0;
  width: 0;
  height: 0;
}

.toggle-slider {
  width: 44px;
  height: 24px;
  background: var(--surface-2);
  border-radius: 12px;
  position: relative;
  transition: background 0.2s;
}

.toggle-slider::before {
  content: '';
  position: absolute;
  top: 2px;
  left: 2px;
  width: 20px;
  height: 20px;
  background: white;
  border-radius: 50%;
  transition: transform 0.2s;
}

.toggle-input:checked + .toggle-slider {
  background: var(--brand);
}

.toggle-input:checked + .toggle-slider::before {
  transform: translateX(20px);
}

.toggle-text {
  font-weight: 600;
  font-size: 0.875rem;
}

.selection-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-lg);
  margin-bottom: var(--space-lg);
}

@media (max-width: 768px) {
  .selection-grid {
    grid-template-columns: 1fr;
  }
}

/* File Tabs */
.file-tabs-section {
  padding: var(--space-md);
  background: var(--surface);
  border-radius: var(--radius-md);
}

.file-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  padding: var(--space-sm) 0;
  border-bottom: 2px solid var(--border);
  margin-bottom: var(--space-md);
  max-height: 120px;
  overflow-y: auto;
}

.file-tab {
  padding: var(--space-xs) var(--space-md);
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-bottom: none;
  border-radius: var(--radius-sm) var(--radius-sm) 0 0;
  cursor: pointer;
  font-size: 0.8rem;
  font-weight: 500;
  color: var(--muted);
  transition: all 0.15s;
  display: flex;
  flex-direction: column;
  align-items: center;
  min-width: 80px;
  max-width: 160px;
}

.file-tab:hover {
  background: var(--surface-3);
  color: var(--foreground);
}

.file-tab.active {
  background: var(--brand);
  color: white;
  border-color: var(--brand);
}

.tab-meta {
  font-size: 0.65rem;
  opacity: 0.7;
  margin-top: 2px;
}

/* File Info Bar */
.file-info-bar {
  display: flex;
  align-items: center;
  gap: var(--space-md);
  padding: var(--space-sm) var(--space-md);
  background: var(--surface-2);
  border-radius: var(--radius-sm);
  margin-bottom: var(--space-md);
  flex-wrap: wrap;
}

.file-name {
  font-weight: 700;
  font-size: 0.9rem;
}

.file-stats {
  color: var(--muted);
  font-size: 0.8rem;
}

.file-actions {
  margin-left: auto;
  display: flex;
  gap: var(--space-sm);
}

/* Spreadsheet */
.spreadsheet-container {
  position: relative;
  min-height: 300px;
  max-height: 500px;
  overflow: auto;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--surface);
}

.spreadsheet-container.edit-mode-active {
  border-color: var(--brand);
  box-shadow: 0 0 0 2px rgba(var(--brand-rgb), 0.2);
}

.loading-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(var(--background-rgb), 0.8);
  z-index: 10;
}

.spreadsheet-wrapper {
  overflow: auto;
}

.spreadsheet {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.8rem;
  font-family: 'SF Mono', 'Monaco', 'Consolas', monospace;
}

.spreadsheet th,
.spreadsheet td {
  padding: 6px 10px;
  text-align: left;
  border: 1px solid var(--border);
  white-space: nowrap;
}

.spreadsheet thead tr {
  background: var(--surface-2);
  position: sticky;
  top: 0;
  z-index: 5;
}

.spreadsheet th.row-number,
.spreadsheet td.row-number {
  background: var(--surface-2);
  color: var(--muted);
  font-weight: 600;
  text-align: center;
  width: 50px;
  min-width: 50px;
  position: sticky;
  left: 0;
  z-index: 3;
}

.spreadsheet .header-cell {
  font-weight: 700;
  color: var(--foreground);
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.spreadsheet .row-actions-header {
  width: 60px;
}

.data-cell {
  max-width: 250px;
  position: relative;
}

.cell-display {
  overflow: hidden;
  text-overflow: ellipsis;
  min-height: 20px;
}

.cell-display.editable {
  cursor: cell;
  padding: 2px;
  border-radius: 2px;
}

.cell-display.editable:hover {
  background: rgba(var(--brand-rgb), 0.1);
}

.cell-input {
  width: 100%;
  padding: 4px;
  border: 2px solid var(--brand);
  border-radius: 2px;
  font-size: inherit;
  font-family: inherit;
  background: var(--background);
  color: var(--foreground);
}

.cell-modified {
  background: rgba(255, 193, 7, 0.15) !important;
}

.cell-editing {
  padding: 0 !important;
}

.row-actions {
  width: 40px;
  text-align: center;
  position: sticky;
  right: 0;
  background: var(--surface);
}

.btn-icon {
  background: none;
  border: none;
  cursor: pointer;
  padding: 4px;
  font-size: 0.9rem;
  opacity: 0.6;
  transition: opacity 0.15s;
}

.btn-icon:hover {
  opacity: 1;
}

.add-row-section {
  padding: var(--space-sm);
  border-top: 1px solid var(--border);
  background: var(--surface-2);
}

.no-preview {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 200px;
  color: var(--muted);
}

/* Preview Footer */
.preview-footer {
  padding: var(--space-sm) var(--space-md);
  background: var(--surface-2);
  border-top: 1px solid var(--border);
  font-size: 0.8rem;
  color: var(--muted);
  border-radius: 0 0 var(--radius-md) var(--radius-md);
}

.changes-indicator {
  color: var(--warning);
  font-weight: 600;
}

/* Data Table (reused) */
.data-table-wrapper {
  overflow-x: auto;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.875rem;
}

.data-table th,
.data-table td {
  padding: var(--space-sm) var(--space-md);
  text-align: left;
  border-bottom: 1px solid var(--border);
}

.data-table th {
  background: var(--surface-2);
  font-weight: 600;
  position: sticky;
  top: 0;
}

.data-table tbody tr:hover {
  background: var(--surface-2);
  cursor: pointer;
}

.data-table tbody tr.selected {
  background: rgba(var(--brand-rgb), 0.1);
}

.spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid transparent;
  border-top-color: currentColor;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin-right: var(--space-xs);
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
