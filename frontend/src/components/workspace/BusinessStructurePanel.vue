<template>
  <div class="bs-panel">
    <!-- Not converted yet -->
    <div v-if="!converted" class="empty-state">
      <div class="empty-title">Conversion required</div>
      <div class="empty-text">
        Complete XML → CSV conversion to generate the Business Structure graph.
      </div>
    </div>

    <!-- Loading -->
    <div v-else-if="loadingStructure" class="empty-state">
      <div class="empty-title"><span class="spinner" aria-hidden="true"></span> Building structure…</div>
      <div class="empty-text">Reading converted CSVs to derive the 5-layer hierarchy.</div>
    </div>

    <!-- Error / missing data states -->
    <div v-else-if="!businessStructure || statusBad" class="empty-state">
      <div class="empty-title">{{ statusTitle }}</div>
      <div class="empty-text">{{ statusText }}</div>
      <div v-if="hasDiagnostics" class="diagnostics">
        <p v-for="d in businessStructure?.diagnostics" :key="d" class="diag-line">âš  {{ d }}</p>
      </div>
      <button class="btn btn-secondary" style="margin-top:12px" @click="$emit('refresh')">Retry</button>
    </div>

    <!-- Ready -->
    <div v-else>
      <!-- Top -->
      <div class="bs-top">
        <div class="bs-title">
          <h4 class="section-title">Organization Structure</h4>
          <p class="section-help">
            Business Group → Ledger → Legal Entity → Operating Unit → Inventory Organization
          </p>
        </div>
        <div class="bs-actions">
          <button class="btn btn-secondary" @click="$emit('refresh')" :disabled="loadingStructure">
            <span v-if="loadingStructure" class="spinner" aria-hidden="true"></span>
            {{ loadingStructure ? 'Loading…' : 'Refresh' }}
          </button>
        </div>
      </div>

      <!-- Summary -->
      <div class="summary">
        <div class="summary-item">
          <div class="summary-label">Status</div>
          <div class="summary-value status-ready">Ready</div>
        </div>
        <div class="summary-item">
          <div class="summary-label">Source Files</div>
          <div class="summary-value">{{ businessStructure.source_files?.join(', ') || '—' }}</div>
        </div>
        <div v-if="hasDiagnostics" class="summary-item full">
          <div class="summary-label">Warnings</div>
          <div class="summary-value warn-text">
            <span v-for="d in businessStructure.diagnostics" :key="d" class="diag-inline">{{ d }}</span>
          </div>
        </div>
        <div v-if="prunedTotal > 0" class="summary-item full">
          <div class="summary-label">Pruned Rows</div>
          <div class="summary-value muted-text">
            {{ prunedTotal }} incomplete rows excluded from graph
          </div>
        </div>
      </div>

      <!-- Controls -->
      <div class="controls">
        <div class="controls-left">
          <div class="field">
            <label class="label">Search</label>
            <input
              v-model="search"
              class="input"
              placeholder="Filter nodes by name…"
              aria-label="Search in organization structure"
            />
          </div>
        </div>
      </div>

      <!-- GRAPH VIEW -->
      <div class="graph-wrap" aria-label="Organization graph">
        <div class="graph-head">
          <div class="muted-text">Horizontal enterprise graph. Drag to pan, zoom for detail.</div>
          <div class="graph-meta muted-text">
            Nodes: <strong>{{ graphNodeCount }}</strong>
          </div>
        </div>

        <div class="graph-toolbar">
          <div class="field slim graph-depth">
            <label class="label">Depth</label>
            <select v-model.number="graphDepth" class="select">
              <option :value="1">Business Group</option>
              <option :value="2">Ledger</option>
              <option :value="3">Legal Entity</option>
              <option :value="4">Operating Unit</option>
              <option :value="5">Inventory Organization</option>
            </select>
          </div>

          <div class="graph-depth-actions">
            <button class="btn btn-sm btn-secondary" @click="graphDepth = 4">Collapse to OU</button>
            <button class="btn btn-sm btn-secondary" @click="graphDepth = 5">Expand all</button>
          </div>

          <div class="graph-zoom-actions">
            <button class="btn btn-sm btn-secondary" @click="zoomOut" :disabled="graphZoom <= 0.4">âˆ’</button>
            <button class="btn btn-sm btn-secondary" @click="resetGraphView">Reset</button>
            <button class="btn btn-sm btn-secondary" @click="zoomIn" :disabled="graphZoom >= 2.5">+</button>
            <span class="zoom-label muted-text">{{ Math.round(graphZoom * 100) }}%</span>
          </div>
        </div>

        <div v-if="graphTooLarge" class="error-box">
          Graph limited to {{ graphNodeCap }} nodes for performance. Refine search or reduce depth.
        </div>

        <div v-else-if="graphRenderError" class="error-box">
          {{ graphRenderError }}
        </div>

        <div
          v-else
          ref="graphViewportRef"
          class="graph-viewport"
          @mousedown="startGraphPan"
        >
          <div class="graph-canvas" :style="graphTransformStyle" v-html="graphSvg"></div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import mermaid from 'mermaid'

const props = defineProps({
  sessionId: { type: String, default: null },
  converted: { type: Boolean, default: false },
  businessStructure: { type: Object, default: null },
  loadingStructure: { type: Boolean, default: false },
})

const emit = defineEmits(['refresh'])

const DEPTH_MAP = {
  business_group: 1,
  ledger: 2,
  legal_entity: 3,
  operating_unit: 4,
  inventory_org: 5,
}

const LABEL_MAP = {
  business_group: 'Business Group',
  ledger: 'Ledger',
  legal_entity: 'Legal Entity',
  operating_unit: 'Operating Unit',
  inventory_org: 'Inventory Org',
}

const CLASS_MAP = {
  business_group: 'bg',
  ledger: 'ledger',
  legal_entity: 'le',
  operating_unit: 'ou',
  inventory_org: 'io',
}

// --- Status helpers ---
const statusBad = computed(() => {
  const s = props.businessStructure?.status
  return s && s !== 'ready'
})

const statusTitle = computed(() => {
  const s = props.businessStructure?.status
  if (!props.businessStructure) return 'No data'
  if (s === 'not_converted') return 'Conversion required'
  if (s === 'missing_files') return 'Required CSVs not found'
  if (s === 'missing_columns') return 'Required columns not found'
  if (s === 'no_data') return 'No usable data'
  return 'Unable to build structure'
})

const statusText = computed(() => {
  const s = props.businessStructure?.status
  if (!props.businessStructure) return 'The business structure data is not available yet.'
  if (s === 'not_converted') return 'Complete the XML to CSV conversion first.'
  if (s === 'missing_files') return 'FUN_BUSINESS_UNIT.CSV, INVENTORYORGANIZATIONMASTER.CSV, or INVENTORYORGANIZATIONCHILD.CSV not found in output.'
  if (s === 'missing_columns') return 'Required columns (PrimaryLedgerName, LegalEntityName, BusinessUnitName, NAME) are missing.'
  if (s === 'no_data') return 'CSVs were found but contained no usable rows.'
  return 'Check diagnostics below for details.'
})

const hasDiagnostics = computed(() => {
  return props.businessStructure?.diagnostics?.length > 0
})

const prunedTotal = computed(() => {
  return props.businessStructure?.pruned_summary?.total || 0
})

// --- Search ---
const search = ref('')

// --- Graph state ---
const graphDepth = ref(5)
const graphZoom = ref(1)
const graphOffset = reactive({ x: 0, y: 0 })
const graphPan = reactive({ active: false, startX: 0, startY: 0, originX: 0, originY: 0 })
const graphSvg = ref('')
const graphRenderError = ref('')
const graphTooLarge = ref(false)
const graphNodeCount = ref(0)
const graphNodeCap = 10000
const graphViewportRef = ref(null)

// --- Graph helpers ---
const graphTransformStyle = computed(() => ({
  transform: `translate(${graphOffset.x}px, ${graphOffset.y}px) scale(${graphZoom.value})`,
  transformOrigin: '0 0'
}))

function zoomIn() { graphZoom.value = Math.min(2.5, Number((graphZoom.value + 0.1).toFixed(2))) }
function zoomOut() { graphZoom.value = Math.max(0.4, Number((graphZoom.value - 0.1).toFixed(2))) }
function resetGraphView() { graphZoom.value = 1; graphOffset.x = 0; graphOffset.y = 0 }

function startGraphPan(e) {
  if (e.button !== 0) return
  graphPan.active = true
  graphPan.startX = e.clientX
  graphPan.startY = e.clientY
  graphPan.originX = graphOffset.x
  graphPan.originY = graphOffset.y
}
function onGraphMouseMove(e) {
  if (!graphPan.active) return
  graphOffset.x = graphPan.originX + (e.clientX - graphPan.startX)
  graphOffset.y = graphPan.originY + (e.clientY - graphPan.startY)
}
function onGraphMouseUp() { graphPan.active = false }

function sanitizeMermaidLabel(value) {
  return String(value || '\u2014').replace(/"/g, "'").replace(/[<>]/g, '')
}

function hashId(input) {
  const s = String(input || '')
  let h = 0
  for (let i = 0; i < s.length; i++) {
    h = ((h << 5) - h) + s.charCodeAt(i)
    h |= 0
  }
  return `n_${Math.abs(h)}`
}

// --- Filter tree by search ---
function matchesSearch(name) {
  if (!search.value) return true
  return String(name || '').toLowerCase().includes(search.value.toLowerCase())
}

function filterNode(node) {
  if (!search.value) return node
  if (!node) return null
  if (!node.children || node.children.length === 0) {
    return matchesSearch(node.name) ? node : null
  }
  const filteredChildren = node.children.map(filterNode).filter(Boolean)
  if (filteredChildren.length > 0 || matchesSearch(node.name)) {
    return { ...node, children: filteredChildren }
  }
  return null
}

const filteredNodes = computed(() => {
  const nodes = props.businessStructure?.nodes || []
  if (!search.value) return nodes
  return nodes.map(filterNode).filter(Boolean)
})

// --- Build Mermaid graph definition ---
const graphDefinition = computed(() => {
  const nodeSet = new Set()
  const edgeSet = new Set()
  const nodeLines = []
  const edgeLines = []
  const classLines = []
  const depth = graphDepth.value

  const addNode = (id, label, cls) => {
    if (nodeSet.has(id)) return
    nodeSet.add(id)
    nodeLines.push(`${id}["${sanitizeMermaidLabel(label)}"]`)
    if (cls) classLines.push(`class ${id} ${cls};`)
  }

  const addEdge = (from, to) => {
    const k = `${from}-->${to}`
    if (edgeSet.has(k)) return
    edgeSet.add(k)
    edgeLines.push(`${from} --> ${to}`)
  }

  function walkNode(node, parentId, parentPath) {
    const nodeDepth = DEPTH_MAP[node.node_type] || 1
    if (nodeDepth > depth) return

    const path = parentPath ? `${parentPath}/${node.name}` : node.name
    const id = hashId(`${node.node_type}|${path}`)
    const label = `${LABEL_MAP[node.node_type] || node.node_type}: ${node.name}`
    const cls = CLASS_MAP[node.node_type] || ''

    addNode(id, label, cls)
    if (parentId) addEdge(parentId, id)

    for (const child of node.children || []) {
      walkNode(child, id, path)
    }
  }

  for (const root of filteredNodes.value) {
    walkNode(root, null, '')
  }

  const classDefs = [
    'classDef bg fill:#dcfce7,stroke:#22c55e,color:#14532d,stroke-width:1.2px;',
    'classDef ledger fill:#ffedd5,stroke:#fb923c,color:#7c2d12,stroke-width:1.2px;',
    'classDef le fill:#ffe4e6,stroke:#f43f5e,color:#881337,stroke-width:1.2px;',
    'classDef ou fill:#f3e8ff,stroke:#a855f7,color:#581c87,stroke-width:1.2px;',
    'classDef io fill:#ccfbf1,stroke:#14b8a6,color:#134e4a,stroke-width:1.2px;',
  ]

  const text = [
    'flowchart LR',
    ...classDefs,
    ...nodeLines,
    ...edgeLines,
    ...classLines
  ].join('\n')

  return { text, nodeCount: nodeSet.size }
})

// --- Mermaid rendering ---
let mermaidInitialized = false

function initMermaid() {
  if (mermaidInitialized) return
  const isDark = document.documentElement.classList.contains('dark') ||
    window.matchMedia('(prefers-color-scheme: dark)').matches

  mermaid.initialize({
    startOnLoad: false,
    securityLevel: 'strict',
    theme: isDark ? 'dark' : 'default',
    flowchart: { curve: 'basis', nodeSpacing: 32, rankSpacing: 48 }
  })
  mermaidInitialized = true
}

async function renderGraph() {
  await nextTick()

  graphNodeCount.value = graphDefinition.value.nodeCount
  graphRenderError.value = ''

  if (graphNodeCount.value === 0) {
    graphSvg.value = ''
    return
  }

  if (graphNodeCount.value > graphNodeCap) {
    graphTooLarge.value = true
    graphSvg.value = ''
    return
  }
  graphTooLarge.value = false

  try {
    initMermaid()
    const id = `bs-graph-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
    const { svg } = await mermaid.render(id, graphDefinition.value.text)
    graphSvg.value = svg || ''
  } catch (e) {
    graphSvg.value = ''
    graphRenderError.value = `Failed to render graph: ${e?.message || 'unknown error'}`
  }
}

// --- Watchers ---
watch(
  [search, graphDepth, () => props.businessStructure],
  () => { renderGraph() },
  { deep: true }
)

watch(
  () => props.businessStructure,
  () => { resetGraphView() }
)

onMounted(() => {
  window.addEventListener('mousemove', onGraphMouseMove)
  window.addEventListener('mouseup', onGraphMouseUp)
  if (props.businessStructure?.status === 'ready') renderGraph()
})

onUnmounted(() => {
  window.removeEventListener('mousemove', onGraphMouseMove)
  window.removeEventListener('mouseup', onGraphMouseUp)
})

</script>

<style scoped>
.bs-panel { display: flex; flex-direction: column; gap: 12px; }

/* Header */
.bs-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.section-title {
  margin: 0;
  font-size: 1rem;
  font-weight: 900;
  color: var(--text-heading);
}
.section-help {
  margin: 6px 0 0 0;
  color: var(--text-secondary);
  font-size: 0.9rem;
}
.bs-actions { display: flex; gap: 10px; align-items: center; }

/* Summary */
.summary {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}
.summary-item {
  flex: 1;
  min-width: 200px;
  border-radius: 12px;
  border: 1px solid var(--border-light);
  background: linear-gradient(180deg, var(--surface-base), var(--surface-elevated));
  padding: 10px 12px;
}
.summary-label { font-size: 0.8rem; color: var(--text-tertiary); }
.summary-value { font-size: 1.02rem; font-weight: 900; color: var(--text-heading); margin-top: 2px; }

/* Controls */
.controls {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  align-items: flex-start;
  border: 1px solid var(--border-light);
  background: var(--surface-base);
  border-radius: 14px;
  padding: 12px;
}
.controls-left { display: grid; grid-template-columns: 320px 420px; gap: 12px; }
@media (max-width: 980px) { .controls-left { grid-template-columns: 1fr; width: 100%; } }

.field {
  border: 1px solid var(--border-light);
  background: var(--surface-elevated);
  border-radius: 12px;
  padding: 10px 12px;
}
.field.slim { padding: 8px 10px; }

.label {
  display: block;
  font-weight: 900;
  font-size: 0.85rem;
  color: var(--text-primary);
  margin-bottom: 8px;
}
.input, .select {
  width: 100%;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid var(--border-medium);
  background: var(--surface-base);
  color: var(--text-primary);
}

.muted-text { color: var(--text-tertiary); font-size: 0.88rem; }

/* ===== Graph ===== *//* ===== Graph ===== */
.graph-wrap {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.graph-head {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}

.graph-toolbar {
  display: flex;
  gap: 10px;
  align-items: end;
  flex-wrap: wrap;
  border: 1px solid var(--border-light);
  border-radius: 12px;
  background: var(--surface-base);
  padding: 10px;
}

.graph-depth { min-width: 220px; }
.graph-depth-actions,
.graph-zoom-actions {
  display: inline-flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}

.zoom-label {
  min-width: 48px;
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.graph-viewport {
  min-height: 560px;
  max-height: 70vh;
  overflow: auto;
  border: 1px solid var(--border-light);
  border-radius: 14px;
  background: linear-gradient(180deg, var(--surface-base), var(--surface-elevated));
  cursor: grab;
}

.graph-viewport:active { cursor: grabbing; }

.graph-canvas {
  min-width: 100%;
  min-height: 100%;
  padding: 16px;
  transition: transform 0.06s linear;
}

.graph-canvas :deep(svg) {
  display: block;
  width: max-content;
  max-width: none;
  height: auto;
}

/* Buttons + spinner */
.btn {
  border-radius: 10px;
  border: 1px solid var(--border-medium);
  padding: 10px 12px;
  cursor: pointer;
  font-weight: 900;
}
.btn:disabled { opacity: 0.55; cursor: not-allowed; }
.btn-secondary { background: var(--surface-elevated); color: var(--text-primary); }
.btn-sm { padding: 7px 10px; font-size: 0.85rem; border-radius: 10px; }

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
@keyframes spin { to { transform: rotate(360deg); } }

/* Error + empty */
.error-box {
  padding: 10px 12px;
  border: 1px solid #ef4444;
  background: rgba(239, 68, 68, 0.10);
  color: #991b1b;
  border-radius: 12px;
}
.empty-state {
  border: 1px dashed var(--border-medium);
  border-radius: 12px;
  padding: 18px;
  text-align: center;
  background: var(--surface-base);
  color: var(--text-secondary);
}
.empty-title { font-weight: 950; color: var(--text-primary); }
.empty-text { margin-top: 6px; font-size: 0.9rem; color: var(--text-tertiary); }

/* Diagnostics & status additions */
.diagnostics { margin-top: 10px; text-align: left; }
.diag-line { margin: 4px 0; font-size: 0.88rem; color: var(--text-secondary); }
.diag-inline { display: block; font-size: 0.88rem; color: #b45309; }
.status-ready { color: #16a34a; font-weight: 700; }
.warn-text { color: #b45309; font-size: 0.9rem; }
.summary-item.full { flex-basis: 100%; }
</style>
