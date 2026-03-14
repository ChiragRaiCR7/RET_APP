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
      <div><strong>Drop ZIP / XML / CSV / XLSX / XLS here, or click to upload</strong></div>
      <div class="form-hint">
        Supports ZIP archives and individual XML/XML.GZ/CSV/XLSX/XLS files.
        Scans nested ZIPs and groups by module prefix. Large archives may take a few minutes.
      </div>
    </div>

    <input
      ref="input"
      type="file"
      multiple
      @change="onFiles"
      style="display:none"
      accept=".zip,.xml,.xml.gz,.csv,.xlsx,.xls,application/zip,text/xml,application/xml,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel"
    />

    <div v-if="files.length" style="margin-top: var(--space-md)">
      <div v-for="(f, i) in files" :key="i" class="info-item">
        <div style="display:flex; justify-content:space-between;">
          <div>
            <div style="font-weight:800">{{ f.name }}</div>
            <div class="form-hint">{{ prettySize(f.size) }} • {{ f.type || 'file' }}</div>
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

        <!-- Optional: show scan parameters in UI (nice for debugging) -->
        <div class="form-hint" style="margin-top:6px" v-if="showLimitsHint">
          Scan limits: max_unzipped_mb={{ scanLimits.max_unzipped_mb }},
          max_files={{ scanLimits.max_files }},
          max_depth={{ scanLimits.max_depth }}
        </div>
      </div>
    </div>

    <!-- Scan Results -->
    <div v-if="scanResults" style="margin-top: var(--space-lg)">
      <div class="enterprise-card">
        <h4 class="card-title">📊 Scan Results</h4>

        <div class="metric-container">
          <div class="metric-card">
            <div class="metric-value">{{ scanResults.file_count ?? scanResults.summary?.totalFiles ?? 0 }}</div>
            <div class="metric-label">Total Files</div>
          </div>

          <div class="metric-card">
            <div class="metric-value">{{ scanResults.xml_count ?? 0 }}</div>
            <div class="metric-label">XML Files</div>
          </div>

          <div class="metric-card">
            <div class="metric-value">{{ scanResults.group_count ?? 0 }}</div>
            <div class="metric-label">Groups Found</div>
          </div>

          <div class="metric-card">
            <div class="metric-value">{{ prettySize(scanResults.summary?.totalSize) }}</div>
            <div class="metric-label">Total Size</div>
          </div>
        </div>

        <!-- ✅ NEW: Type counts summary -->
        <div v-if="scanResults.summary?.typeCounts" class="typecounts">
          <div class="typecounts-title">File types</div>
          <div class="typecounts-badges">
            <span
              v-for="(count, typ) in scanResults.summary.typeCounts"
              :key="typ"
              class="type-badge"
            >
              {{ String(typ).toUpperCase() }}: <strong>{{ count }}</strong>
            </span>
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

        <!-- Optional: show scan warnings -->
        <div v-if="scanResults.warnings?.length" class="warn-box">
          <div class="warn-title">Warnings</div>
          <ul class="warn-list">
            <li v-for="(w, idx) in scanResults.warnings" :key="idx">{{ w }}</li>
          </ul>
        </div>
      </div>
    </div>

    <!-- Error Display -->
    <div
      v-if="error"
      style="margin-top: var(--space-md); padding: var(--space-md); background: #fee; color: #c33; border-radius: 4px;"
    >
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
import api, { longApi } from '@/utils/api'

const input = ref(null)
const files = ref([])
const dragging = ref(false)
const scanning = ref(false)
const scanResults = ref(null)
const error = ref('')

// You can flip this on/off if you want to show limits under each file row
const showLimitsHint = false

// ✅ Default scan limits (prevents max bytes stopping)
const scanLimits = {
  max_unzipped_mb: 5000, // 5 GB
  max_files: 200000,
  max_depth: 25,
  group_mode: 'zip'
}

// Define emits - 'files-added' for raw files, 'uploaded'/'scanned' for scan results
const emit = defineEmits(['uploaded', 'scanned', 'files-added'])

function open() {
  input.value?.click()
}

function onFiles(e) {
  const list = Array.from(e.target.files || [])
  files.value.push(...list)
  error.value = ''
  emit('files-added', list)
}

function onDrop(e) {
  dragging.value = false
  const list = Array.from(e.dataTransfer.files || [])
  files.value.push(...list)
  error.value = ''
  emit('files-added', list)
}

function remove(i) {
  files.value.splice(i, 1)
}

function prettySize(n) {
  if (n === null || n === undefined) return '-'
  const num = Number(n)
  if (!Number.isFinite(num) || num <= 0) return '-'
  if (num < 1024) return `${num} B`
  if (num < 1024 * 1024) return `${(num / 1024).toFixed(1)} KB`
  if (num < 1024 * 1024 * 1024) return `${(num / (1024 * 1024)).toFixed(1)} MB`
  return `${(num / (1024 * 1024 * 1024)).toFixed(1)} GB`
}

async function scanFile(file) {
  const data = new FormData()
  data.append('file', file)

  scanning.value = true
  error.value = ''

  try {
    // ✅ Use longApi + pass query params to avoid scan budget truncation
    const resp = await longApi.post('/conversion/scan', data, {
      params: {
        group_mode: scanLimits.group_mode,
        max_unzipped_mb: scanLimits.max_unzipped_mb,
        max_files: scanLimits.max_files,
        max_depth: scanLimits.max_depth
      },
      timeout: 15 * 60 * 1000 // 15 min
    })

    scanResults.value = resp.data
    emit('scanned', resp.data)

    // ✅ Emit a richer payload so MainView can build exclusion UI
    emit('uploaded', {
      sessionId: resp.data.session_id,
      session_id: resp.data.session_id,
      groups: resp.data.groups,
      xmlCount: resp.data.xml_count,
      xml_count: resp.data.xml_count,
      file_count: resp.data.file_count,
      files: resp.data.files,
      summary: resp.data.summary
    })
  } catch (e) {
    error.value =
      e.response?.data?.detail ||
      e.response?.data?.message ||
      e.message ||
      'Unknown error'
    console.error('Scan error:', e)
  } finally {
    scanning.value = false
  }
}
</script>

<style scoped>
.file-upload-zone {
  border: 2px dashed var(--border-medium);
  border-radius: var(--radius-lg);
  padding: var(--space-xl) var(--space-lg);
  text-align: center;
  cursor: pointer;
  transition: all var(--transition-base);
  background: var(--surface-base);
}

.file-upload-zone:hover {
  border-color: var(--brand-primary);
  background: var(--brand-subtle);
}

.file-upload-zone.dragging {
  border-color: var(--brand-primary);
  background: var(--brand-subtle);
  border-style: solid;
}

.file-upload-icon {
  font-size: 3rem;
  margin-bottom: var(--space-md);
}

.info-item {
  background: var(--surface-elevated);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  padding: var(--space-md);
  margin-bottom: var(--space-sm);
}

.metric-container {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: var(--space-md);
  margin-bottom: var(--space-lg);
}

.metric-card {
  background: var(--surface-elevated);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  padding: var(--space-md);
  text-align: center;
}

.metric-value {
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--brand-primary);
}

.metric-label {
  font-size: 0.85rem;
  color: var(--text-tertiary);
  margin-top: var(--space-xs);
}

.typecounts {
  margin-top: var(--space-md);
  padding: var(--space-md);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-light);
  background: var(--surface-base);
}

.typecounts-title {
  font-weight: 800;
  color: var(--text-primary);
  margin-bottom: 8px;
}

.typecounts-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.type-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 999px;
  background: var(--surface-elevated);
  border: 1px solid var(--border-light);
  color: var(--text-secondary);
  font-size: 0.85rem;
}

.warn-box {
  margin-top: var(--space-md);
  padding: var(--space-md);
  border-radius: var(--radius-md);
  border: 1px solid #f2c94c;
  background: #fff7db;
  color: #6b4f00;
}
.warn-title { font-weight: 900; margin-bottom: 6px; }
.warn-list { margin: 0; padding-left: 18px; }

.spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid transparent;
  border-top-color: currentColor;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>