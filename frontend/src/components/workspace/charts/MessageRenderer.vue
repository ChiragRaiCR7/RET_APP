<template>
  <div class="message-renderer" ref="rootEl" v-html="renderedContent"></div>
</template>

<script setup>
import { computed, onMounted, onUpdated, nextTick, ref } from 'vue'
import { marked } from 'marked'
import mermaid from 'mermaid'

const props = defineProps({
  content: {
    type: String,
    required: true
  },
  role: {
    type: String,
    default: 'assistant'
  }
})

const emit = defineEmits(['render-chart', 'render-table', 'render-stats'])

const rootEl = ref(null)
let mermaidInitialized = false
const instanceNonce = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`

const renderedContent = computed(() => {
  let content = props.content || ''
  const blockMap = {}

  // Extract structured blocks BEFORE markdown so fenced blocks are not lost
  content = processDataBlocks(content, blockMap)
  content = processMermaid(content, blockMap)

  // Render markdown text around placeholders
  content = processMarkdown(content)
  content = restoreBlockPlaceholders(content, blockMap)

  // Enhance citations in final html
  content = enhanceCitations(content)

  return content
})

function initMermaid() {
  if (mermaidInitialized) return
  const isDark = document.documentElement.classList.contains('dark') ||
    window.matchMedia('(prefers-color-scheme: dark)').matches

  mermaid.initialize({
    startOnLoad: false,
    theme: isDark ? 'dark' : 'default',
    securityLevel: 'loose'
  })
  mermaidInitialized = true
}

async function renderMermaidDiagrams() {
  await nextTick()
  const el = rootEl.value
  if (!el) return
  const nodes = el.querySelectorAll('.mermaid')
  if (!nodes.length) return
  try {
    await mermaid.run({ nodes })
  } catch {
    // Mermaid rendering is best-effort; ignore errors to avoid breaking chat UI
  }
}

onMounted(() => {
  initMermaid()
  renderMermaidDiagrams()
})

onUpdated(() => {
  renderMermaidDiagrams()
})

function processDataBlocks(content, blockMap) {
  // Extract JSON chart definitions
  const chartRegex = /```(?:chart|chart-data|graph|plot)\s*\n?([\s\S]*?)```/gi
  content = content.replace(chartRegex, (match, jsonContent, offset) => {
    try {
      const chartConfig = parseJsonLoose(jsonContent)
      const id = buildStableId('chart', jsonContent, offset)
      setTimeout(() => emit('render-chart', { id, config: chartConfig }), 0)
      return createBlockPlaceholder(blockMap, `<div id="${id}" class="viz-mount chart-slot"></div>`)
    } catch (e) {
      return createBlockPlaceholder(blockMap, `<div class="viz-error"><span aria-hidden="true">⚠</span> Chart data could not be parsed</div>`)
    }
  })
  
  // Extract table data
  const tableRegex = /```(?:table|data-table|datatable)\s*\n?([\s\S]*?)```/gi
  content = content.replace(tableRegex, (match, jsonContent, offset) => {
    try {
      const tableConfig = parseJsonLoose(jsonContent)
      const id = buildStableId('table', jsonContent, offset)
      setTimeout(() => emit('render-table', { id, config: tableConfig }), 0)
      return createBlockPlaceholder(blockMap, `<div id="${id}" class="viz-mount table-slot"></div>`)
    } catch (e) {
      return createBlockPlaceholder(blockMap, `<div class="viz-error"><span aria-hidden="true">⚠</span> Table data could not be parsed</div>`)
    }
  })
  
  // Extract stats
  const statsRegex = /```(?:stats|statistics|kpi|summary-stats)\s*\n?([\s\S]*?)```/gi
  content = content.replace(statsRegex, (match, jsonContent, offset) => {
    try {
      const statsConfig = parseJsonLoose(jsonContent)
      const id = buildStableId('stats', jsonContent, offset)
      setTimeout(() => emit('render-stats', { id, config: statsConfig }), 0)
      return createBlockPlaceholder(blockMap, `<div id="${id}" class="viz-mount stats-slot"></div>`)
    } catch (e) {
      return createBlockPlaceholder(blockMap, `<div class="viz-error"><span aria-hidden="true">⚠</span> Statistics data could not be parsed</div>`)
    }
  })
  
  return content
}

function processMarkdown(content) {
  // Configure marked
  marked.setOptions({
    async: false,
    breaks: true,
    gfm: true,
    tables: true
  })
  
  try {
    return marked.parse(content)
  } catch (e) {
    return escapeHtml(content).replace(/\n/g, '<br>')
  }
}

function enhanceCitations(content) {
  const citTypes = {
    csv:     { icon: '📊', abbr: 'csv',  title: 'CSV data source' },
    xml:     { icon: '📋', abbr: 'xml',  title: 'XML source' },
    catalog: { icon: '📚', abbr: 'cat',  title: 'Catalog entry' },
    note:    { icon: '📝', abbr: 'note', title: 'Note' },
    source:  { icon: '📄', abbr: 'src',  title: 'Source' }
  }
  return content.replace(/\[(csv|xml|catalog|note|source):(\d+)\]/gi, (match, type, num) => {
    const cfg = citTypes[type.toLowerCase()] || citTypes.source
    return `<span class="citation citation-${type.toLowerCase()}" data-type="${type}" data-num="${num}" title="${cfg.title} #${num}">` +
      `<span class="cit-icon">${cfg.icon}</span>` +
      `<span class="cit-abbr">${cfg.abbr}</span>` +
      `<sup class="cit-num">${num}</sup>` +
      `</span>`
  })
}

function processMermaid(content, blockMap) {
  // Mark mermaid blocks for rendering
  const mermaidRegex = /```mermaid\s*\n?([\s\S]*?)```/gi
  return content.replace(mermaidRegex, (match, diagram, offset) => {
    const id = buildStableId('mermaid', diagram, offset)
    return createBlockPlaceholder(blockMap, `<div class="mermaid-diagram" data-mermaid-id="${id}">
      <pre class="mermaid">${escapeHtml((diagram || '').trim())}</pre>
    </div>`)
  })
}

function restoreBlockPlaceholders(content, blockMap) {
  let html = content
  for (const [token, blockHtml] of Object.entries(blockMap)) {
    // Handle both plain comment and marked-wrapped <p>comment</p> variants
    const escaped = token.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    html = html.replace(new RegExp(`<p>\\s*<!--RETBLK:${escaped}-->\\s*<\/p>`, 'g'), blockHtml)
    html = html.replace(new RegExp(`<!--RETBLK:${escaped}-->`, 'g'), blockHtml)
  }
  return html
}

function createBlockPlaceholder(blockMap, html) {
  // HTML comments survive marked.parse() unlike custom HTML tags
  // Surrounding newlines ensure marked treats the comment as a block (not inline)
  const token = `blk${Object.keys(blockMap).length}`
  blockMap[token] = html
  return `\n\n<!--RETBLK:${token}-->\n\n`
}

function buildStableId(prefix, seed, index) {
  return `${prefix}-${hashString(`${instanceNonce}:${prefix}:${index}:${seed || ''}`)}`
}

function hashString(value) {
  let hash = 0
  for (let i = 0; i < value.length; i++) {
    hash = ((hash << 5) - hash) + value.charCodeAt(i)
    hash |= 0
  }
  return Math.abs(hash).toString(36)
}

function parseJsonLoose(input) {
  if (typeof input !== 'string') {
    throw new Error('Expected JSON string')
  }

  const normalized = input
    .trim()
    .replace(/[“”]/g, '"')
    .replace(/[‘’]/g, "'")

  try {
    return JSON.parse(normalized)
  } catch {
    // Try common LLM issue: trailing commas before } or ]
    const noTrailingCommas = normalized.replace(/,\s*([}\]])/g, '$1')
    return JSON.parse(noTrailingCommas)
  }
}

function escapeHtml(text) {
  const div = document.createElement('div')
  div.textContent = text
  return div.innerHTML
}
</script>

<style scoped>
.message-renderer {
  line-height: var(--leading-relaxed, 1.7);
  color: var(--text-body);
}

.message-renderer :deep(h1),
.message-renderer :deep(h2),
.message-renderer :deep(h3),
.message-renderer :deep(h4) {
  color: var(--text-heading);
  margin-top: 1.5em;
  margin-bottom: 0.6em;
  font-weight: 700;
  font-family: var(--font-display);
}

.message-renderer :deep(h1) { font-size: 1.55em; border-bottom: 2px solid var(--brand-primary); padding-bottom: 0.3em; }
.message-renderer :deep(h2) { font-size: 1.35em; }
.message-renderer :deep(h3) { font-size: 1.15em; color: var(--text-secondary); }
.message-renderer :deep(h4) { font-size: 1.05em; color: var(--text-secondary); }

.message-renderer :deep(p) {
  margin: 0.85em 0;
}

.message-renderer :deep(ul),
.message-renderer :deep(ol) {
  margin: 0.85em 0;
  padding-left: 1.75em;
}

.message-renderer :deep(li) {
  margin: 0.4em 0;
}

.message-renderer :deep(strong) {
  color: var(--text-heading);
  font-weight: 700;
}

.message-renderer :deep(code) {
  background: var(--brand-subtle);
  padding: 0.15em 0.4em;
  border-radius: var(--radius-sm, 6px);
  font-family: var(--font-mono);
  font-size: 0.88em;
  color: var(--brand-secondary);
  border: 1px solid var(--brand-subtle);
}

.message-renderer :deep(pre) {
  background: var(--chat-code-block-bg, #0f172a);
  padding: 1em 1.25em;
  border-radius: var(--radius-md, 10px);
  overflow-x: auto;
  margin: 1.25em 0;
  border: 1px solid var(--border-medium);
}

.message-renderer :deep(pre code) {
  background: none;
  padding: 0;
  color: #c2410c;
  font-size: 0.9em;
}

.message-renderer :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 1.25em 0;
  border: 1px solid var(--border-medium);
  border-radius: var(--radius-md, 10px);
  overflow: hidden;
}

.message-renderer :deep(thead) {
  background: var(--surface-active);
}

.message-renderer :deep(th) {
  padding: 0.65em 1em;
  text-align: left;
  font-weight: 700;
  font-size: var(--text-sm);
  color: var(--text-heading);
  border-bottom: 2px solid var(--brand-primary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.message-renderer :deep(td) {
  padding: 0.6em 1em;
  border-bottom: 1px solid var(--border-light);
  font-size: var(--text-sm);
  color: var(--text-body);
}

.message-renderer :deep(tr:hover td) {
  background: var(--brand-subtle-2);
}

.message-renderer :deep(blockquote) {
  border-left: 4px solid var(--brand-primary);
  padding: 0.5em 1em;
  margin: 1.25em 0;
  background: var(--brand-subtle-2);
  border-radius: 0 var(--radius-sm, 6px) var(--radius-sm, 6px) 0;
  color: var(--text-secondary);
  font-style: italic;
}

.message-renderer :deep(a) {
  color: var(--link);
  text-decoration: none;
  transition: color var(--transition-fast, 150ms);
}

.message-renderer :deep(a:hover) {
  color: var(--brand-primary);
  text-decoration: underline;
}

/* ── Citations ─────────────────────────────────────────── */
.message-renderer :deep(.citation) {
  display: inline-flex;
  align-items: center;
  gap: 0.2em;
  padding: 0.1em 0.45em 0.1em 0.35em;
  border-radius: var(--radius-full, 9999px);
  font-size: 0.8em;
  font-weight: 600;
  cursor: default;
  vertical-align: baseline;
  margin: 0 0.15em;
  white-space: nowrap;
  transition: filter var(--transition-fast, 150ms);
  /* type-specific colors via modifier classes below */
}

.message-renderer :deep(.citation:hover) {
  filter: brightness(1.08);
}

.message-renderer :deep(.citation-csv) {
  background: rgba(76, 175, 80, 0.14);
  border: 1px solid rgba(76, 175, 80, 0.35);
  color: #2e7d32;
}
.message-renderer :deep(.citation-xml) {
  background: rgba(33, 150, 243, 0.12);
  border: 1px solid rgba(33, 150, 243, 0.3);
  color: #1565c0;
}
.message-renderer :deep(.citation-catalog) {
  background: rgba(156, 39, 176, 0.12);
  border: 1px solid rgba(156, 39, 176, 0.3);
  color: #6a1b9a;
}
.message-renderer :deep(.citation-note) {
  background: rgba(255, 152, 0, 0.12);
  border: 1px solid rgba(255, 152, 0, 0.3);
  color: #e65100;
}
.message-renderer :deep(.citation-source) {
  background: var(--brand-subtle);
  border: 1px solid rgba(255, 192, 0, 0.3);
  color: var(--brand-secondary);
}

.message-renderer :deep(.cit-icon) {
  font-size: 0.95em;
  line-height: 1;
}
.message-renderer :deep(.cit-abbr) {
  font-variant: small-caps;
  letter-spacing: 0.04em;
}
.message-renderer :deep(.cit-num) {
  font-variant-numeric: tabular-nums;
  font-size: 0.85em;
}

/* ── Visualization mount containers ─────────────────────── */
/* These are injected via v-html — must use :deep() to receive styles */

.message-renderer :deep(.viz-mount) {
  margin: 1rem 0;
  min-height: 0; /* collapse if never mounted */
}

.message-renderer :deep(.viz-error) {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.65rem 1rem;
  background: var(--error-bg);
  border: 1px solid var(--error-border);
  border-radius: var(--radius-sm, 6px);
  color: var(--error);
  font-size: var(--text-sm);
  margin: 0.75rem 0;
}

.message-renderer :deep(.error-block) {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.65rem 1rem;
  background: var(--error-bg);
  border: 1px solid var(--error-border);
  border-radius: var(--radius-sm, 6px);
  color: var(--error);
  font-size: var(--text-sm);
  margin: 0.75rem 0;
}

.message-renderer :deep(.mermaid-diagram) {
  margin: 1.25rem 0;
  background: var(--surface-elevated);
  padding: 1.25rem;
  border-radius: var(--radius-md, 10px);
  border: 1px solid var(--border-light);
  overflow-x: auto;
}

@media (prefers-color-scheme: dark) {
  .message-renderer :deep(.citation-csv)    { color: #66bb6a; }
  .message-renderer :deep(.citation-xml)    { color: #64b5f6; }
  .message-renderer :deep(.citation-catalog){ color: #ce93d8; }
  .message-renderer :deep(.citation-note)   { color: #ffcc80; }
  .message-renderer :deep(.citation-source) { color: var(--brand-primary); }
}
</style>
