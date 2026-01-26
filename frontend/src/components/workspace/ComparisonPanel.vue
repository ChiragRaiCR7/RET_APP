<template>
  <div class="comparison-panel">
    <!-- Side-by-side file upload -->
    <div class="upload-grid">
      <div class="side-container">
        <h4 class="card-title">📄 Side A (Base)</h4>
        <FileUploader @uploaded="(f) => comparison.sideA = f[0]" />
        <div v-if="comparison.sideA" class="info-item" style="margin-top:var(--space-md)">
          <div class="info-label">File</div>
          <div class="info-value">{{ comparison.sideA.name }}</div>
        </div>
      </div>

      <div class="side-container">
        <h4 class="card-title">📄 Side B (Compare)</h4>
        <FileUploader @uploaded="(f) => comparison.sideB = f[0]" />
        <div v-if="comparison.sideB" class="info-item" style="margin-top:var(--space-md)">
          <div class="info-label">File</div>
          <div class="info-value">{{ comparison.sideB.name }}</div>
        </div>
      </div>
    </div>

    <!-- Compare Button -->
    <div style="margin-top:var(--space-lg); display:flex; gap:12px">
      <button 
        class="btn btn-primary" 
        @click="runComparison" 
        :disabled="!comparison.sideA || !comparison.sideB || comparing"
      >
        <span v-if="comparing" class="spinner" style="margin-right:8px"></span>
        {{ comparing ? 'Comparing...' : 'Compare Now' }}
      </button>
    </div>

    <!-- Results -->
    <div v-if="comparison.results" style="margin-top:var(--space-xl)">
      <h4 class="card-title">📊 Comparison Results</h4>
      
      <!-- Summary Metrics -->
      <div class="metric-container" style="margin-top:var(--space-md)">
        <div class="metric-card">
          <div class="metric-value">{{ comparison.results.similarity }}%</div>
          <div class="metric-label">Similarity</div>
        </div>
        <div class="metric-card">
          <div class="metric-value" style="color:var(--success)">+{{ comparison.results.added }}</div>
          <div class="metric-label">Added Rows</div>
        </div>
        <div class="metric-card">
          <div class="metric-value" style="color:var(--error)">-{{ comparison.results.removed }}</div>
          <div class="metric-label">Removed Rows</div>
        </div>
        <div class="metric-card">
          <div class="metric-value" style="color:var(--warning)">{{ comparison.results.modified }}</div>
          <div class="metric-label">Modified Rows</div>
        </div>
      </div>

      <!-- Changes Table -->
      <div style="margin-top:var(--space-xl)">
        <h4 class="card-title">🔍 Change Details</h4>
        
        <div v-if="comparison.results.changes.length === 0" class="alert alert-info">
          No changes detected - files are identical
        </div>

        <div v-else class="data-table-wrapper" style="margin-top:var(--space-md)">
          <table class="data-table">
            <thead>
              <tr>
                <th>Change Type</th>
                <th>Row ID</th>
                <th>Field</th>
                <th>Old Value</th>
                <th>New Value</th>
                <th>Indicator</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(change, idx) in comparison.results.changes.slice(0, 100)" :key="idx">
                <td>
                  <span class="badge" :class="getBadgeClass(change.type)">
                    {{ change.type }}
                  </span>
                </td>
                <td>{{ change.row_id }}</td>
                <td v-if="change.field">{{ change.field }}</td>
                <td v-else>-</td>
                <td v-if="change.old_value" class="truncate">
                  {{ change.old_value }}
                </td>
                <td v-else>-</td>
                <td v-if="change.new_value" class="truncate">
                  {{ change.new_value }}
                </td>
                <td v-else>-</td>
                <td>{{ change.indicator }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div v-if="comparison.results.changes.length > 100" class="alert alert-info">
          Showing first 100 of {{ comparison.results.changes.length }} changes
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import FileUploader from './FileUploader.vue'
import api from '@/utils/api'

const comparison = reactive({
  sideA: null,
  sideB: null,
  results: null
})

const comparing = ref(false)

function getBadgeClass(type) {
  switch (type) {
    case 'added':
      return 'badge-success'
    case 'removed':
      return 'badge-error'
    case 'modified':
      return 'badge-warning'
    default:
      return 'badge-info'
  }
}

async function runComparison() {
  comparing.value = true
  try {
    const formData = new FormData()
    formData.append('sideA', comparison.sideA)
    formData.append('sideB', comparison.sideB)
    
    const res = await api.post('/api/comparison/run', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
    
    comparison.results = res.data
  } catch (e) {
    alert('Comparison failed: ' + (e.response?.data?.detail || e.message))
  } finally {
    comparing.value = false
  }
}
</script>

<style scoped>
.comparison-panel {
  padding: var(--space-lg);
}

.upload-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-lg);
  margin-bottom: var(--space-lg);
}

.side-container {
  background: var(--surface-base);
  padding: var(--space-lg);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-color);
}

.badge {
  display: inline-block;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 0.85rem;
  font-weight: 600;
}

.badge-success {
  background-color: var(--success);
  color: white;
}

.badge-error {
  background-color: var(--error);
  color: white;
}

.badge-warning {
  background-color: var(--warning);
  color: white;
}

.badge-info {
  background-color: var(--info);
  color: white;
}

.truncate {
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
