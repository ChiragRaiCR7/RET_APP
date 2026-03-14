<template>
  <div class="bs-panel">
    <!-- Empty state -->
    <div v-if="!sessionId" class="empty-state">
      <div class="empty-title">No active session</div>
      <div class="empty-text">
        Upload a ZIP in Utility tab to scan and generate the organization structure.
      </div>
    </div>

    <div v-else>
      <!-- Top -->
      <div class="bs-top">
        <div class="bs-title">
          <h4 class="section-title">Organization Structure</h4>
          <p class="section-help">
            Primary → Company → Business Group → Ledger → Legal Entity → Operating Unit → Industrial Organization
          </p>
        </div>

        <div class="bs-actions">
          <button class="btn btn-secondary" @click="refresh" :disabled="loading">
            <span v-if="loading" class="spinner" aria-hidden="true"></span>
            {{ loading ? 'Loading…' : 'Refresh' }}
          </button>
        </div>
      </div>

      <!-- Summary -->
      <div v-if="scanSummary" class="summary">
        <div class="summary-item">
          <div class="summary-label">Source</div>
          <div class="summary-value">{{ displayCompany }}</div>
        </div>
        <div class="summary-item">
          <div class="summary-label">Files</div>
          <div class="summary-value">{{ scanSummary.totalFiles ?? 0 }}</div>
        </div>
        <div class="summary-item">
          <div class="summary-label">Groups</div>
          <div class="summary-value">{{ scanSummary.totalGroups ?? 0 }}</div>
        </div>
      </div>

      <!-- Controls -->
      <div class="controls">
        <div class="controls-left">
          <div class="field">
            <label class="label">View</label>
            <div class="segmented" role="group" aria-label="Organization structure view">
              <label class="seg-option">
                <input type="radio" v-model="viewMode" value="tree" />
                <span>Org Tree</span>
              </label>
              <label class="seg-option">
                <input type="radio" v-model="viewMode" value="graph" />
                <span>Graph (Horizontal)</span>
              </label>
              <label class="seg-option">
                <input type="radio" v-model="viewMode" value="matrix" />
                <span>Matrix</span>
              </label>
            </div>
          </div>

          <div class="field">
            <label class="label">Search</label>
            <input
              v-model="search"
              class="input"
              placeholder="Search Company / Group / Ledger / LE / OU / Industry / File…"
              aria-label="Search in organization structure"
            />
            <p class="field-help">
              Filters the dataset before building the hierarchy (fast + accurate).
            </p>
          </div>
        </div>

        <div class="controls-right">
          <label class="toggle">
            <input type="checkbox" v-model="ui.compact" />
            <span>Compact</span>
          </label>

          <label class="toggle">
            <input type="checkbox" v-model="ui.showFiles" />
            <span>Show files</span>
          </label>

          <div class="field slim">
            <label class="label">Files per node</label>
            <select v-model.number="ui.filesPerNode" class="select">
              <option :value="25">25</option>
              <option :value="50">50</option>
              <option :value="100">100</option>
              <option :value="250">250</option>
            </select>
            <p class="field-help">Limits DOM size for big archives.</p>
          </div>
        </div>
      </div>

      <!-- Error -->
      <div v-if="error" class="error-box">
        {{ error }}
      </div>

      <!-- No data -->
      <div v-if="!loading && effectiveFiles.length === 0" class="empty-state">
        <div class="empty-title">No scan file metadata available</div>
        <div class="empty-text">
          Ensure scan response includes <code>files</code>, or enable fetch-on-empty to load session metadata.
        </div>
      </div>

      <!-- TREE VIEW -->
      <div
        v-else-if="viewMode === 'tree'"
        class="tree-wrap"
        :class="{ compact: ui.compact }"
        aria-label="Organization structure tree"
      >
        <div class="tree-hint muted-text">
          Industrial Organization ordering uses Oracle-first module ordering when recognizable; otherwise alphabetical.
        </div>

        <ul class="org-tree">
          <li>
            <!-- Primary -->
            <div class="node node-primary">
              <div class="node-title">{{ labels.primary }}</div>
              <div class="node-sub">{{ filteredFiles.length }} files</div>
            </div>

            <ul>
              <!-- Company -->
              <li>
                <div class="node node-company">
                  <div class="node-title">{{ labels.company }}: {{ displayCompany }}</div>
                  <div class="node-sub">{{ filteredFiles.length }} files • {{ tree.businessGroups.length }} business group(s)</div>
                </div>

                <ul>
                  <!-- Business Groups -->
                  <li v-for="bg in tree.businessGroups" :key="bg.key">
                    <div class="node node-bg">
                      <div class="node-title">{{ labels.businessGroup }}: {{ bg.name }}</div>
                      <div class="node-sub">{{ bg.count }} files • {{ bg.ledgers.length }} ledger(s)</div>
                    </div>

                    <ul>
                      <!-- Ledgers -->
                      <li v-for="led in bg.ledgers" :key="led.key">
                        <div class="node node-ledger">
                          <div class="node-title">{{ labels.ledger }}: {{ led.name }}</div>
                          <div class="node-sub">{{ led.count }} files • {{ led.legalEntities.length }} legal entity(ies)</div>
                        </div>

                        <ul>
                          <!-- Legal Entities -->
                          <li v-for="le in led.legalEntities" :key="le.key">
                            <div class="node node-le">
                              <div class="node-title">{{ labels.legalEntity }}: {{ le.name }}</div>
                              <div class="node-sub">{{ le.count }} files • {{ le.operatingUnits.length }} operating unit(s)</div>
                            </div>

                            <ul>
                              <!-- Operating Units -->
                              <li v-for="ou in le.operatingUnits" :key="ou.key">
                                <div class="node node-ou">
                                  <div class="node-title">{{ labels.operatingUnit }}: {{ ou.name }}</div>
                                  <div class="node-sub">{{ ou.count }} files • {{ ou.industrialOrgs.length }} industrial org(s)</div>
                                </div>

                                <ul>
                                  <!-- Industrial Orgs -->
                                  <li v-for="io in ou.industrialOrgs" :key="io.key">
                                    <div class="node node-io">
                                      <div class="node-title">
                                        {{ labels.industrialOrganization }}: {{ io.name }}
                                        <span class="pill">{{ io.count }}</span>
                                      </div>
                                      <div class="node-sub">
                                        {{ io.types.join(', ') || '—' }}
                                      </div>
                                    </div>

                                    <!-- Files -->
                                    <ul v-if="ui.showFiles">
                                      <li v-for="f in io.filesLimited" :key="f.key">
                                        <div class="node node-file">
                                          <div class="node-title">{{ f.displayName }}</div>
                                          <div class="node-sub">{{ f.type }} • {{ f.sizeLabel }}</div>
                                        </div>
                                      </li>

                                      <li v-if="io.moreCount > 0" class="more-row">
                                        <button class="btn btn-sm btn-secondary" @click="expandNode(io.key)">
                                          Show {{ io.moreCount }} more…
                                        </button>
                                      </li>
                                    </ul>
                                  </li>
                                </ul>
                              </li>
                            </ul>

                          </li>
                        </ul>

                      </li>
                    </ul>
                  </li>
                </ul>

              </li>
            </ul>

          </li>
        </ul>
      </div>

      <!-- GRAPH VIEW -->
      <div v-else-if="viewMode === 'graph'" class="graph-wrap" aria-label="Organization graph">
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
              <option :value="3">Business Group</option>
              <option :value="4">Ledger</option>
              <option :value="5">Legal Entity</option>
              <option :value="6">Operating Unit</option>
              <option :value="7">Industrial Organization</option>
              <option :value="8" :disabled="!ui.showFiles">Files (requires Show files)</option>
            </select>
          </div>

          <div class="graph-depth-actions">
            <button class="btn btn-sm btn-secondary" @click="collapseToOU">Collapse to OU</button>
            <button class="btn btn-sm btn-secondary" @click="expandAllDepth">Expand all</button>
          </div>

          <div class="graph-zoom-actions">
            <button class="btn btn-sm btn-secondary" @click="zoomOut" :disabled="graphZoom <= 0.4">−</button>
            <button class="btn btn-sm btn-secondary" @click="resetGraphView">Reset</button>
            <button class="btn btn-sm btn-secondary" @click="zoomIn" :disabled="graphZoom >= 2.5">＋</button>
            <span class="zoom-label muted-text">{{ Math.round(graphZoom * 100) }}%</span>
          </div>
        </div>

        <div v-if="graphTooLarge" class="error-box">
          Graph view is limited to {{ graphNodeCap }} nodes for performance.
          Refine search, disable files, or use Matrix view for large datasets.
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

      <!-- MATRIX VIEW -->
      <div v-else class="matrix-wrap" :class="{ compact: ui.compact }" aria-label="Organization matrix">
        <div class="matrix-head">
          <div class="muted-text">
            Matrix view is fastest for large ZIPs and is naturally “horizontal”.
          </div>
          <div class="matrix-count muted-text">
            Rows: <strong>{{ matrixRows.length }}</strong>
          </div>
        </div>

        <div class="matrix-table-wrap">
          <table class="matrix-table">
            <thead>
              <tr>
                <th>{{ labels.primary }}</th>
                <th>{{ labels.company }}</th>
                <th>{{ labels.businessGroup }}</th>
                <th>{{ labels.ledger }}</th>
                <th>{{ labels.legalEntity }}</th>
                <th>{{ labels.operatingUnit }}</th>
                <th>{{ labels.industrialOrganization }}</th>
                <th v-if="ui.showFiles">File</th>
                <th v-if="ui.showFiles">Type</th>
                <th v-if="ui.showFiles">Size</th>
              </tr>
            </thead>

            <tbody>
              <tr v-for="row in matrixRows" :key="row.key">
                <td><span class="cell-box primary">{{ row.primary }}</span></td>
                <td><span class="cell-box company">{{ row.company }}</span></td>
                <td><span class="cell-box bg">{{ row.businessGroup }}</span></td>
                <td><span class="cell-box ledger">{{ row.ledger }}</span></td>
                <td><span class="cell-box le">{{ row.legalEntity }}</span></td>
                <td><span class="cell-box ou">{{ row.operatingUnit }}</span></td>
                <td><span class="cell-box io">{{ row.industrialOrganization }}</span></td>

                <template v-if="ui.showFiles">
                  <td class="file-col">{{ row.file }}</td>
                  <td>{{ row.type }}</td>
                  <td>{{ row.size }}</td>
                </template>
              </tr>

              <tr v-if="matrixRows.length === 0">
                <td :colspan="ui.showFiles ? 10 : 7" class="empty-row">
                  No rows match your search.
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <p class="muted-text">Tip: Search “ledger”, “ou”, or an industry keyword to narrow results.</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import mermaid from 'mermaid'
import api from '@/utils/api'

/**
 * Props from MainView
 */
const props = defineProps({
  sessionId: { type: String, default: null },
  uploadedFilename: { type: String, default: '' },
  scanSummary: { type: Object, default: null },
  scannedFiles: { type: Array, default: () => [] },
  scannedGroups: { type: Array, default: () => [] },

  // Fixed module ordering — we reuse it to order Industrial Organization
  moduleOrder: {
    type: Array,
    default: () => ([
      'XLE', 'FUN', 'FND',
      'GL', 'XLA',
      'AP', 'AR', 'CE', 'FA',
      'HZ', 'IBY', 'INV', 'ZX',
      'MISC', 'EXTRAS'
    ])
  },

  // Optional: supply company name directly (best result)
  companyName: { type: String, default: '' },

  // If scannedFiles are empty but sessionId exists, optionally fetch metadata
  fetchOnEmpty: { type: Boolean, default: true }
})

/** Labels requested (and editable centrally) */
const labels = reactive({
  primary: 'Primary',
  company: 'Company',
  businessGroup: 'Business Group',
  ledger: 'Ledger',
  legalEntity: 'Legal Entity',
  operatingUnit: 'Operating Unit',
  industrialOrganization: 'Industrial Organization'
})

/** UI state */
const ui = reactive({
  compact: false,
  showFiles: false,      // ✅ default OFF to avoid showing filenames unless needed
  filesPerNode: 50
})

const viewMode = ref('tree') // 'tree' | 'graph' | 'matrix'
const search = ref('')

const graphDepth = ref(7)
const graphZoom = ref(1)
const graphOffset = reactive({ x: 0, y: 0 })
const graphPan = reactive({ active: false, startX: 0, startY: 0, originX: 0, originY: 0 })
const graphSvg = ref('')
const graphRenderError = ref('')
const graphTooLarge = ref(false)
const graphNodeCount = ref(0)
const graphNodeCap = 10000
const graphViewportRef = ref(null)

const loading = ref(false)
const error = ref('')
const fetchedFiles = ref([])

/** --------------- Normalization / semantic helpers --------------- */

/** Remove extensions from display */
const EXT_RE = /\.(xml\.gz|xml|zip|csv|xlsx|xls|xlf)$/i

function stripExt(name) {
  const s = String(name || '')
  return s.replace(EXT_RE, '')
}

/** Basic “prettify” for org names: underscores/hyphens → spaces, title case, remove noise tokens */
const NOISE_TOKENS = new Set([
  'DATA', 'EXPORT', 'EXTRACT', 'OUTPUT', 'INPUT', 'FILES', 'FILE', 'REPORT', 'REPORTS',
  'TEMP', 'TMP', 'FINAL', 'VERSION', 'V1', 'V2', 'TEST', 'DEV', 'PROD',
  'XML', 'CSV', 'XLSX', 'ZIP'
])

/**
 * Expand abbreviations (you can keep extending)
 * Add your industry terms here later as you learn them.
 */
const ABBR = {
  'LE': 'Legal Entity',
  'OU': 'Operating Unit',
  'BG': 'Business Group',
  'LED': 'Ledger',
  'LEDGER': 'Ledger',
  'ORG': 'Organization',
  'IND': 'Industrial',
  'INDORG': 'Industrial Organization',
  'PRIMARY': 'Primary'
}

function titleCase(s) {
  return s
    .toLowerCase()
    .split(' ')
    .filter(Boolean)
    .map(w => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}

/** Try to make names enterprise-friendly */
function prettyName(raw) {
  let s = String(raw || '').trim()
  if (!s) return '—'

  // Remove extensions and normalize separators
  s = stripExt(s)
  s = s.replace(/[_\-]+/g, ' ')
  s = s.replace(/\s+/g, ' ').trim()

  // Strip leading/trailing non-word
  s = s.replace(/^[^A-Za-z0-9]+|[^A-Za-z0-9]+$/g, '')

  // Remove pure noise tokens
  const parts = s.split(' ').filter(Boolean)
  const cleaned = parts.filter(p => !NOISE_TOKENS.has(p.toUpperCase()))
  s = cleaned.join(' ').trim() || s

  // Expand abbreviations when the whole token matches
  const expanded = s.split(' ').map(tok => ABBR[tok.toUpperCase()] || tok)
  s = expanded.join(' ')

  // Title case final
  return titleCase(s)
}

/** Paths */
function normalizePath(p) {
  return String(p || '').replace(/\\/g, '/').replace(/^\/+/, '').trim()
}

function pickBestPath(entry) {
  return (
    normalizePath(entry?.folder_path) ||
    normalizePath(entry?.logical_path) ||
    normalizePath(entry?.path) ||
    normalizePath(entry?.filename)
  )
}

function splitSegments(entry) {
  const p = pickBestPath(entry)
  return p ? p.split('/').filter(Boolean) : []
}

function fileNameFromEntry(entry) {
  const fname = normalizePath(entry?.filename)
  if (fname) return fname.split('/').pop()
  const segs = splitSegments(entry)
  return segs.length ? segs[segs.length - 1] : '(unnamed)'
}

function fileType(entry) {
  const t = String(entry?.file_type || '').toLowerCase().trim()
  return t || 'file'
}

function formatSizeBytes(n) {
  const x = Number(n || 0)
  if (!x) return '—'
  if (x < 1024) return `${x} B`
  if (x < 1024 ** 2) return `${(x / 1024).toFixed(1)} KB`
  if (x < 1024 ** 3) return `${(x / (1024 ** 2)).toFixed(1)} MB`
  return `${(x / (1024 ** 3)).toFixed(1)} GB`
}

/** “Industrial Org” normalization uses module-like tokens if present */
function normalizeIndustrialOrg(v) {
  if (!v) return 'Misc'
  const raw = String(v).trim().toUpperCase()
  const token = raw.split(/[\/\s._-]+/)[0]
  // If it's an Oracle module code, keep it as-is; else prettify
  const isModule = props.moduleOrder.includes(token)
  return isModule ? token : prettyName(v)
}

/** Module ordering applied to Industrial Org: known module codes first */
function industrialRank(name) {
  const raw = String(name || '').toUpperCase()
  const idx = props.moduleOrder.indexOf(raw)
  return idx === -1 ? 9999 : idx
}
function sortIndustrial(a, b) {
  const A = String(a?.name ?? a).toUpperCase()
  const B = String(b?.name ?? b).toUpperCase()
  const ra = industrialRank(A)
  const rb = industrialRank(B)
  if (ra !== rb) return ra - rb
  return String(a?.name ?? a).localeCompare(String(b?.name ?? b), undefined, { sensitivity: 'base' })
}

/**
 * Derive levels in your requested order:
 * Primary → Company → Business Group → Ledger → Legal Entity → Operating Unit → Industrial Organization → Files
 *
 * We map folder segments:
 * seg[0] = Business Group
 * seg[1] = Ledger
 * seg[2] = Legal Entity
 * seg[3] = Operating Unit
 * seg[4] = Industrial Organization
 *
 * Company comes from props.companyName or uploadedFilename (stripped)
 * Industrial Org falls back to entry.group if seg[4] missing (because scan groups are meaningful)
 */
function deriveLevels(entry) {
  const segs = splitSegments(entry)

  const company = prettyName(props.companyName || stripExt(props.uploadedFilename) || '(Company)')
  const businessGroup = prettyName(segs[0] || '(Business Group)')
  const ledger = prettyName(segs[1] || '(Ledger)')
  const legalEntity = prettyName(segs[2] || '(Legal Entity)')
  const operatingUnit = prettyName(segs[3] || '(Operating Unit)')

  const industrialOrganization = normalizeIndustrialOrg(segs[4] || entry?.group || '(Industrial Organization)')

  const file = fileNameFromEntry(entry)
  const displayName = prettyName(stripExt(file))  // ✅ hides extension & prettifies

  return {
    primary: labels.primary,
    company,
    businessGroup,
    ledger,
    legalEntity,
    operatingUnit,
    industrialOrganization,
    file,
    displayName
  }
}

/** --------------- Data source handling --------------- */

const displayCompany = computed(() => {
  return prettyName(props.companyName || stripExt(props.uploadedFilename) || '(Company)')
})

const effectiveFiles = computed(() => {
  const p = Array.isArray(props.scannedFiles) ? props.scannedFiles : []
  if (p.length) return p
  const f = Array.isArray(fetchedFiles.value) ? fetchedFiles.value : []
  return f
})

/** Filter before building tree */
const filteredFiles = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return effectiveFiles.value

  return effectiveFiles.value.filter(entry => {
    const lv = deriveLevels(entry)
    const hay = `
      ${lv.company} ${lv.businessGroup} ${lv.ledger} ${lv.legalEntity}
      ${lv.operatingUnit} ${lv.industrialOrganization} ${lv.displayName}
      ${pickBestPath(entry)}
    `.toLowerCase()
    return hay.includes(q)
  })
})

/** Expand “Show more files…” per industrial org node */
const expandedNodes = ref(new Set())
function expandNode(nodeKey) {
  const next = new Set(expandedNodes.value)
  next.add(nodeKey)
  expandedNodes.value = next
}

/**
 * Build tree:
 * Company -> BG -> Ledger -> LE -> OU -> IO -> files
 */
const tree = computed(() => {
  const data = filteredFiles.value || []
  const bgMap = new Map()

  for (const entry of data) {
    const lv = deriveLevels(entry)
    const type = fileType(entry)
    const sizeLabel = formatSizeBytes(entry?.size)

    if (!bgMap.has(lv.businessGroup)) bgMap.set(lv.businessGroup, new Map())
    const ledgerMap = bgMap.get(lv.businessGroup)

    if (!ledgerMap.has(lv.ledger)) ledgerMap.set(lv.ledger, new Map())
    const leMap = ledgerMap.get(lv.ledger)

    if (!leMap.has(lv.legalEntity)) leMap.set(lv.legalEntity, new Map())
    const ouMap = leMap.get(lv.legalEntity)

    if (!ouMap.has(lv.operatingUnit)) ouMap.set(lv.operatingUnit, new Map())
    const ioMap = ouMap.get(lv.operatingUnit)

    if (!ioMap.has(lv.industrialOrganization)) ioMap.set(lv.industrialOrganization, { types: new Set(), files: [] })
    const agg = ioMap.get(lv.industrialOrganization)

    agg.types.add(type)
    agg.files.push({
      key: `${lv.businessGroup}/${lv.ledger}/${lv.legalEntity}/${lv.operatingUnit}/${lv.industrialOrganization}/${lv.file}`,
      name: lv.file,
      displayName: lv.displayName,
      type,
      sizeLabel
    })
  }

  const businessGroups = [...bgMap.entries()]
    .map(([bgName, ledgerMap]) => {
      const ledgers = [...ledgerMap.entries()]
        .map(([ledName, leMap]) => {
          const legalEntities = [...leMap.entries()]
            .map(([leName, ouMap]) => {
              const operatingUnits = [...ouMap.entries()]
                .map(([ouName, ioMap]) => {
                  const industrialOrgs = [...ioMap.entries()]
                    .map(([ioName, agg]) => {
                      const allFiles = (agg.files || []).sort((a, b) =>
                        a.displayName.localeCompare(b.displayName, undefined, { sensitivity: 'base' })
                      )

                      const nodeKey = `${bgName}/${ledName}/${leName}/${ouName}/${ioName}`
                      const expanded = expandedNodes.value.has(nodeKey)
                      const limit = ui.filesPerNode
                      const filesLimited = expanded ? allFiles : allFiles.slice(0, limit)
                      const moreCount = expanded ? 0 : Math.max(0, allFiles.length - limit)

                      return {
                        name: ioName,
                        key: nodeKey,
                        count: allFiles.length,
                        types: [...agg.types].sort(),
                        files: allFiles,
                        filesLimited,
                        moreCount
                      }
                    })
                    .sort(sortIndustrial) // ✅ order IO using module order when applicable

                  const count = industrialOrgs.reduce((s, x) => s + x.count, 0)
                  return {
                    name: ouName,
                    key: `${bgName}/${ledName}/${leName}/${ouName}`,
                    count,
                    industrialOrgs
                  }
                })
                .sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }))

              const count = operatingUnits.reduce((s, x) => s + x.count, 0)
              return {
                name: leName,
                key: `${bgName}/${ledName}/${leName}`,
                count,
                operatingUnits
              }
            })
            .sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }))

          const count = legalEntities.reduce((s, x) => s + x.count, 0)
          return {
            name: ledName,
            key: `${bgName}/${ledName}`,
            count,
            legalEntities
          }
        })
        .sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }))

      const count = ledgers.reduce((s, x) => s + x.count, 0)
      return {
        name: bgName,
        key: bgName,
        count,
        ledgers
      }
    })
    .sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }))

  return { businessGroups }
})

/**
 * Matrix rows:
 * - If showFiles: one row per file
 * - Else: one row per industrial org (aggregated)
 */
const matrixRows = computed(() => {
  const rows = []
  const showFiles = ui.showFiles

  for (const bg of tree.value.businessGroups) {
    for (const led of bg.ledgers) {
      for (const le of led.legalEntities) {
        for (const ou of le.operatingUnits) {
          for (const io of ou.industrialOrgs) {
            if (!showFiles) {
              rows.push({
                key: `${bg.name}/${led.name}/${le.name}/${ou.name}/${io.name}`,
                primary: labels.primary,
                company: displayCompany.value,
                businessGroup: bg.name,
                ledger: led.name,
                legalEntity: le.name,
                operatingUnit: ou.name,
                industrialOrganization: io.name
              })
            } else {
              for (const f of io.filesLimited) {
                rows.push({
                  key: f.key,
                  primary: labels.primary,
                  company: displayCompany.value,
                  businessGroup: bg.name,
                  ledger: led.name,
                  legalEntity: le.name,
                  operatingUnit: ou.name,
                  industrialOrganization: io.name,
                  file: f.displayName,  // ✅ extension removed + prettified
                  type: f.type,
                  size: f.sizeLabel
                })
              }
            }
          }
        }
      }
    }
  }
  return rows
})

const graphTransformStyle = computed(() => ({
  transform: `translate(${graphOffset.x}px, ${graphOffset.y}px) scale(${graphZoom.value})`,
  transformOrigin: '0 0'
}))

function collapseToOU() {
  graphDepth.value = 6
}

function expandAllDepth() {
  graphDepth.value = ui.showFiles ? 8 : 7
}

function zoomIn() {
  graphZoom.value = Math.min(2.5, Number((graphZoom.value + 0.1).toFixed(2)))
}

function zoomOut() {
  graphZoom.value = Math.max(0.4, Number((graphZoom.value - 0.1).toFixed(2)))
}

function resetGraphView() {
  graphZoom.value = 1
  graphOffset.x = 0
  graphOffset.y = 0
}

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

function onGraphMouseUp() {
  graphPan.active = false
}

function sanitizeMermaidLabel(value) {
  return String(value || '—')
    .replace(/"/g, "'")
    .replace(/[<>]/g, '')
}

function hashId(input) {
  const s = String(input || '')
  let h = 0
  for (let i = 0; i < s.length; i += 1) {
    h = ((h << 5) - h) + s.charCodeAt(i)
    h |= 0
  }
  return `n_${Math.abs(h)}`
}

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

  const primaryId = hashId(`primary|${labels.primary}`)
  addNode(primaryId, labels.primary, 'primary')

  let companyId = null
  if (depth >= 2) {
    companyId = hashId(`company|${displayCompany.value}`)
    addNode(companyId, `${labels.company}: ${displayCompany.value}`, 'company')
    addEdge(primaryId, companyId)
  }

  for (const bg of tree.value.businessGroups) {
    if (depth < 3) continue
    const bgId = hashId(`bg|${bg.key}`)
    addNode(bgId, `${labels.businessGroup}: ${bg.name}`, 'bg')
    addEdge(companyId || primaryId, bgId)

    for (const led of bg.ledgers) {
      if (depth < 4) continue
      const ledId = hashId(`ledger|${bg.key}|${led.key}`)
      addNode(ledId, `${labels.ledger}: ${led.name}`, 'ledger')
      addEdge(bgId, ledId)

      for (const le of led.legalEntities) {
        if (depth < 5) continue
        const leId = hashId(`le|${bg.key}|${led.key}|${le.key}`)
        addNode(leId, `${labels.legalEntity}: ${le.name}`, 'le')
        addEdge(ledId, leId)

        for (const ou of le.operatingUnits) {
          if (depth < 6) continue
          const ouId = hashId(`ou|${bg.key}|${led.key}|${le.key}|${ou.key}`)
          addNode(ouId, `${labels.operatingUnit}: ${ou.name}`, 'ou')
          addEdge(leId, ouId)

          for (const io of ou.industrialOrgs) {
            if (depth < 7) continue
            const ioId = hashId(`io|${bg.key}|${led.key}|${le.key}|${ou.key}|${io.key}`)
            addNode(ioId, `${labels.industrialOrganization}: ${io.name}`, 'io')
            addEdge(ouId, ioId)

            if (ui.showFiles && depth >= 8) {
              for (const f of io.filesLimited) {
                const fileId = hashId(`file|${f.key}`)
                addNode(fileId, f.displayName, 'file')
                addEdge(ioId, fileId)
              }
            }
          }
        }
      }
    }
  }

  const nodeCount = nodeSet.size
  const classDefs = [
    'classDef primary fill:#e0f2fe,stroke:#38bdf8,color:#0c4a6e,stroke-width:1.2px;',
    'classDef company fill:#e0e7ff,stroke:#6366f1,color:#312e81,stroke-width:1.2px;',
    'classDef bg fill:#dcfce7,stroke:#22c55e,color:#14532d,stroke-width:1.2px;',
    'classDef ledger fill:#ffedd5,stroke:#fb923c,color:#7c2d12,stroke-width:1.2px;',
    'classDef le fill:#ffe4e6,stroke:#f43f5e,color:#881337,stroke-width:1.2px;',
    'classDef ou fill:#f3e8ff,stroke:#a855f7,color:#581c87,stroke-width:1.2px;',
    'classDef io fill:#ccfbf1,stroke:#14b8a6,color:#134e4a,stroke-width:1.2px;',
    'classDef file fill:#f8fafc,stroke:#94a3b8,color:#334155,stroke-dasharray: 4 2;'
  ]

  const text = [
    'flowchart LR',
    ...classDefs,
    ...nodeLines,
    ...edgeLines,
    ...classLines
  ].join('\n')

  return { text, nodeCount }
})

let mermaidInitialized = false

function initMermaid() {
  if (mermaidInitialized) return
  const isDark = document.documentElement.classList.contains('dark') ||
    window.matchMedia('(prefers-color-scheme: dark)').matches

  mermaid.initialize({
    startOnLoad: false,
    securityLevel: 'strict',
    theme: isDark ? 'dark' : 'default',
    flowchart: {
      curve: 'basis',
      nodeSpacing: 32,
      rankSpacing: 48
    }
  })
  mermaidInitialized = true
}

async function renderGraph() {
  if (viewMode.value !== 'graph') return
  await nextTick()

  graphNodeCount.value = graphDefinition.value.nodeCount
  graphRenderError.value = ''

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

watch(() => ui.showFiles, (enabled) => {
  if (!enabled && graphDepth.value > 7) graphDepth.value = 7
})

watch(
  [viewMode, search, () => ui.showFiles, () => ui.filesPerNode, graphDepth, () => effectiveFiles.value.length],
  () => {
    if (viewMode.value === 'graph') renderGraph()
  }
)

onMounted(() => {
  window.addEventListener('mousemove', onGraphMouseMove)
  window.addEventListener('mouseup', onGraphMouseUp)
})

onUnmounted(() => {
  window.removeEventListener('mousemove', onGraphMouseMove)
  window.removeEventListener('mouseup', onGraphMouseUp)
})

/** --------------- Fetch fallback --------------- */
async function fetchSessionFilesIfNeeded() {
  if (!props.fetchOnEmpty) return
  if (!props.sessionId) return
  if (Array.isArray(props.scannedFiles) && props.scannedFiles.length) return

  loading.value = true
  error.value = ''
  try {
    // Your router provides: GET /files/session/{session_id}
    const res = await api.get(`/files/session/${props.sessionId}`)
    const scanned = res.data?.scanned_files || res.data?.xml_files || []
    fetchedFiles.value = Array.isArray(scanned) ? scanned : []
  } catch (e) {
    error.value = 'Failed to load session metadata: ' + (e.response?.data?.detail || e.message)
    fetchedFiles.value = []
  } finally {
    loading.value = false
    if (viewMode.value === 'graph') renderGraph()
  }
}

function refresh() {
  expandedNodes.value = new Set()
  resetGraphView()
  fetchSessionFilesIfNeeded()
}

watch(
  () => props.sessionId,
  () => {
    fetchedFiles.value = []
    expandedNodes.value = new Set()
    resetGraphView()
    fetchSessionFilesIfNeeded()
  },
  { immediate: true }
)

watch(
  () => props.scannedFiles,
  (v) => {
    if (Array.isArray(v) && v.length) fetchedFiles.value = []
    if (viewMode.value === 'graph') renderGraph()
  },
  { deep: false }
)
</script>

<style scoped>
/* ===== New Palette: modern, subtle, enterprise ===== */
:root {
  /* (scoped) fallbacks if global vars missing */
}

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

.controls-right {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}

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
.field-help {
  margin: 8px 0 0 0;
  font-size: 0.84rem;
  color: var(--text-tertiary);
  line-height: 1.25;
}

.input, .select {
  width: 100%;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid var(--border-medium);
  background: var(--surface-base);
  color: var(--text-primary);
}

.segmented { display: inline-flex; gap: 8px; flex-wrap: wrap; }
.seg-option {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 10px;
  border: 1px solid var(--border-light);
  background: var(--surface-base);
  cursor: pointer;
}
.seg-option input { accent-color: var(--brand-primary); }

.toggle {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid var(--border-light);
  background: var(--surface-elevated);
  cursor: pointer;
  font-weight: 900;
  color: var(--text-secondary);
}
.toggle input { accent-color: var(--brand-primary); }

.muted-text { color: var(--text-tertiary); font-size: 0.88rem; }

/* ===== Tree layout ===== */
.tree-wrap { display: flex; flex-direction: column; gap: 10px; }

.org-tree, .org-tree ul { list-style: none; margin: 0; padding: 0; }
.org-tree li { position: relative; padding-left: 28px; margin: 10px 0; }

/* connectors */
.org-tree li::before {
  content: '';
  position: absolute;
  top: 18px;
  left: 10px;
  width: 18px;
  height: 1px;
  background: color-mix(in oklab, var(--border-medium) 70%, transparent);
}
.org-tree li::after {
  content: '';
  position: absolute;
  top: -10px;
  left: 10px;
  width: 1px;
  height: calc(100% + 20px);
  background: color-mix(in oklab, var(--border-light) 70%, transparent);
}
.org-tree > li { padding-left: 0; }
.org-tree > li::before,
.org-tree > li::after { display: none; }

/* node boxes */
.node {
  display: inline-flex;
  flex-direction: column;
  gap: 4px;
  min-width: 280px;
  max-width: 720px;
  padding: 10px 12px;
  border-radius: 14px;
  border: 1px solid var(--border-light);
  background: var(--surface-base);
  box-shadow: 0 6px 16px rgba(15, 23, 42, 0.06);
}
.node-title {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  font-weight: 950;
  color: var(--text-primary);
}
.node-sub {
  font-size: 0.85rem;
  color: var(--text-tertiary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ===== Improved palette per level ===== */
.node-primary {
  border-color: rgba(56, 189, 248, 0.35);
  background: linear-gradient(180deg, rgba(56, 189, 248, 0.10), rgba(56, 189, 248, 0.04));
}
.node-company {
  border-color: rgba(99, 102, 241, 0.35);
  background: linear-gradient(180deg, rgba(99, 102, 241, 0.10), rgba(99, 102, 241, 0.04));
}
.node-bg {
  border-color: rgba(34, 197, 94, 0.35);
  background: linear-gradient(180deg, rgba(34, 197, 94, 0.10), rgba(34, 197, 94, 0.04));
}
.node-ledger {
  border-color: rgba(251, 146, 60, 0.35);
  background: linear-gradient(180deg, rgba(251, 146, 60, 0.10), rgba(251, 146, 60, 0.04));
}
.node-le {
  border-color: rgba(244, 63, 94, 0.30);
  background: linear-gradient(180deg, rgba(244, 63, 94, 0.10), rgba(244, 63, 94, 0.04));
}
.node-ou {
  border-color: rgba(168, 85, 247, 0.30);
  background: linear-gradient(180deg, rgba(168, 85, 247, 0.10), rgba(168, 85, 247, 0.04));
}
.node-io {
  border-color: rgba(20, 184, 166, 0.30);
  background: linear-gradient(180deg, rgba(20, 184, 166, 0.10), rgba(20, 184, 166, 0.04));
}
.node-file {
  border-style: dashed;
  opacity: 0.97;
  background: linear-gradient(180deg, rgba(148, 163, 184, 0.08), rgba(148, 163, 184, 0.03));
}

.pill {
  display: inline-flex;
  align-items: center;
  padding: 2px 10px;
  border-radius: 999px;
  font-size: 0.78rem;
  font-weight: 950;
  border: 1px solid var(--border-light);
  background: rgba(15, 23, 42, 0.06);
  color: var(--text-secondary);
}

.more-row { padding-left: 28px; }

/* ===== Graph ===== */
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

/* ===== Matrix ===== */
.matrix-wrap { display: flex; flex-direction: column; gap: 10px; }
.matrix-head { display: flex; justify-content: space-between; gap: 12px; align-items: center; flex-wrap: wrap; }
.matrix-table-wrap {
  border: 1px solid var(--border-light);
  border-radius: 14px;
  overflow: auto;
  background: var(--surface-base);
  max-height: 560px;
}
.matrix-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.9rem;
}
.matrix-table th, .matrix-table td {
  padding: 10px 12px;
  border-bottom: 1px solid var(--border-light);
  text-align: left;
  white-space: nowrap;
}
.matrix-table thead th {
  position: sticky;
  top: 0;
  z-index: 1;
  background: var(--surface-elevated);
  font-weight: 950;
  color: var(--text-primary);
}
.file-col { max-width: 520px; overflow: hidden; text-overflow: ellipsis; }

.cell-box {
  display: inline-flex;
  padding: 6px 10px;
  border-radius: 12px;
  border: 1px solid var(--border-light);
  background: var(--surface-elevated);
  font-weight: 900;
  color: var(--text-secondary);
}

/* palette in matrix */
.cell-box.primary { background: rgba(56, 189, 248, 0.12); }
.cell-box.company { background: rgba(99, 102, 241, 0.12); }
.cell-box.bg { background: rgba(34, 197, 94, 0.12); }
.cell-box.ledger { background: rgba(251, 146, 60, 0.12); }
.cell-box.le { background: rgba(244, 63, 94, 0.10); }
.cell-box.ou { background: rgba(168, 85, 247, 0.10); }
.cell-box.io { background: rgba(20, 184, 166, 0.10); }

.empty-row { text-align: center; color: var(--text-tertiary); padding: 18px; }

/* Compact mode */
.tree-wrap.compact .node { min-width: 240px; padding: 8px 10px; }
.tree-wrap.compact .node-sub { display: none; }
.matrix-wrap.compact .cell-box { padding: 4px 8px; font-size: 0.85rem; }

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
</style>
