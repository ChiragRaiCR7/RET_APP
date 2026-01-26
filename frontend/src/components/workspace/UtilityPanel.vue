<template>
  <div class="utility-panel">
    <!-- ZIP Upload Section -->
    <div class="upload-section">
      <FileUploader @uploaded="onUploaded" />
      
      <!-- Workflow Controls -->
      <div class="info-grid" style="margin-top:var(--space-lg)">
        <div class="form-group">
          <label class="form-label">Output Format</label>
          <select v-model="workflow.outputFormat" class="form-select">
            <option value="csv">CSV</option>
            <option value="xlsx">Excel (XLSX)</option>
          </select>
        </div>
        <div class="form-group">
          <label class="form-label">Edit Mode</label>
          <select v-model="workflow.editMode" class="form-select">
            <option value="none">No Edits</option>
            <option value="minimal">Minimal Edits</option>
            <option value="full">Full Edits</option>
          </select>
        </div>
        <div class="form-group">
          <label class="form-label">Include Prefixes</label>
          <select v-model="workflow.includePrefixes" class="form-select">
            <option :value="true">Yes</option>
            <option :value="false">No</option>
          </select>
        </div>
      </div>

      <!-- Action Buttons -->
      <div style="display:flex; gap:12px; margin-top:var(--space-lg)">
        <button class="btn btn-primary" @click="scanZip" :disabled="!workflow.uploadedFiles.length || scanning">
          <span v-if="scanning" class="spinner" style="margin-right:8px"></span>
          {{ scanning ? 'Scanning...' : 'Scan ZIP' }}
        </button>
        <button class="btn btn-secondary" @click="clearWorkflow">Clear</button>
        <button class="btn btn-success" @click="bulkConvert" :disabled="!workflow.scannedGroups.length">
          Bulk Convert All
        </button>
      </div>
    </div>

    <!-- Scan Results -->
    <div v-if="workflow.scanSummary" style="margin-top:var(--space-xl)">
      <h4 class="card-title">📊 Scan Summary</h4>
      <div class="metric-container" style="margin-top:var(--space-md)">
        <div class="metric-card">
          <div class="metric-value">{{ workflow.scanSummary.totalGroups }}</div>
          <div class="metric-label">Groups Found</div>
        </div>
        <div class="metric-card">
          <div class="metric-value">{{ workflow.scanSummary.totalFiles }}</div>
          <div class="metric-label">XML Files</div>
        </div>
        <div class="metric-card">
          <div class="metric-value">{{ workflow.scanSummary.totalSize }}</div>
          <div class="metric-label">Total Size</div>
        </div>
      </div>
    </div>

    <!-- Groups Table -->
    <div v-if="workflow.scannedGroups.length" style="margin-top:var(--space-xl)">
      <h4 class="card-title">📂 Detected Groups</h4>
      <div class="data-table-wrapper" style="margin-top:var(--space-md)">
        <table class="data-table">
          <thead>
            <tr>
              <th>Group Name</th>
              <th>Files</th>
              <th>Size</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(group, idx) in workflow.scannedGroups" :key="idx">
              <td><strong>{{ group.name }}</strong></td>
              <td>{{ group.fileCount }} files</td>
              <td>{{ group.size }}</td>
              <td>
                <button class="btn btn-sm btn-primary" @click="convertGroup(group)">
                  Convert
                </button>
                <button class="btn btn-sm btn-secondary" @click="downloadGroup(group)">
                  Download
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Group Preview -->
    <div v-if="selectedGroup" style="margin-top:var(--space-xl)">
      <h4 class="card-title">📋 Group Preview</h4>
      <div class="enterprise-card">
        <div class="info-item">
          <div class="info-label">Selected Group</div>
          <div class="info-value">{{ selectedGroup.name }}</div>
        </div>
        <div class="info-item">
          <div class="info-label">File Count</div>
          <div class="info-value">{{ selectedGroup.fileCount }}</div>
        </div>
        <div class="info-item">
          <div class="info-label">Total Size</div>
          <div class="info-value">{{ selectedGroup.size }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import FileUploader from './FileUploader.vue'
import api from '@/utils/api'

const workflow = reactive({
  outputFormat: 'csv',
  editMode: 'none',
  includePrefixes: true,
  uploadedFiles: [],
  scannedGroups: [],
  scanSummary: null,
  sessionId: null
})

const scanning = ref(false)
const selectedGroup = ref(null)

function onUploaded(files) {
  workflow.uploadedFiles.push(...files)
}

async function scanZip() {
  scanning.value = true
  try {
    const formData = new FormData()
    workflow.uploadedFiles.forEach(f => formData.append('files', f))
    
    const res = await api.post('/api/workflow/scan', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
    
    workflow.sessionId = res.data.session_id
    workflow.scannedGroups = res.data.groups || []
    workflow.scanSummary = res.data.summary || { 
      totalGroups: 0, 
      totalFiles: 0, 
      totalSize: '0 KB' 
    }
    
    if (workflow.scannedGroups.length > 0) {
      selectedGroup.value = workflow.scannedGroups[0]
    }
  } catch (e) {
    alert('Scan failed: ' + (e.response?.data?.detail || e.message))
  } finally {
    scanning.value = false
  }
}

function clearWorkflow() {
  workflow.uploadedFiles = []
  workflow.scannedGroups = []
  workflow.scanSummary = null
  workflow.sessionId = null
  selectedGroup.value = null
}

async function convertGroup(group) {
  try {
    const res = await api.post('/api/workflow/convert', {
      groupName: group.name,
      format: workflow.outputFormat,
      editMode: workflow.editMode,
      includePrefixes: workflow.includePrefixes
    }, { responseType: 'blob' })
    
    // Download
    const blob = new Blob([res.data])
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${group.name}.${workflow.outputFormat}`
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    alert('Conversion failed: ' + (e.response?.data?.detail || e.message))
  }
}

async function bulkConvert() {
  for (const group of workflow.scannedGroups) {
    await convertGroup(group)
  }
}

function downloadGroup(group) {
  window.open(`/api/workflow/download/${encodeURIComponent(group.name)}`, '_blank')
}
</script>

<style scoped>
.utility-panel {
  padding: var(--space-lg);
}

.upload-section {
  background: var(--surface-base);
  padding: var(--space-lg);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-color);
}
</style>
