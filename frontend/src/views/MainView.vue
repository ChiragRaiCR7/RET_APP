<template>
  <div>
    <div class="metric-container" role="region" aria-label="Quick stats">
      <div class="metric-card">
        <p class="metric-value">1,234</p>
        <p class="metric-label">Total Users</p>
      </div>
      <div class="metric-card">
        <p class="metric-value">12</p>
        <p class="metric-label">Admins</p>
      </div>
      <div class="metric-card">
        <p class="metric-value">1,222</p>
        <p class="metric-label">Regular Users</p>
      </div>
    </div>

    <div class="tab-list" role="tablist" aria-hidden="false">
      <button class="tab-button active">Convert & Download</button>
      <button class="tab-button">Compare</button>
      <button class="tab-button">Ask RET AI</button>
    </div>

    <section class="enterprise-card">
      <h3 class="card-title">Utility Workflow</h3>
      <div style="display:grid; grid-template-columns: 1fr 360px; gap:var(--space-lg);">
        <div>
          <FileUploader @uploaded="onUploaded" />
          <div style="margin-top: var(--space-md)">
            <h4 class="card-title">Scan Summary</h4>
            <p class="card-description">Files scanned: {{ summary.count }} — Size: {{ summary.size }}</p>
            <div class="data-table-wrapper" style="margin-top:var(--space-md)">
              <table class="data-table" role="table">
                <thead><tr><th>Filename</th><th>Type</th><th>Rows</th><th>Actions</th></tr></thead>
                <tbody>
                  <tr v-for="row in tableData" :key="row.id">
                    <td>{{ row.name }}</td>
                    <td>{{ row.type }}</td>
                    <td>{{ row.rows || '-' }}</td>
                    <td>
                      <button class="btn btn-sm btn-primary" @click="download(row)">Download</button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <div>
          <h4 class="card-title">Group Preview</h4>
          <div class="enterprise-card">
            <p class="card-description">Preview of the extracted XML groups and datasets.</p>
            <!-- placeholder preview -->
            <pre style="max-height:240px; overflow:auto"> <!-- fill in later --> </pre>
            <div style="margin-top: var(--space-md); display:flex; gap:8px;">
              <button class="btn btn-primary">Bulk Convert</button>
              <button class="btn btn-secondary">Clear</button>
            </div>
          </div>
        </div>
      </div>
    </section>

    <section class="enterprise-card" style="margin-top: var(--space-lg)">
      <h3 class="card-title">Ask RET AI</h3>
      <AIChatInterface />
    </section>
  </div>
</template>

<script setup>
import FileUploader from '@/components/workspace/FileUploader.vue'
import AIChatInterface from '@/components/workspace/AIChatInterface.vue'
import { ref } from 'vue'

const summary = ref({ count: 0, size: '0 KB' })
const tableData = ref([])

function onUploaded(files) {
  summary.value.count = files.length
  summary.value.size = files.reduce((acc, f) => acc + (f.size || 0), 0)
  tableData.value = files.map((f, i) => ({ id: i, name: f.name, type: f.type || 'zip', rows: null }))
}

function download(row) {
  // placeholder: request backend to provide converted blob
  alert(`Requesting download for ${row.name}`)
}
</script>
