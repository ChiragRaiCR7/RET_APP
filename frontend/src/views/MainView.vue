<template>
  <div>
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
        {{ tab }}
      </button>
    </div>

    <!-- TAB 0: Convert & Download -->
    <section v-show="activeTab === 0" class="enterprise-card" role="tabpanel">
      <div class="card-header">
        <div class="card-title-group">
          <h3 class="card-title">🔄 Utility Workflow</h3>
          <p class="card-description">Upload ZIP → Scan → Convert to CSV/XLSX</p>
        </div>
      </div>

      <!-- Workflow Controls -->
      <div class="info-grid" style="margin-bottom:var(--space-lg)">
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

      <div style="display:grid; grid-template-columns: 1fr 420px; gap:var(--space-lg);">
        <!-- Left: Upload & Table -->
        <div>
          <FileUploader @uploaded="onUploaded" />
          
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

          <!-- Scan Summary Metrics -->
          <div v-if="workflow.scanSummary" class="metric-container" style="margin-top:var(--space-xl)">
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

          <!-- Groups Table -->
          <div v-if="workflow.scannedGroups.length" style="margin-top:var(--space-lg)">
            <h4 class="card-title">Scanned Groups</h4>
            <div class="data-table-wrapper" style="margin-top:var(--space-md)">
              <table class="data-table" role="table">
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
        </div>

        <!-- Right: Group Preview -->
        <div>
          <div class="enterprise-card">
            <h4 class="card-title">Group Preview</h4>
            <p class="card-description">Preview of extracted XML groups</p>
            
            <div v-if="selectedGroup" style="margin-top:var(--space-md)">
              <div class="info-item">
                <div class="info-label">Selected Group</div>
                <div class="info-value">{{ selectedGroup.name }}</div>
              </div>
              <div class="info-item">
                <div class="info-label">Files</div>
                <div class="info-value">{{ selectedGroup.fileCount }}</div>
              </div>
              <div class="info-item">
                <div class="info-label">Total Rows</div>
                <div class="info-value">{{ selectedGroup.totalRows || '—' }}</div>
              </div>
            </div>
            
            <div v-else class="alert alert-info" style="margin-top:var(--space-md)">
              <div class="alert-content">Scan a ZIP to see group details</div>
            </div>

            <!-- Group File List -->
            <div v-if="selectedGroup?.files" style="margin-top:var(--space-md); max-height:300px; overflow-y:auto">
              <div v-for="(file, idx) in selectedGroup.files" :key="idx" class="info-item">
                <div class="info-label">{{ file.name }}</div>
                <div class="info-value">{{ file.size }}</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- TAB 1: Compare -->
    <section v-show="activeTab === 1" class="enterprise-card" role="tabpanel">
      <div class="card-header">
        <div class="card-title-group">
          <h3 class="card-title">📊 Compare ZIP/XML/CSV</h3>
          <p class="card-description">Side-by-side delta analysis</p>
        </div>
      </div>

      <div style="display:grid; grid-template-columns:1fr 1fr; gap:var(--space-lg); margin-bottom:var(--space-lg)">
        <!-- Side A -->
        <div class="enterprise-card">
          <h4 class="card-title">Side A (Base)</h4>
          <FileUploader @uploaded="(f) => compare.sideA = f[0]" />
          <div v-if="compare.sideA" class="info-item" style="margin-top:var(--space-md)">
            <div class="info-label">File</div>
            <div class="info-value">{{ compare.sideA.name }}</div>
          </div>
        </div>

        <!-- Side B -->
        <div class="enterprise-card">
          <h4 class="card-title">Side B (Compare)</h4>
          <FileUploader @uploaded="(f) => compare.sideB = f[0]" />
          <div v-if="compare.sideB" class="info-item" style="margin-top:var(--space-md)">
            <div class="info-label">File</div>
            <div class="info-value">{{ compare.sideB.name }}</div>
          </div>
        </div>
      </div>

      <button 
        class="btn btn-primary" 
        @click="runComparison" 
        :disabled="!compare.sideA || !compare.sideB || comparing"
      >
        <span v-if="comparing" class="spinner" style="margin-right:8px"></span>
        {{ comparing ? 'Comparing...' : 'Compare Now' }}
      </button>

      <!-- Comparison Results -->
      <div v-if="compare.results" style="margin-top:var(--space-xl)">
        <div class="metric-container">
          <div class="metric-card">
            <div class="metric-value">{{ compare.results.similarity }}%</div>
            <div class="metric-label">Similarity</div>
          </div>
          <div class="metric-card">
            <div class="metric-value" style="color:var(--success)">+{{ compare.results.added }}</div>
            <div class="metric-label">Added Rows</div>
          </div>
          <div class="metric-card">
            <div class="metric-value" style="color:var(--error)">-{{ compare.results.removed }}</div>
            <div class="metric-label">Removed Rows</div>
          </div>
          <div class="metric-card">
            <div class="metric-value" style="color:var(--warning)">{{ compare.results.modified }}</div>
            <div class="metric-label">Modified Rows</div>
          </div>
        </div>

        <!-- Change Details Table -->
        <div class="enterprise-card" style="margin-top:var(--space-lg)">
          <h4 class="card-title">Change Details</h4>
          <DataTable 
            :headers="['Type', 'Row ID', 'Field', 'Old Value', 'New Value']"
            :columns="['type', 'rowId', 'field', 'oldValue', 'newValue']"
            :rows="compare.results.changes || []"
            aria-label="Comparison changes table"
          />
        </div>
      </div>
    </section>

    <!-- TAB 2: Ask RET AI -->
    <section v-show="activeTab === 2" class="enterprise-card" role="tabpanel">
      <div class="card-header">
        <div class="card-title-group">
          <h3 class="card-title">🤖 Ask RET AI</h3>
          <p class="card-description">Query conversions, compare results, or ask questions</p>
        </div>
      </div>

      <!-- Memory Tools -->
      <details class="enterprise-card" style="margin-bottom:var(--space-lg)">
        <summary style="cursor:pointer; font-weight:700; padding:var(--space-md)">
          Session Memory Tools
        </summary>
        <div style="padding:var(--space-md)">
          <div class="form-group">
            <label class="form-label">Index XML Groups (for AI context)</label>
            <select v-model="ai.selectedGroups" multiple class="form-select" size="5">
              <option v-for="g in workflow.scannedGroups" :key="g.name" :value="g.name">
                {{ g.name }}
              </option>
            </select>
          </div>
          <div style="display:flex; gap:8px; margin-top:var(--space-md)">
            <button class="btn btn-primary btn-sm" @click="indexGroups" :disabled="!ai.selectedGroups.length">
              Index Selected Groups
            </button>
            <button class="btn btn-danger btn-sm" @click="clearMemory">
              Clear Memory
            </button>
          </div>
          <div v-if="ai.indexStatus" class="alert alert-info" style="margin-top:var(--space-md)">
            <div class="alert-content">{{ ai.indexStatus }}</div>
          </div>
        </div>
      </details>

      <!-- AI Chat Interface -->
      <AIChatInterface />
    </section>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import FileUploader from '@/components/workspace/FileUploader.vue'
import AIChatInterface from '@/components/workspace/AIChatInterface.vue'
import DataTable from '@/components/common/DataTable.vue'
import api from '@/utils/api'

const activeTab = ref(0)
const tabs = ['Convert & Download', 'Compare', 'Ask RET AI']

const workflow = reactive({
  outputFormat: 'csv',
  editMode: 'none',
  includePrefixes: true,
  uploadedFiles: [],
  scannedGroups: [],
  scanSummary: null
})

const scanning = ref(false)
const selectedGroup = ref(null)

const compare = reactive({
  sideA: null,
  sideB: null,
  results: null
})
const comparing = ref(false)

const ai = reactive({
  selectedGroups: [],
  indexStatus: null
})

function onUploaded(files) {
  workflow.uploadedFiles.push(...files)
}

async function scanZip() {
  scanning.value = true
  try {
    const formData = new FormData()
    workflow.uploadedFiles.forEach(f => formData.append('files', f))
    
    const res = await api.post('/workflow/scan', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
    
    workflow.scannedGroups = res.data.groups || []
    workflow.scanSummary = res.data.summary || { totalGroups: 0, totalFiles: 0, totalSize: '0 KB' }
    
    if (workflow.scannedGroups.length > 0) {
      selectedGroup.value = workflow.scannedGroups[0]
    }
  } catch (e) {
    alert('Scan failed: ' + (e.response?.data?.message || e.message))
  } finally {
    scanning.value = false
  }
}

function clearWorkflow() {
  workflow.uploadedFiles = []
  workflow.scannedGroups = []
  workflow.scanSummary = null
  selectedGroup.value = null
}

async function convertGroup(group) {
  try {
    const res = await api.post('/workflow/convert', {
      groupName: group.name,
      format: workflow.outputFormat,
      editMode: workflow.editMode,
      includePrefixes: workflow.includePrefixes
    }, { responseType: 'blob' })
    
    // Download converted file
    const blob = new Blob([res.data])
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${group.name}.${workflow.outputFormat}`
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    alert('Conversion failed: ' + (e.response?.data?.message || e.message))
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

async function runComparison() {
  comparing.value = true
  try {
    const formData = new FormData()
    formData.append('sideA', compare.sideA)
    formData.append('sideB', compare.sideB)
    
    const res = await api.post('/compare/run', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
    
    compare.results = res.data
  } catch (e) {
    alert('Comparison failed: ' + (e.response?.data?.message || e.message))
  } finally {
    comparing.value = false
  }
}

async function indexGroups() {
  try {
    const res = await api.post('/ai/index', { groups: ai.selectedGroups })
    ai.indexStatus = res.data.message || 'Groups indexed successfully'
    setTimeout(() => ai.indexStatus = null, 5000)
  } catch (e) {
    ai.indexStatus = 'Indexing failed: ' + (e.response?.data?.message || e.message)
  }
}

async function clearMemory() {
  try {
    await api.post('/ai/clear-memory')
    ai.indexStatus = 'Memory cleared successfully'
    ai.selectedGroups = []
    setTimeout(() => ai.indexStatus = null, 3000)
  } catch (e) {
    alert('Failed to clear memory: ' + (e.response?.data?.message || e.message))
  }
}

onMounted(() => {
  // Initialize on mount
})
</script>