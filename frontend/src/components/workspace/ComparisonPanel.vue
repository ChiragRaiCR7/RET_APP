<template>
  <div class="comparison-panel">
    <div class="card-header">
      <div class="card-title-group">
        <h3 class="card-title">📊 Compare Two Inputs (ZIP/XML/CSV → CSV diff)</h3>
        <p class="card-description">Compare results are best-effort for keyless CSVs. Drilldown shows only changed rows/columns side-by-side.</p>
      </div>
    </div>

    <!-- Comparison Options -->
    <div class="comparison-options">
      <label class="toggle-control">
        <input type="checkbox" v-model="options.ignoreCase" class="toggle-input" />
        <span class="toggle-text">Ignore case</span>
      </label>
      <label class="toggle-control">
        <input type="checkbox" v-model="options.trimWhitespace" class="toggle-input" />
        <span class="toggle-text">Trim whitespace</span>
      </label>
      <label class="toggle-control">
        <input type="checkbox" v-model="options.similarityPairing" class="toggle-input" />
        <span class="toggle-text">Similarity pairing (enhanced matching)</span>
      </label>
    </div>

    <!-- Side-by-Side Upload -->
    <div class="sides-grid">
      <!-- Side A -->
      <div class="side-section">
        <h4 class="side-title">Side A</h4>
        <div class="form-group">
          <label class="form-label">Input type A</label>
          <div class="radio-group">
            <label class="radio-label">
              <input type="radio" v-model="sideA.inputType" value="zip" />
              <span>ZIP</span>
            </label>
            <label class="radio-label">
              <input type="radio" v-model="sideA.inputType" value="xml" />
              <span>XML</span>
            </label>
            <label class="radio-label">
              <input type="radio" v-model="sideA.inputType" value="csv" />
              <span>CSV</span>
            </label>
          </div>
        </div>

        <div class="upload-zone-sm">
          <label class="form-label">Upload {{ sideA.inputType.toUpperCase() }} A</label>
          <div 
            class="file-drop-zone"
            :class="{ dragging: sideA.dragging, 'has-file': sideA.file }"
            @dragover.prevent="sideA.dragging = true"
            @dragleave.prevent="sideA.dragging = false"
            @drop.prevent="onDropA"
            @click="$refs.inputA.click()"
          >
            <div v-if="!sideA.file">
              <div class="drop-icon">📁</div>
              <p>Drag and drop file here</p>
              <p class="drop-hint">Limit 200MB per file • {{ sideA.inputType.toUpperCase() }}</p>
            </div>
            <div v-else class="file-info">
              <span class="file-icon">📄</span>
              <span class="file-name">{{ sideA.file.name }}</span>
              <span class="file-size">{{ formatSize(sideA.file.size) }}</span>
              <button class="btn-remove" @click.stop="removeFileA">×</button>
            </div>
            <button class="btn btn-sm btn-secondary browse-btn" @click.stop="$refs.inputA.click()">
              Browse files
            </button>
          </div>
          <input 
            ref="inputA" 
            type="file" 
            @change="onFileA"
            :accept="getAcceptTypes(sideA.inputType)"
            style="display: none"
          />
        </div>
      </div>

      <!-- Side B -->
      <div class="side-section">
        <h4 class="side-title">Side B</h4>
        <div class="form-group">
          <label class="form-label">Input type B</label>
          <div class="radio-group">
            <label class="radio-label">
              <input type="radio" v-model="sideB.inputType" value="zip" />
              <span>ZIP</span>
            </label>
            <label class="radio-label">
              <input type="radio" v-model="sideB.inputType" value="xml" />
              <span>XML</span>
            </label>
            <label class="radio-label">
              <input type="radio" v-model="sideB.inputType" value="csv" />
              <span>CSV</span>
            </label>
          </div>
        </div>

        <div class="upload-zone-sm">
          <label class="form-label">Upload {{ sideB.inputType.toUpperCase() }} B</label>
          <div 
            class="file-drop-zone"
            :class="{ dragging: sideB.dragging, 'has-file': sideB.file }"
            @dragover.prevent="sideB.dragging = true"
            @dragleave.prevent="sideB.dragging = false"
            @drop.prevent="onDropB"
            @click="$refs.inputB.click()"
          >
            <div v-if="!sideB.file">
              <div class="drop-icon">📁</div>
              <p>Drag and drop file here</p>
              <p class="drop-hint">Limit 200MB per file • {{ sideB.inputType.toUpperCase() }}</p>
            </div>
            <div v-else class="file-info">
              <span class="file-icon">📄</span>
              <span class="file-name">{{ sideB.file.name }}</span>
              <span class="file-size">{{ formatSize(sideB.file.size) }}</span>
              <button class="btn-remove" @click.stop="removeFileB">×</button>
            </div>
            <button class="btn btn-sm btn-secondary browse-btn" @click.stop="$refs.inputB.click()">
              Browse files
            </button>
          </div>
          <input 
            ref="inputB" 
            type="file" 
            @change="onFileB"
            :accept="getAcceptTypes(sideB.inputType)"
            style="display: none"
          />
        </div>
      </div>
    </div>

    <!-- Compare Button -->
    <div class="compare-action">
      <button 
        class="btn btn-primary btn-lg compare-btn"
        @click="runComparison"
        :disabled="!canCompare || comparing"
      >
        <span v-if="comparing" class="spinner"></span>
        {{ comparing ? 'Comparing...' : '🔍 Compare Now' }}
      </button>
      <p class="compare-hint">Upload Side A and Side B, then click Compare Now.</p>
    </div>

    <!-- Progress Indicator -->
    <div v-if="comparing" class="progress-section">
      <div class="progress-steps">
        <div class="progress-step" :class="{ active: progressStep >= 1, done: progressStep > 1 }">
          Preparing Side A and B...
        </div>
        <div class="progress-step" :class="{ active: progressStep >= 2, done: progressStep > 2 }">
          Finalizing...
        </div>
        <div class="progress-step" :class="{ active: progressStep >= 3 }">
          Compare complete.
        </div>
      </div>
      <div class="progress-bar">
        <div class="progress-fill" :style="{ width: progressPercent + '%' }"></div>
      </div>
    </div>

    <!-- Results Section -->
    <div v-if="results" class="results-section">
      <!-- Similarity Dashboard -->
      <div class="dashboard-card">
        <h4 class="section-title">📊 Similarity Dashboard (Group+Filename matching)</h4>
        <div class="dashboard-metrics">
          <div class="metric-card large">
            <div class="metric-label">Overall (proxy)</div>
            <div class="metric-value">{{ results.similarity }}%</div>
          </div>
          <div class="metric-card">
            <div class="metric-icon">✅</div>
            <div class="metric-label">Same</div>
            <div class="metric-value">{{ results.same }}</div>
          </div>
          <div class="metric-card">
            <div class="metric-icon">✏️</div>
            <div class="metric-label">Modified</div>
            <div class="metric-value">{{ results.modified }}</div>
          </div>
          <div class="metric-card">
            <div class="metric-icon">➕/🗑️</div>
            <div class="metric-label">Added / Removed</div>
            <div class="metric-value">{{ results.added }}/{{ results.removed }}</div>
          </div>
        </div>
      </div>

      <!-- Collapsible Sections -->
      <details class="collapsible-section">
        <summary>📋 Input details</summary>
        <div class="section-content">
          <p><strong>Side A:</strong> {{ sideA.file?.name }} ({{ formatSize(sideA.file?.size) }})</p>
          <p><strong>Side B:</strong> {{ sideB.file?.name }} ({{ formatSize(sideB.file?.size) }})</p>
        </div>
      </details>

      <details class="collapsible-section folder-tree-section">
        <summary>📁 Folder structure (tree view)</summary>
        <div class="section-content">
          <p v-if="!results.folderChanges?.length && !results.changes?.length" class="no-changes">No folder structure changes detected.</p>
          <div v-else class="folder-tree-container">
            <div class="tree-legend">
              <span class="legend-item"><span class="tree-icon folder">📁</span> Folder</span>
              <span class="legend-item"><span class="tree-icon file-same">📄</span> Same</span>
              <span class="legend-item"><span class="tree-icon file-modified">📝</span> Modified</span>
              <span class="legend-item"><span class="tree-icon file-added">➕</span> Added</span>
              <span class="legend-item"><span class="tree-icon file-removed">🗑️</span> Removed</span>
            </div>
            <div class="tree-view">
              <div v-for="node in buildFolderTree" :key="node.path" :class="['tree-node', `depth-${node.depth}`]" :style="{ paddingLeft: (node.depth * 20) + 'px' }">
                <span v-if="node.isFolder" class="tree-icon folder">📁</span>
                <span v-else-if="node.status === 'SAME'" class="tree-icon file-same">📄</span>
                <span v-else-if="node.status === 'MODIFIED'" class="tree-icon file-modified">📝</span>
                <span v-else-if="node.status === 'ADDED'" class="tree-icon file-added">➕</span>
                <span v-else-if="node.status === 'REMOVED'" class="tree-icon file-removed">🗑️</span>
                <span v-else class="tree-icon">📄</span>
                <span class="tree-name" :class="{ 'folder-name': node.isFolder, ['status-' + (node.status || '').toLowerCase()]: !node.isFolder }">
                  {{ node.name }}
                </span>
                <span v-if="node.status && !node.isFolder" class="tree-status-badge" :class="'badge-' + node.status.toLowerCase()">
                  {{ node.status }}
                </span>
              </div>
            </div>
          </div>
        </div>
      </details>

      <details class="collapsible-section">
        <summary>📈 Group count deltas (OK only)</summary>
        <div class="section-content">
          <p v-if="!results.groupDeltas?.length">No group count changes.</p>
        </div>
      </details>

      <!-- Change List Table -->
      <div class="change-list-section">
        <h4 class="section-title">📋 Change list</h4>
        <div class="filter-bar">
          <button class="filter-btn" :class="{ active: statusFilter === 'MODIFIED' }" @click="statusFilter = statusFilter === 'MODIFIED' ? '' : 'MODIFIED'">Only MODIFIED</button>
          <button class="filter-btn warning" :class="{ active: statusFilter === 'ADDED_REMOVED' }" @click="statusFilter = statusFilter === 'ADDED_REMOVED' ? '' : 'ADDED_REMOVED'">Only ADDED/REMOVED</button>
          <button class="filter-btn" :class="{ active: statusFilter === '' }" @click="statusFilter = ''">Everything</button>
        </div>

        <div class="status-filters">
          <label class="form-label">Filter status</label>
          <div class="filter-badges">
            <span v-for="status in availableStatuses" :key="status" class="filter-badge" :class="{ active: selectedStatuses.includes(status) }" @click="toggleStatus(status)">{{ status }} ×</span>
          </div>
        </div>

        <div class="search-filter">
          <label class="form-label">Search Group/Filename</label>
          <input v-model="searchQuery" type="text" class="form-input" placeholder="Type to filter..." />
        </div>

        <p class="similarity-note">Cosine similarity is informational. Any SHA mismatch is MODIFIED.</p>

        <div class="data-table-wrapper">
          <table class="data-table">
            <thead>
              <tr>
                <th></th>
                <th>Status</th>
                <th>Group</th>
                <th>Filename</th>
                <th>Similarity%</th>
                <th>Rows_A</th>
                <th>Rows_B</th>
                <th>Cols_A</th>
                <th>Cols_B</th>
                <th>Message</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(change, idx) in filteredChanges" :key="idx">
                <td>{{ idx }}</td>
                <td><span class="status-badge" :class="getStatusBadgeClass(change.status)">{{ change.status }}</span></td>
                <td>{{ change.group }}</td>
                <td>{{ change.filename }}</td>
                <td>{{ change.similarity }}</td>
                <td>{{ change.rows_a }}</td>
                <td>{{ change.rows_b }}</td>
                <td>{{ change.cols_a }}</td>
                <td>{{ change.cols_b }}</td>
                <td>
                  <span v-if="change.status === 'SAME'" class="message-badge success">✅ Content identical (SHA256 match).</span>
                  <span v-else-if="change.status === 'MODIFIED'" class="message-badge warning">❌ Content differs (SHA mismatch).</span>
                  <span v-else>{{ change.message }}</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Drilldown Section -->
      <div class="drilldown-section">
        <h4 class="section-title">🔍 Drilldown: Side-by-side deltas (only changes)</h4>
        <p class="drilldown-hint">Select a file to see row-level differences. Click on <span class="dot-example red">●</span> or <span class="dot-example green">●</span> dots to view details.</p>
        
        <div class="form-group">
          <label class="form-label">Pick a file (Group+Filename)</label>
          <select v-model="drilldownFile" class="form-select" @change="loadDrilldown">
            <option value="">Select a file...</option>
            <option v-for="change in results.changes.filter(c => ['MODIFIED','ADDED','REMOVED'].includes(c.status))" :key="change.filename + change.group" :value="change.filename + '||' + (change.group || '')">
              {{ change.group }} | {{ change.filename }} ({{ change.status }})
            </option>
          </select>
        </div>

        <div v-if="drilldownFile && drilldownData" class="drilldown-content">
          <div class="drilldown-stats-bar">
            <div class="stat-item">
              <span class="stat-label">Side A Rows</span>
              <span class="stat-value">{{ drilldownData.sizeA }}</span>
            </div>
            <div class="stat-item">
              <span class="stat-label">Side B Rows</span>
              <span class="stat-value">{{ drilldownData.sizeB }}</span>
            </div>
            <div class="stat-item modified">
              <span class="stat-label">Modified</span>
              <span class="stat-value">{{ drilldownData.modified }}</span>
            </div>
            <div class="stat-item added">
              <span class="stat-label">Added</span>
              <span class="stat-value">{{ drilldownData.added }}</span>
            </div>
            <div class="stat-item removed">
              <span class="stat-label">Removed</span>
              <span class="stat-value">{{ drilldownData.removed }}</span>
            </div>
          </div>
          
          <div class="drilldown-legend">
            <span class="legend-item"><span class="dot red">●</span> Removed/Changed in A</span>
            <span class="legend-item"><span class="dot green">●</span> Added/Changed in B</span>
            <span class="legend-item"><span class="dot gray">○</span> Unchanged</span>
          </div>
          
          <p v-if="drilldownData.truncated" class="truncation-warning">⚠️ Results truncated (too many changes to display)</p>

          <div class="delta-tables">
            <div class="delta-side side-a">
              <h5>🅰️ Side A — Original</h5>
              <div class="data-table-wrapper">
                <table class="data-table delta-table">
                  <thead>
                    <tr>
                      <th class="col-narrow">Kind</th>
                      <th class="col-narrow">Row#</th>
                      <th v-for="col in drilldownData.columns" :key="col" :class="{ 'col-changed': isColumnChanged(col) }">
                        <span v-if="isColumnChanged(col)" class="col-indicator">●</span>
                        {{ col }}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="(row, idx) in drilldownData.deltaA" :key="idx" :class="getRowClass(row._kind_)">
                      <td class="col-narrow"><span :class="'kind-badge kind-' + (row._kind_ || '').toLowerCase()">{{ row._kind_ }}</span></td>
                      <td class="col-narrow">{{ row._rowA_ }}</td>
                      <td v-for="col in drilldownData.columns" :key="col" :class="getCellClass(row, col, 'A')" @click="onCellClick(row, col, 'A')">
                        <span v-if="cellHasChange(row, col)" class="cell-dot" :class="getCellDotClass(row, col, 'A')" title="Click to view change details">●</span>
                        <span class="cell-value" :class="{ 'cell-muted': !cellHasChange(row, col) }">{{ formatCellValue(row[col]) }}</span>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            <div class="delta-side side-b">
              <h5>🅱️ Side B — Modified</h5>
              <div class="data-table-wrapper">
                <table class="data-table delta-table">
                  <thead>
                    <tr>
                      <th class="col-narrow">Kind</th>
                      <th class="col-narrow">Row#</th>
                      <th v-for="col in drilldownData.columns" :key="col" :class="{ 'col-changed': isColumnChanged(col) }">
                        <span v-if="isColumnChanged(col)" class="col-indicator">●</span>
                        {{ col }}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="(row, idx) in drilldownData.deltaB" :key="idx" :class="getRowClass(row._kind_)">
                      <td class="col-narrow"><span :class="'kind-badge kind-' + (row._kind_ || '').toLowerCase()">{{ row._kind_ }}</span></td>
                      <td class="col-narrow">{{ row._rowB_ }}</td>
                      <td v-for="col in drilldownData.columns" :key="col" :class="getCellClass(row, col, 'B')" @click="onCellClick(row, col, 'B')">
                        <span v-if="cellHasChange(row, col)" class="cell-dot" :class="getCellDotClass(row, col, 'B')" title="Click to view change details">●</span>
                        <span class="cell-value" :class="{ 'cell-muted': !cellHasChange(row, col) }">{{ formatCellValue(row[col]) }}</span>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      </div>
      
      <!-- Cell Detail Modal -->
      <div v-if="showCellModal" class="modal-overlay" @click.self="showCellModal = false">
        <div class="cell-detail-modal full-drilldown-modal">
          <div class="modal-header">
            <div>
              <h4>Full Drilldown View</h4>
              <p class="modal-subtitle">Side-by-side tables with the selected change highlighted.</p>
            </div>
            <button class="modal-close" @click="showCellModal = false">×</button>
          </div>
          <div class="modal-body full-drilldown-body">
            <div class="cell-meta">
              <p><strong>Column:</strong> {{ cellModalData.column }}</p>
              <p><strong>Row A:</strong> {{ cellModalData.rowA }} | <strong>Row B:</strong> {{ cellModalData.rowB }}</p>
              <p><strong>Change Type:</strong> <span :class="'kind-badge kind-' + (cellModalData.kind || '').toLowerCase()">{{ cellModalData.kind }}</span></p>
              <div class="cell-comparison compact">
                <div class="cell-side old">
                  <h5>🅰️ Side A (Original)</h5>
                  <div class="cell-content">{{ cellModalData.valueA || '(empty)' }}</div>
                </div>
                <div class="cell-side new">
                  <h5>🅱️ Side B (Modified)</h5>
                  <div class="cell-content">{{ cellModalData.valueB || '(empty)' }}</div>
                </div>
              </div>
            </div>

            <div class="delta-tables full-view">
              <div class="delta-side side-a">
                <h5>🅰️ Side A — Original</h5>
                <div class="data-table-wrapper tall-scroll">
                  <table class="data-table delta-table">
                    <thead>
                      <tr>
                        <th class="col-narrow">Kind</th>
                        <th class="col-narrow">Row#</th>
                        <th v-for="col in drilldownData.columns" :key="col" :class="{ 'col-changed': isColumnChanged(col) }">
                          <span v-if="isColumnChanged(col)" class="col-indicator">●</span>
                          {{ col }}
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="(row, idx) in drilldownData.deltaA" :key="idx" :class="getRowClass(row._kind_)">
                        <td class="col-narrow"><span :class="'kind-badge kind-' + (row._kind_ || '').toLowerCase()">{{ row._kind_ }}</span></td>
                        <td class="col-narrow">{{ row._rowA_ }}</td>
                        <td v-for="col in drilldownData.columns" :key="col" :class="getCellClass(row, col, 'A')">
                          <span v-if="cellHasChange(row, col)" class="cell-dot" :class="getCellDotClass(row, col, 'A')">●</span>
                          <span class="cell-value" :class="{ 'cell-muted': !cellHasChange(row, col) }">{{ formatCellValue(row[col]) }}</span>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>

              <div class="delta-side side-b">
                <h5>🅱️ Side B — Modified</h5>
                <div class="data-table-wrapper tall-scroll">
                  <table class="data-table delta-table">
                    <thead>
                      <tr>
                        <th class="col-narrow">Kind</th>
                        <th class="col-narrow">Row#</th>
                        <th v-for="col in drilldownData.columns" :key="col" :class="{ 'col-changed': isColumnChanged(col) }">
                          <span v-if="isColumnChanged(col)" class="col-indicator">●</span>
                          {{ col }}
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="(row, idx) in drilldownData.deltaB" :key="idx" :class="getRowClass(row._kind_)">
                        <td class="col-narrow"><span :class="'kind-badge kind-' + (row._kind_ || '').toLowerCase()">{{ row._kind_ }}</span></td>
                        <td class="col-narrow">{{ row._rowB_ }}</td>
                        <td v-for="col in drilldownData.columns" :key="col" :class="getCellClass(row, col, 'B')">
                          <span v-if="cellHasChange(row, col)" class="cell-dot" :class="getCellDotClass(row, col, 'B')">●</span>
                          <span class="cell-value" :class="{ 'cell-muted': !cellHasChange(row, col) }">{{ formatCellValue(row[col]) }}</span>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import api from '@/utils/api'
import { useToastStore } from '@/stores/toastStore'

const toast = useToastStore()
const emit = defineEmits(['comparison-complete'])

const options = reactive({ ignoreCase: false, trimWhitespace: true, similarityPairing: true })
const sideA = reactive({ inputType: 'zip', file: null, dragging: false })
const sideB = reactive({ inputType: 'zip', file: null, dragging: false })
const comparing = ref(false)
const progressStep = ref(0)
const progressPercent = ref(0)
const results = ref(null)
const statusFilter = ref('')
const selectedStatuses = ref(['MODIFIED', 'SAME'])
const searchQuery = ref('')
const availableStatuses = ['MODIFIED', 'SAME', 'ADDED', 'REMOVED']
const drilldownFile = ref('')
const drilldownData = ref(null)
const showCellModal = ref(false)
const cellModalData = ref({
  column: '',
  valueA: '',
  valueB: '',
  rowA: '',
  rowB: '',
  kind: ''
})
const changedColumns = ref(new Set())

const canCompare = computed(() => sideA.file && sideB.file)

const filteredChanges = computed(() => {
  if (!results.value?.changes) return []
  let changes = [...results.value.changes]
  if (statusFilter.value === 'MODIFIED') changes = changes.filter(c => c.status === 'MODIFIED')
  else if (statusFilter.value === 'ADDED_REMOVED') changes = changes.filter(c => c.status === 'ADDED' || c.status === 'REMOVED')
  if (selectedStatuses.value.length > 0) changes = changes.filter(c => selectedStatuses.value.includes(c.status))
  if (searchQuery.value) {
    const q = searchQuery.value.toLowerCase()
    changes = changes.filter(c => c.group?.toLowerCase().includes(q) || c.filename?.toLowerCase().includes(q))
  }
  return changes
})

// Build tree structure from changes
const buildFolderTree = computed(() => {
  if (!results.value?.changes) return []
  
  const folderMap = new Map()
  const nodes = []
  
  // Group files by their group/folder
  results.value.changes.forEach(change => {
    const folder = change.group || 'root'
    if (!folderMap.has(folder)) {
      folderMap.set(folder, [])
    }
    folderMap.get(folder).push({
      name: change.filename,
      status: change.status,
      isFolder: false
    })
  })
  
  // Build tree nodes
  const sortedFolders = Array.from(folderMap.keys()).sort()
  sortedFolders.forEach(folder => {
    // Add folder node
    nodes.push({
      path: folder,
      name: folder,
      isFolder: true,
      depth: 0,
      status: null
    })
    
    // Add file nodes under folder
    const files = folderMap.get(folder).sort((a, b) => a.name.localeCompare(b.name))
    files.forEach(file => {
      nodes.push({
        path: folder + '/' + file.name,
        name: file.name,
        isFolder: false,
        depth: 1,
        status: file.status
      })
    })
  })
  
  return nodes
})

function formatSize(bytes) {
  if (!bytes) return '0 KB'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

function getAcceptTypes(type) {
  const map = { zip: '.zip,application/zip', xml: '.xml,text/xml,application/xml', csv: '.csv,text/csv' }
  return map[type] || '*/*'
}

function onDropA(e) { sideA.dragging = false; if (e.dataTransfer.files.length) sideA.file = e.dataTransfer.files[0] }
function onDropB(e) { sideB.dragging = false; if (e.dataTransfer.files.length) sideB.file = e.dataTransfer.files[0] }
function onFileA(e) { if (e.target.files.length) sideA.file = e.target.files[0] }
function onFileB(e) { if (e.target.files.length) sideB.file = e.target.files[0] }
function removeFileA() { sideA.file = null }
function removeFileB() { sideB.file = null }

async function runComparison() {
  if (!canCompare.value) return
  comparing.value = true
  progressStep.value = 1
  progressPercent.value = 20
  results.value = null
  drilldownFile.value = ''
  drilldownData.value = null
  
  try {
    const formData = new FormData()
    formData.append('sideA', sideA.file)
    formData.append('sideB', sideB.file)
    progressStep.value = 2
    progressPercent.value = 60
    
    const res = await api.post('/comparison/run', formData, { headers: { 'Content-Type': 'multipart/form-data' } })
    progressStep.value = 3
    progressPercent.value = 100
    
    results.value = {
      similarity: res.data.similarity || 0,
      same: res.data.same || 0,
      modified: res.data.modified || 0,
      added: res.data.added || 0,
      removed: res.data.removed || 0,
      changes: res.data.changes || [],
      folderChanges: res.data.folder_changes || [],
      groupDeltas: res.data.group_deltas || []
    }
    emit('comparison-complete', results.value)
    toast.success('Comparison complete!')
  } catch (e) {
    toast.error('Comparison failed: ' + (e.response?.data?.detail || e.message))
  } finally {
    comparing.value = false
  }
}

function toggleStatus(status) {
  const idx = selectedStatuses.value.indexOf(status)
  if (idx >= 0) selectedStatuses.value.splice(idx, 1)
  else selectedStatuses.value.push(status)
}

function getStatusBadgeClass(status) {
  const map = { SAME: 'badge-success', MODIFIED: 'badge-warning', ADDED: 'badge-info', REMOVED: 'badge-error' }
  return map[status] || ''
}

function getRowClass(kind) {
  const map = { MODIFIED: 'row-modified', ADDED: 'row-added', REMOVED: 'row-removed' }
  return map[kind] || ''
}

function getCellClass(row, col, side) {
  const changedCols = row._changed_cols_ || []
  const colIndex = drilldownData.value?.columns?.indexOf(col)
  const isChanged = row._kind_ === 'ADDED' || row._kind_ === 'REMOVED'
    ? true
    : (changedCols.includes(colIndex) || changedCols.includes(col))
  if (isChanged) return side === 'A' ? 'cell-old' : 'cell-new'
  return ''
}

function getCellIndicatorClass(row, col) {
  const changedCols = row._changed_cols_ || []
  const colIndex = drilldownData.value?.columns?.indexOf(col)
  const isChanged = row._kind_ === 'ADDED' || row._kind_ === 'REMOVED'
    ? true
    : (changedCols.includes(colIndex) || changedCols.includes(col))
  return isChanged ? 'indicator-changed' : 'indicator-unchanged'
}

function cellHasChange(row, col) {
  const changedCols = row._changed_cols_ || []
  const colIndex = drilldownData.value?.columns?.indexOf(col)
  if (row._kind_ === 'ADDED' || row._kind_ === 'REMOVED') return true
  return changedCols.includes(colIndex) || changedCols.includes(col)
}

function getCellDotClass(row, col, side) {
  if (!cellHasChange(row, col)) return 'dot-unchanged'
  if (row._kind_ === 'REMOVED') return 'dot-red'
  if (row._kind_ === 'ADDED') return 'dot-green'
  return side === 'A' ? 'dot-red' : 'dot-green'
}

function onCellClick(row, col, side) {
  if (!cellHasChange(row, col)) return
  showCellDetail(row, col, side)
}

function isColumnChanged(col) {
  return changedColumns.value.has(col)
}

function formatCellValue(value, maxLen = 40) {
  if (value === null || value === undefined) return ''
  const str = String(value)
  return str.length > maxLen ? str.substring(0, maxLen) + '…' : str
}

function showCellDetail(row, col, side) {
  // Find matching row in the other side
  const deltaA = drilldownData.value?.deltaA || []
  const deltaB = drilldownData.value?.deltaB || []
  
  let rowA = null, rowB = null
  
  if (side === 'A') {
    rowA = row
    // Find matching row in B by row index
    rowB = deltaB.find(r => r._rowB_ === row._rowB_ || r._rowA_ === row._rowA_)
  } else {
    rowB = row
    rowA = deltaA.find(r => r._rowA_ === row._rowA_ || r._rowB_ === row._rowB_)
  }
  
  cellModalData.value = {
    column: col,
    valueA: rowA ? rowA[col] : '(not found)',
    valueB: rowB ? rowB[col] : '(not found)',
    rowA: row._rowA_ || '-',
    rowB: row._rowB_ || '-',
    kind: row._kind_ || 'MODIFIED'
  }
  
  showCellModal.value = true
}

async function loadDrilldown() {
  if (!drilldownFile.value || !results.value) return

  const [filename, group] = drilldownFile.value.split('||')
  const change = results.value.changes.find(c => c.filename === filename && (c.group || '') === (group || ''))
  if (!change) {
    toast.warning('Cannot load drilldown - file not found')
    return
  }

  const hasA = !!change.csv_path_a
  const hasB = !!change.csv_path_b
  if (!hasA && !hasB) {
    toast.warning('Cannot load drilldown - file paths not available')
    return
  }

  try {
    toast.info('Loading drilldown comparison...')

    const params = new URLSearchParams({
      ignore_case: options.ignoreCase.toString(),
      trim_whitespace: options.trimWhitespace.toString(),
      similarity_pairing: options.similarityPairing.toString(),
      sim_threshold: '0.65'
    })

    if (hasA) params.append('csv_path_a', change.csv_path_a)
    if (hasB) params.append('csv_path_b', change.csv_path_b)

    const res = await api.post(`/comparison/drilldown?${params.toString()}`)

    if (res.data.error) {
      toast.error('Drilldown failed: ' + res.data.error)
      return
    }

    const deltaA = res.data.deltaA || {}
    const deltaB = res.data.deltaB || {}
    const stats = res.data.stats || {}
    const header = res.data.header || []

    drilldownData.value = {
      sizeA: res.data.row_count_A || 0,
      sizeB: res.data.row_count_B || 0,
      modified: stats.modified || 0,
      added: stats.added || 0,
      removed: stats.removed || 0,
      columns: header,
      deltaA: deltaA.rows || [],
      deltaB: deltaB.rows || [],
      truncated: res.data.truncated || false,
      header
    }
    
    // Build set of changed columns
    const changedCols = new Set()
    const allRows = [...(deltaA.rows || []), ...(deltaB.rows || [])]
    allRows.forEach(row => {
      if (row._changed_cols_) {
        row._changed_cols_.forEach(c => {
          if (typeof c === 'number' && header[c]) {
            changedCols.add(header[c])
          } else {
            changedCols.add(c)
          }
        })
      }
      // For ADDED/REMOVED, all columns are changed
      if (row._kind_ === 'ADDED' || row._kind_ === 'REMOVED') {
        header.forEach(h => changedCols.add(h))
      }
    })
    changedColumns.value = changedCols

    toast.success('Drilldown loaded!')
  } catch (e) {
    toast.error('Failed to load drilldown: ' + (e.response?.data?.detail || e.message))
    drilldownData.value = null
  }
}
</script>

<style scoped>
.comparison-panel { padding: 0; }
.comparison-options { display: flex; flex-wrap: wrap; gap: var(--space-lg); align-items: center; padding: var(--space-md); background: var(--surface-base); border-radius: var(--radius-md); margin-bottom: var(--space-lg); }
.toggle-control { display: flex; align-items: center; gap: var(--space-sm); cursor: pointer; }
.toggle-input { width: 40px; height: 20px; appearance: none; background: var(--border-medium); border-radius: 10px; position: relative; cursor: pointer; transition: background 0.2s; }
.toggle-input:checked { background: var(--brand-primary); }
.toggle-input::before { content: ''; position: absolute; width: 16px; height: 16px; border-radius: 50%; background: white; top: 2px; left: 2px; transition: transform 0.2s; }
.toggle-input:checked::before { transform: translateX(20px); }
.threshold-control { display: flex; align-items: center; gap: var(--space-sm); }
.threshold-slider { width: 100px; accent-color: var(--brand-primary); }
.threshold-value { font-weight: 600; color: var(--brand-primary); }
.sides-grid { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-lg); margin-bottom: var(--space-lg); }
.side-section { background: var(--surface-base); border-radius: var(--radius-md); padding: var(--space-lg); }
.side-title { font-size: 1.1rem; font-weight: 700; margin-bottom: var(--space-md); }
.radio-group { display: flex; gap: var(--space-lg); }
.radio-label { display: flex; align-items: center; gap: var(--space-xs); cursor: pointer; }
.file-drop-zone { border: 2px dashed var(--border-medium); border-radius: var(--radius-md); padding: var(--space-lg); text-align: center; cursor: pointer; transition: all 0.2s; min-height: 150px; display: flex; flex-direction: column; align-items: center; justify-content: center; }
.file-drop-zone:hover, .file-drop-zone.dragging { border-color: var(--brand-primary); background: var(--brand-subtle); }
.file-drop-zone.has-file { border-style: solid; border-color: var(--success); }
.drop-icon { font-size: 2rem; margin-bottom: var(--space-sm); }
.drop-hint { font-size: 0.85rem; color: var(--text-tertiary); }
.file-info { display: flex; align-items: center; gap: var(--space-sm); }
.file-icon { font-size: 1.5rem; }
.file-name { font-weight: 600; }
.file-size { color: var(--text-tertiary); font-size: 0.85rem; }
.btn-remove { background: var(--error); color: white; border: none; border-radius: 50%; width: 24px; height: 24px; cursor: pointer; font-size: 1rem; line-height: 1; }
.browse-btn { margin-top: var(--space-sm); }
.compare-action { text-align: center; margin-bottom: var(--space-xl); }
.compare-btn { min-width: 300px; }
.compare-hint { color: var(--text-tertiary); margin-top: var(--space-sm); }
.progress-section { margin-bottom: var(--space-xl); }
.progress-steps { display: flex; flex-direction: column; gap: var(--space-xs); margin-bottom: var(--space-md); }
.progress-step { padding: var(--space-sm); border-radius: var(--radius-sm); background: var(--surface-base); color: var(--text-tertiary); }
.progress-step.active { background: var(--brand-subtle); color: var(--text-body); }
.progress-step.done { color: var(--success); }
.progress-bar { height: 8px; background: var(--surface-base); border-radius: 4px; overflow: hidden; }
.progress-fill { height: 100%; background: linear-gradient(90deg, var(--brand-primary), var(--brand-light)); transition: width 0.3s; }
.results-section { margin-top: var(--space-xl); }
.dashboard-card { background: var(--surface-base); border-radius: var(--radius-md); padding: var(--space-lg); margin-bottom: var(--space-lg); }
.section-title { font-size: 1rem; font-weight: 700; margin-bottom: var(--space-md); }
.dashboard-metrics { display: flex; gap: var(--space-lg); flex-wrap: wrap; }
.metric-card { background: var(--surface-elevated); border: 1px solid var(--border-light); border-radius: var(--radius-md); padding: var(--space-md); text-align: center; min-width: 100px; }
.metric-card.large { min-width: 150px; }
.metric-card .metric-icon { font-size: 1.5rem; }
.metric-card .metric-label { font-size: 0.85rem; color: var(--text-tertiary); }
.metric-card .metric-value { font-size: 1.5rem; font-weight: 700; color: var(--text-heading); }
.collapsible-section { background: var(--surface-base); border-radius: var(--radius-md); margin-bottom: var(--space-md); }
.collapsible-section summary { padding: var(--space-md); cursor: pointer; font-weight: 600; }
.collapsible-section .section-content { padding: 0 var(--space-md) var(--space-md); }
.change-list-section { background: var(--surface-base); border-radius: var(--radius-md); padding: var(--space-lg); margin-bottom: var(--space-lg); }
.filter-bar { display: flex; gap: var(--space-sm); margin-bottom: var(--space-md); }
.filter-btn { padding: 8px 16px; border-radius: var(--radius-full); border: 1px solid var(--border-medium); background: var(--surface-elevated); cursor: pointer; font-weight: 600; transition: all 0.2s; }
.filter-btn:hover { border-color: var(--brand-primary); }
.filter-btn.active { background: var(--brand-primary); color: #000; border-color: var(--brand-primary); }
.filter-btn.warning.active { background: var(--warning); }
.status-filters { margin-bottom: var(--space-md); }
.filter-badges { display: flex; flex-wrap: wrap; gap: var(--space-xs); margin-top: var(--space-xs); }
.filter-badge { display: inline-flex; align-items: center; gap: 4px; padding: 4px 12px; border-radius: var(--radius-full); background: var(--surface-active); font-size: 0.85rem; cursor: pointer; transition: all 0.2s; }
.filter-badge.active { background: var(--brand-primary); color: #000; }
.search-filter { margin-bottom: var(--space-md); }
.search-filter .form-input { max-width: 300px; }
.similarity-note { font-size: 0.85rem; color: var(--text-tertiary); font-style: italic; margin-bottom: var(--space-md); }
.message-badge { display: inline-flex; align-items: center; gap: 4px; font-size: 0.8rem; }
.message-badge.success { color: var(--success); }
.message-badge.warning { color: var(--warning); }
.drilldown-section { background: var(--surface-base); border-radius: var(--radius-md); padding: var(--space-lg); }
.drilldown-content { margin-top: var(--space-lg); }
.diff-complexity { font-size: 0.85rem; color: var(--text-tertiary); }
.delta-summary { font-weight: 600; margin: var(--space-md) 0; }
.delta-tables { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-lg); }
.delta-side h5 { margin-bottom: var(--space-sm); }
.delta-table { font-size: 0.85rem; }
.row-modified { background: var(--warning-bg); }
.row-added { background: var(--success-bg); }
.row-removed { background: var(--error-bg); }
.cell-old { background: #fecaca; border-left: 3px solid #ef4444; }
.cell-new { background: #bbf7d0; border-left: 3px solid #22c55e; }
.cell-indicator { font-size: 0.85rem; margin-right: 6px; font-weight: bold; }
.indicator-changed { color: #ef4444; }
.indicator-unchanged { color: #9ca3af; opacity: 0.5; }
.kind-badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: 600; }
.kind-modified { background: #fef3c7; color: #92400e; }
.kind-added { background: #d1fae5; color: #065f46; }
.kind-removed { background: #fee2e2; color: #991b1b; }
.truncation-warning { color: var(--warning); font-weight: 600; background: var(--warning-bg); padding: var(--space-sm) var(--space-md); border-radius: var(--radius-sm); }

/* Folder Tree View Styles */
.folder-tree-section .section-content { max-height: 400px; overflow-y: auto; }
.folder-tree-container { margin-top: var(--space-md); }
.tree-legend { display: flex; flex-wrap: wrap; gap: var(--space-md); padding: var(--space-sm); background: var(--surface-elevated); border-radius: var(--radius-sm); margin-bottom: var(--space-md); font-size: 0.85rem; }
.legend-item { display: flex; align-items: center; gap: var(--space-xs); }
.tree-view { font-family: 'Menlo', 'Monaco', 'Consolas', monospace; font-size: 0.9rem; }
.tree-node { display: flex; align-items: center; gap: var(--space-sm); padding: 4px 8px; border-radius: var(--radius-sm); transition: background 0.1s; position: relative; }
.tree-node:hover { background: var(--surface-hover); }
.tree-node.depth-1::before { content: ''; position: absolute; left: 10px; top: -6px; bottom: -6px; width: 1px; background: var(--border-light); opacity: 0.6; }
.tree-node.depth-1::after { content: ''; position: absolute; left: 10px; top: 50%; width: 12px; height: 1px; background: var(--border-light); opacity: 0.6; }
.tree-icon { font-size: 1rem; flex-shrink: 0; }
.tree-name { flex: 1; }
.tree-name.folder-name { font-weight: 600; color: var(--text-heading); }
.tree-name.status-modified { color: #d97706; }
.tree-name.status-added { color: #059669; }
.tree-name.status-removed { color: #dc2626; text-decoration: line-through; }
.tree-name.status-same { color: var(--text-secondary); }
.tree-status-badge { padding: 2px 8px; border-radius: var(--radius-full); font-size: 0.7rem; font-weight: 600; }
.tree-status-badge.badge-modified { background: #fef3c7; color: #92400e; }
.tree-status-badge.badge-added { background: #d1fae5; color: #065f46; }
.tree-status-badge.badge-removed { background: #fee2e2; color: #991b1b; }
.tree-status-badge.badge-same { background: #e5e7eb; color: #6b7280; }
.no-changes { color: var(--text-tertiary); font-style: italic; }

.delta-modified { color: #f59e0b; font-weight: 600; }
.delta-added { color: #10b981; font-weight: 600; }
.delta-removed { color: #ef4444; font-weight: 600; }
.spinner { display: inline-block; width: 16px; height: 16px; border: 2px solid transparent; border-top-color: currentColor; border-radius: 50%; animation: spin 0.8s linear infinite; margin-right: 8px; }
@keyframes spin { to { transform: rotate(360deg); } }

/* Enhanced Drilldown Styles */
.drilldown-hint { font-size: 0.9rem; color: var(--text-secondary); margin-bottom: var(--space-md); }
.dot-example { font-weight: bold; margin: 0 2px; }
.dot-example.red { color: #ef4444; }
.dot-example.green { color: #22c55e; }

.drilldown-stats-bar { display: flex; flex-wrap: wrap; gap: var(--space-md); margin-bottom: var(--space-md); padding: var(--space-md); background: var(--surface-elevated); border-radius: var(--radius-md); }
.stat-item { display: flex; flex-direction: column; padding: var(--space-sm) var(--space-md); background: var(--surface-base); border-radius: var(--radius-sm); min-width: 80px; text-align: center; }
.stat-item.modified { border-left: 3px solid #f59e0b; }
.stat-item.added { border-left: 3px solid #22c55e; }
.stat-item.removed { border-left: 3px solid #ef4444; }
.stat-label { font-size: 0.75rem; color: var(--text-tertiary); }
.stat-value { font-size: 1.25rem; font-weight: 700; }

.drilldown-legend { display: flex; gap: var(--space-lg); margin-bottom: var(--space-md); padding: var(--space-sm); background: var(--surface-base); border-radius: var(--radius-sm); font-size: 0.85rem; }
.drilldown-legend .legend-item { display: flex; align-items: center; gap: var(--space-xs); }
.drilldown-legend .dot { font-size: 1.2rem; }
.drilldown-legend .dot.red { color: #ef4444; }
.drilldown-legend .dot.green { color: #22c55e; }
.drilldown-legend .dot.gray { color: #9ca3af; }

.delta-side { overflow: hidden; }
.delta-side.side-a h5 { color: #dc2626; }
.delta-side.side-b h5 { color: #16a34a; }

.col-narrow { width: 60px; max-width: 60px; }
.col-changed { background: linear-gradient(to bottom, #fef3c7, transparent); }
.col-indicator { color: #f59e0b; margin-right: 4px; }

.cell-dot { cursor: pointer; font-size: 1rem; margin-right: 6px; transition: transform 0.2s; }
.cell-dot:hover { transform: scale(1.3); }
.cell-dot.dot-red { color: #ef4444; }
.cell-dot.dot-green { color: #22c55e; }
.cell-dot.dot-unchanged { color: #d1d5db; font-size: 0.8rem; }
.cell-value { font-size: 0.85rem; }
.cell-muted { color: var(--text-tertiary); }

/* Cell Detail Modal */
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.6); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.cell-detail-modal { background: var(--surface-elevated); border-radius: var(--radius-lg); width: 90%; max-width: 700px; box-shadow: var(--shadow-heavy); overflow: hidden; }
.cell-detail-modal .modal-header { display: flex; justify-content: space-between; align-items: center; padding: var(--space-md) var(--space-lg); background: var(--surface-base); border-bottom: 1px solid var(--border-light); }
.cell-detail-modal .modal-header h4 { margin: 0; }
.cell-detail-modal .modal-close { background: transparent; border: none; font-size: 1.5rem; cursor: pointer; color: var(--text-secondary); }
.cell-detail-modal .modal-body { padding: var(--space-lg); }
.modal-subtitle { margin: 4px 0 0; color: var(--text-tertiary); font-size: 0.95rem; }

.full-drilldown-modal { max-width: 1400px; width: 96%; max-height: 90vh; display: flex; flex-direction: column; }
.full-drilldown-modal .modal-header { position: sticky; top: 0; z-index: 2; }
.full-drilldown-body { display: flex; flex-direction: column; gap: var(--space-md); max-height: calc(90vh - 110px); overflow: hidden; }
.delta-tables.full-view { flex: 1; display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-lg); }
.tall-scroll { max-height: 60vh; overflow: auto; }
.cell-comparison.compact { grid-template-columns: 1fr 1fr; gap: var(--space-md); margin-bottom: var(--space-md); }
.full-drilldown-modal .cell-meta { border: 1px solid var(--border-light); border-radius: var(--radius-md); padding: var(--space-md); background: var(--surface-base); }
.full-drilldown-modal .cell-content { max-height: 120px; }

.cell-comparison { display: grid; grid-template-columns: 1fr auto 1fr; gap: var(--space-md); align-items: stretch; margin-bottom: var(--space-lg); }
.cell-side { padding: var(--space-md); border-radius: var(--radius-md); }
.cell-side.old { background: #fef2f2; border: 2px solid #fecaca; }
.cell-side.new { background: #f0fdf4; border: 2px solid #bbf7d0; }
.cell-side h5 { margin: 0 0 var(--space-sm) 0; font-size: 0.9rem; }
.cell-side.old h5 { color: #dc2626; }
.cell-side.new h5 { color: #16a34a; }
.cell-content { font-family: monospace; font-size: 0.9rem; word-break: break-all; white-space: pre-wrap; max-height: 200px; overflow-y: auto; background: white; padding: var(--space-sm); border-radius: var(--radius-sm); }
.cell-arrow { display: flex; align-items: center; font-size: 1.5rem; color: var(--text-tertiary); }
.cell-meta { padding-top: var(--space-md); border-top: 1px solid var(--border-light); font-size: 0.9rem; }
.cell-meta p { margin: var(--space-xs) 0; }

@media (max-width: 768px) { .sides-grid { grid-template-columns: 1fr; } .delta-tables { grid-template-columns: 1fr; } .delta-tables.full-view { grid-template-columns: 1fr; } .cell-comparison { grid-template-columns: 1fr; } .cell-arrow { transform: rotate(90deg); justify-self: center; } }
</style>
