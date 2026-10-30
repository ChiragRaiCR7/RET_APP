<template>
  <div class="message-renderer" ref="rootEl" v-html="renderedContent"></div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useTheme } from '@/composable/useTheme'
import { configureMermaid } from '@/utils/mermaid'
import { renderMessage, type VizBlock } from '@/utils/messageMarkdown'

const props = withDefaults(defineProps<{ content: string; role?: string }>(), { role: 'assistant' })

const emit = defineEmits<{
  'render-chart': [payload: { id: string; config: unknown }]
  'render-table': [payload: { id: string; config: unknown }]
  'render-stats': [payload: { id: string; config: unknown }]
}>()

const rootEl = ref<HTMLElement | null>(null)
const { theme } = useTheme()
// Per-instance nonce keeps block ids unique across messages with identical content.
const nonce = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`

const rendered = computed(() => renderMessage(props.content || '', nonce))
const renderedContent = computed(() => rendered.value.html)

function emitBlock(block: VizBlock) {
  const payload = { id: block.id, config: block.config }
  if (block.kind === 'chart') emit('render-chart', payload)
  else if (block.kind === 'table') emit('render-table', payload)
  else emit('render-stats', payload)
}

async function renderMermaidDiagrams() {
  const nodes = rootEl.value?.querySelectorAll<HTMLElement>('.mermaid')
  if (!nodes?.length) return
  try {
    await configureMermaid(theme.value === 'dark').run({ nodes: Array.from(nodes) })
  } catch {
    // Diagram rendering is best-effort; a bad diagram must not break the chat.
  }
}

// v-html replaces the DOM on every update, which drops mounted charts and rendered
// diagrams; re-announce blocks and re-render diagrams after each DOM update.
watch(
  rendered,
  async (value) => {
    await nextTick()
    value.blocks.forEach(emitBlock)
    await renderMermaidDiagrams()
  },
  { immediate: true, flush: 'post' }
)
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
