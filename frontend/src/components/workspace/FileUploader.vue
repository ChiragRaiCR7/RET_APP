<template>
  <div>
    <div 
      class="file-upload-zone" 
      @dragover.prevent="dragging = true" 
      @dragleave.prevent="dragging = false" 
      @drop.prevent="onDrop" 
      :class="{ dragging }" 
      @click="open"
    >
      <div class="file-upload-icon" aria-hidden="true">📦</div>
      <div><strong>Drop ZIP files here, or click to upload</strong></div>
      <div class="form-hint">Supports bulk ZIP. Max 200MB. We'll scan and show a preview.</div>
    </div>
    
    <input 
      ref="input" 
      type="file" 
      multiple 
      @change="onFiles" 
      style="display:none" 
      accept=".zip,application/zip" 
    />
    
    <div v-if="files.length" style="margin-top: var(--space-md)">
      <div v-for="(f, i) in files" :key="i" class="info-item">
        <div style="display:flex; justify-content:space-between;">
          <div>
            <div style="font-weight:800">{{ f.name }}</div>
            <div class="form-hint">{{ prettySize(f.size) }} • {{ f.type || 'zip' }}</div>
          </div>
          <div style="display:flex; gap:8px; align-items:center">
            <button 
              class="btn btn-sm btn-primary" 
              @click.stop="scanFile(f)"
              :disabled="scanning"
            >
              <span v-if="scanning" class="spinner" style="margin-right:4px"></span>
              {{ scanning ? 'Scanning...' : 'Scan' }}
            </button>
            <button class="btn btn-sm" @click.stop="remove(i)">Remove</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Scan Results -->
    <div v-if="scanResults" style="margin-top: var(--space-lg)">
      <div class="enterprise-card">
        <h4 class="card-title">📊 Scan Results</h4>
        
        <div class="metric-container">
          <div class="metric-card">
            <div class="metric-value">{{ scanResults.xml_count }}</div>
            <div class="metric-label">XML Files</div>
          </div>
          <div class="metric-card">
            <div class="metric-value">{{ scanResults.group_count }}</div>
            <div class="metric-label">Groups Found</div>
          </div>
          <div class="metric-card">
            <div class="metric-value">{{ prettySize(scanResults.summary.totalSize) }}</div>
            <div class="metric-label">Total Size</div>
          </div>
        </div>

        <!-- Groups Table -->
        <div style="margin-top: var(--space-lg)">
          <h5 class="card-title">Groups Detected</h5>
          <table class="data-table" role="table">
            <thead>
              <tr>
                <th>Group Name</th>
                <th>Files</th>
                <th>Size</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="group in scanResults.groups" :key="group.name">
                <td><strong>{{ group.name }}</strong></td>
                <td>{{ group.file_count }}</td>
                <td>{{ prettySize(group.size) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- Error Display -->
    <div v-if="error" style="margin-top: var(--space-md); padding: var(--space-md); background: #fee; color: #c33; border-radius: 4px;">
      <strong>Error:</strong> {{ error }}
      <button 
        @click="error = ''"
        style="float: right; background: none; border: none; cursor: pointer; font-size: 16px;"
      >
        ×
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import api from '@/utils/api'

const input = ref(null)
const files = ref([])
const dragging = ref(false)
const scanning = ref(false)
const scanResults = ref(null)
const error = ref('')

// Define emits
const emit = defineEmits(['uploaded', 'scanned'])

function open() {
  input.value?.click()
}

function onFiles(e) {
  const list = Array.from(e.target.files || [])
  files.value.push(...list)
  error.value = ''
}

function onDrop(e) {
  dragging.value = false
  const list = Array.from(e.dataTransfer.files || [])
  files.value.push(...list)
  error.value = ''
}

function remove(i) {
  files.value.splice(i, 1)
}

function prettySize(n) {
  if (!n) return '-'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / (1024 * 1024)).toFixed(1)} MB`
}

async function scanFile(file) {
  const data = new FormData()
  data.append('file', file)
  scanning.value = true
  error.value = ''
  
  try {
    const resp = await api.post('/conversion/scan', data, { 
      headers: { 'Content-Type': 'multipart/form-data' } 
    })
    
    scanResults.value = resp.data
    emit('scanned', resp.data)
    emit('uploaded', {
      sessionId: resp.data.session_id,
      groups: resp.data.groups,
      xmlCount: resp.data.xml_count,
    })
  } catch (e) {
    error.value = e.response?.data?.detail || e.response?.data?.message || e.message || 'Unknown error'
    console.error('Scan error:', e)
  } finally {
    scanning.value = false
  }
}
</script>

<style scoped>
.file-upload-zone {
  border: 2px dashed #ccc;
  border-radius: 8px;
  padding: 2rem;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s;
}

.file-upload-zone:hover {
  border-color: #666;
  background: #f9f9f9;
}

.file-upload-zone.dragging {
  border-color: #007bff;
  background: #e7f3ff;
}

.file-upload-icon {
  font-size: 2.5rem;
  margin-bottom: 0.5rem;
}

.spinner {
  display: inline-block;
  width: 12px;
  height: 12px;
  border: 2px solid #f3f3f3;
  border-top: 2px solid #007bff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}
</style>
