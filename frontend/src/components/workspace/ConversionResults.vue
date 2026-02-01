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
    </div>

    <!-- Groups and Files Selection -->
    <div class="selection-grid">
      <!-- Groups Dropdown -->
      <div class="form-group">
        <label class="form-label">Select Group</label>
        <select v-model="selectedGroup" class="form-select" @change="onGroupChange">
          <option value="">All Groups</option>
          <option v-for="g in groups" :key="g.name" :value="g.name">
            {{ g.name }} ({{ g.file_count }} files, {{ g.total_rows }} rows)
          </option>
        </select>
      </div>

      <!-- Files Dropdown -->
      <div class="form-group">
        <label class="form-label">Select File</label>
        <select v-model="selectedFile" class="form-select" @change="onFileChange">
          <option value="">-- Select a file --</option>
          <option v-for="f in filteredFiles" :key="f.filename" :value="f.filename">
            {{ f.filename }} ({{ f.rows }} rows, {{ f.columns }} cols)
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

    <!-- Files Table -->
    <div v-if="filteredFiles.length > 0" class="enterprise-card" style="margin-top: var(--space-lg)">
      <h4 class="card-title">
        Files {{ selectedGroup ? `in ${selectedGroup}` : '(All)' }}
      </h4>
      <div class="data-table-wrapper">
        <table class="data-table">
          <thead>
            <tr>
              <th>Filename</th>
              <th>Group</th>
              <th>Rows</th>
              <th>Columns</th>
              <th>Size</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr 
              v-for="f in filteredFiles" 
              :key="f.filename" 
              :class="{ selected: selectedFile === f.filename }"
              @click="selectFile(f.filename)"
            >
              <td><strong>{{ f.filename }}</strong></td>
              <td>{{ f.group }}</td>
              <td>{{ f.rows.toLocaleString() }}</td>
              <td>{{ f.columns }}</td>
              <td>{{ f.size }}</td>
              <td>
                <button class="btn btn-sm btn-primary" @click.stop="previewFile(f.filename)">
                  👁️ Preview
                </button>
                <button class="btn btn-sm btn-secondary" @click.stop="downloadFile(f.filename)">
                  ⬇️ Download
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- File Preview Modal/Section -->
    <div v-if="preview" class="enterprise-card preview-section" style="margin-top: var(--space-lg)">
      <div class="preview-header">
        <h4 class="card-title">📄 Preview: {{ preview.filename }}</h4>
        <div class="preview-meta">
          {{ preview.preview_rows }} of {{ preview.total_rows }} rows | {{ preview.columns }} columns
        </div>
        <button class="btn btn-sm btn-secondary" @click="preview = null">Close Preview</button>
      </div>
      
      <div class="data-table-wrapper preview-table" style="max-height: 400px; overflow: auto">
        <table class="data-table">
          <thead>
            <tr>
              <th v-for="(header, idx) in preview.headers" :key="idx">{{ header }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, rowIdx) in preview.rows" :key="rowIdx">
              <td v-for="(cell, cellIdx) in row" :key="cellIdx">{{ truncateCell(cell) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
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
const downloading = ref(false)
const outputFormat = ref('csv')
const selectedGroup = ref('')
const selectedFile = ref('')
const groups = ref([])
const files = ref([])
const preview = ref(null)
const totalFiles = ref(0)

// Computed
const filteredFiles = computed(() => {
  if (!selectedGroup.value) return files.value
  return files.value.filter(f => f.group === selectedGroup.value)
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

function truncateCell(value, maxLen = 100) {
  if (!value) return ''
  const str = String(value)
  return str.length > maxLen ? str.substring(0, maxLen) + '...' : str
}

async function loadConvertedFiles() {
  if (!props.sessionId) return
  
  loading.value = true
  try {
    const res = await api.get(`/conversion/files/${props.sessionId}`)
    groups.value = res.data.groups || []
    files.value = res.data.files || []
    totalFiles.value = res.data.total_files || 0
  } catch (e) {
    console.error('Failed to load converted files:', e)
    emit('error', e.response?.data?.detail || e.message)
  } finally {
    loading.value = false
  }
}

function onGroupChange() {
  selectedFile.value = ''
  preview.value = null
}

function onFileChange() {
  if (selectedFile.value) {
    previewFile(selectedFile.value)
  }
}

function selectGroup(groupName) {
  selectedGroup.value = groupName
  preview.value = null
}

function selectFile(filename) {
  selectedFile.value = filename
  previewFile(filename)
}

async function previewFile(filename) {
  try {
    const res = await api.get(`/conversion/preview/${props.sessionId}/${filename}`, {
      params: { max_rows: 100 }
    })
    preview.value = res.data
  } catch (e) {
    console.error('Failed to preview file:', e)
    emit('error', e.response?.data?.detail || e.message)
  }
}

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

.preview-section {
  background: var(--surface);
}

.preview-header {
  display: flex;
  align-items: center;
  gap: var(--space-md);
  margin-bottom: var(--space-md);
  flex-wrap: wrap;
}

.preview-meta {
  color: var(--muted);
  font-size: 0.875rem;
  flex: 1;
}

.preview-table {
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
}

.preview-table .data-table td {
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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
