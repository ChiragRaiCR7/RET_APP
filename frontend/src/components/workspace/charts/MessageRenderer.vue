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
      return createBlockPlaceholder(blockMap, `<div id="${id}" class="chart-placeholder">Loading chart...</div>`)
    } catch (e) {
      return `<div class="error-block">Invalid chart definition</div>`
    }
  })
  
  // Extract table data
  const tableRegex = /```(?:table|data-table|datatable)\s*\n?([\s\S]*?)```/gi
  content = content.replace(tableRegex, (match, jsonContent, offset) => {
    try {
      const tableConfig = parseJsonLoose(jsonContent)
      const id = buildStableId('table', jsonContent, offset)
      setTimeout(() => emit('render-table', { id, config: tableConfig }), 0)
      return createBlockPlaceholder(blockMap, `<div id="${id}" class="table-placeholder">Loading table...</div>`)
    } catch (e) {
      return `<div class="error-block">Invalid table definition</div>`
    }
  })
  
  // Extract stats
  const statsRegex = /```(?:stats|statistics|kpi|summary-stats)\s*\n?([\s\S]*?)```/gi
  content = content.replace(statsRegex, (match, jsonContent, offset) => {
    try {
      const statsConfig = parseJsonLoose(jsonContent)
      const id = buildStableId('stats', jsonContent, offset)
      setTimeout(() => emit('render-stats', { id, config: statsConfig }), 0)
      return createBlockPlaceholder(blockMap, `<div id="${id}" class="stats-placeholder">Loading statistics...</div>`)
    } catch (e) {
      return `<div class="error-block">Invalid stats definition</div>`
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
  // Enhanced citation rendering with better styling
  return content.replace(/\[source:(\d+)\]/gi, (match, num) => {
    return `<span class="citation" data-source="${num}" title="Click to view source">
      <span class="citation-icon">📄</span>
      <span class="citation-number">${num}</span>
    </span>`
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
    html = html.replaceAll(`<ret-block data-token="${token}"></ret-block>`, blockHtml)
  }
  return html
}

function createBlockPlaceholder(blockMap, html) {
  const token = `block_${Object.keys(blockMap).length}`
  blockMap[token] = html
  return `<ret-block data-token="${token}"></ret-block>`
}

function buildStableId(prefix, seed, index) {
  return `${prefix}-${hashString(`${prefix}:${index}:${seed || ''}`)}`
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
  line-height: 1.6;
  color: var(--text-secondary, #e0e0e0);
}

.message-renderer :deep(h1),
.message-renderer :deep(h2),
.message-renderer :deep(h3),
.message-renderer :deep(h4) {
  color: var(--text-primary, #fff);
  margin-top: 1.5em;
  margin-bottom: 0.75em;
  font-weight: 600;
}

.message-renderer :deep(h1) { font-size: 1.75em; border-bottom: 2px solid #FFC000; padding-bottom: 0.3em; }
.message-renderer :deep(h2) { font-size: 1.5em; }
.message-renderer :deep(h3) { font-size: 1.25em; }
.message-renderer :deep(h4) { font-size: 1.1em; }

.message-renderer :deep(p) {
  margin: 1em 0;
}

.message-renderer :deep(ul),
.message-renderer :deep(ol) {
  margin: 1em 0;
  padding-left: 2em;
}

.message-renderer :deep(li) {
  margin: 0.5em 0;
}

.message-renderer :deep(code) {
  background: var(--bg-code, rgba(255, 192, 0, 0.1));
  padding: 0.2em 0.4em;
  border-radius: 3px;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 0.9em;
  color: #FFC000;
}

.message-renderer :deep(pre) {
  background: var(--bg-code-block, #1a1a2e);
  padding: 1em;
  border-radius: 8px;
  overflow-x: auto;
  margin: 1.5em 0;
  border: 1px solid var(--border-color, #3a3a4e);
}

.message-renderer :deep(pre code) {
  background: none;
  padding: 0;
  color: #e0e0e0;
}

.message-renderer :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 1.5em 0;
  border: 1px solid var(--border-color, #3a3a4e);
  border-radius: 8px;
  overflow: hidden;
}

.message-renderer :deep(thead) {
  background: var(--bg-panel, #1a1a2e);
}

.message-renderer :deep(th) {
  padding: 0.75em 1em;
  text-align: left;
  font-weight: 600;
  color: var(--text-primary, #fff);
  border-bottom: 2px solid #FFC000;
}

.message-renderer :deep(td) {
  padding: 0.75em 1em;
  border-bottom: 1px solid var(--border-color, #3a3a4e);
}

.message-renderer :deep(tr:hover) {
  background: var(--bg-hover, rgba(255, 192, 0, 0.05));
}

.message-renderer :deep(blockquote) {
  border-left: 4px solid #FFC000;
  padding-left: 1em;
  margin: 1.5em 0;
  color: var(--text-secondary, #b0b0b0);
  font-style: italic;
}

.message-renderer :deep(a) {
  color: #66B5F5;
  text-decoration: none;
  transition: color 0.2s;
}

.message-renderer :deep(a:hover) {
  color: #FFC000;
  text-decoration: underline;
}

.message-renderer :deep(.citation) {
  display: inline-flex;
  align-items: center;
  gap: 0.25em;
  padding: 0.2em 0.5em;
  background: rgba(255, 192, 0, 0.15);
  border: 1px solid rgba(255, 192, 0, 0.3);
  border-radius: 12px;
  font-size: 0.85em;
  font-weight: 600;
  color: #FFC000;
  cursor: pointer;
  transition: all 0.2s;
  margin: 0 0.2em;
}

.message-renderer :deep(.citation:hover) {
  background: rgba(255, 192, 0, 0.25);
  border-color: #FFC000;
  transform: translateY(-1px);
}

.message-renderer :deep(.citation-icon) {
  font-size: 1.1em;
}

.message-renderer :deep(.citation-number) {
  font-variant-numeric: tabular-nums;
}

.chart-placeholder,
.table-placeholder,
.stats-placeholder {
  padding: 2rem;
  text-align: center;
  background: var(--bg-elevated, #2a2a3e);
  border-radius: 8px;
  margin: 1.5rem 0;
  color: var(--text-secondary, #b0b0b0);
}

.error-block {
  padding: 1rem;
  background: rgba(244, 67, 54, 0.1);
  border: 1px solid rgba(244, 67, 54, 0.3);
  border-radius: 6px;
  color: #F44336;
  margin: 1rem 0;
}

.mermaid-diagram {
  margin: 1.5rem 0;
  background: var(--bg-elevated, #2a2a3e);
  padding: 1.5rem;
  border-radius: 12px;
  border: 1px solid var(--border-color, #3a3a4e);
}
</style>
