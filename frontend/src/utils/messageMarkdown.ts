/**
 * Turns a chat answer (markdown from the model) into safe HTML plus the data blocks
 * (charts, tables, KPI stats) that the AI panel mounts into placeholder elements.
 *
 * Pipeline: extract fenced data/mermaid blocks -> markdown -> restore blocks ->
 * citation chips -> DOMPurify. Sanitizing last matters: marked passes raw HTML through,
 * and answers quote uploaded files.
 */
import { marked } from 'marked'
import { sanitizeHtml } from '@/utils/sanitize'

export type VizKind = 'chart' | 'table' | 'stats'

export interface VizBlock {
  kind: VizKind
  /** Id of the placeholder element the block is mounted into. */
  id: string
  /** Parsed JSON from the answer; untrusted, validated by the consumer. */
  config: unknown
}

export interface RenderedMessage {
  html: string
  blocks: VizBlock[]
}

const VIZ_FENCES: ReadonlyArray<{ kind: VizKind; pattern: RegExp; label: string }> = [
  { kind: 'chart', pattern: /```(?:chart|chart-data|graph|plot)\s*\n?([\s\S]*?)```/gi, label: 'Chart data' },
  { kind: 'table', pattern: /```(?:table|data-table|datatable)\s*\n?([\s\S]*?)```/gi, label: 'Table data' },
  { kind: 'stats', pattern: /```(?:stats|statistics|kpi|summary-stats)\s*\n?([\s\S]*?)```/gi, label: 'Statistics data' },
]
const MERMAID_FENCE = /```mermaid\s*\n?([\s\S]*?)```/gi
const CITATION = /\[(csv|xml|catalog|note|source):(\d+)\]/gi
const CITATION_TYPES: Record<string, { icon: string; abbr: string; title: string }> = {
  csv: { icon: '📊', abbr: 'csv', title: 'CSV data source' },
  xml: { icon: '📋', abbr: 'xml', title: 'XML source' },
  catalog: { icon: '📚', abbr: 'cat', title: 'Catalog entry' },
  note: { icon: '📝', abbr: 'note', title: 'Note' },
  source: { icon: '📄', abbr: 'src', title: 'Source' },
}
const SLOT_CLASS: Record<VizKind, string> = { chart: 'chart-slot', table: 'table-slot', stats: 'stats-slot' }

export function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function hashString(value: string): string {
  let hash = 0
  for (let i = 0; i < value.length; i++) {
    hash = (hash << 5) - hash + value.charCodeAt(i)
    hash |= 0
  }
  return Math.abs(hash).toString(36)
}

/** Parses model JSON, tolerating smart quotes and trailing commas. */
export function parseJsonLoose(input: string): unknown {
  const normalized = input.trim().replace(/[“”]/g, '"').replace(/[‘’]/g, "'")
  try {
    return JSON.parse(normalized)
  } catch {
    return JSON.parse(normalized.replace(/,\s*([}\]])/g, '$1'))
  }
}

export function renderMessage(content: string, nonce: string): RenderedMessage {
  const placeholders = new Map<string, string>()
  const blocks: VizBlock[] = []
  // HTML comments survive marked.parse(); blank lines make marked treat them as blocks.
  const placeholder = (html: string): string => {
    const token = `blk${placeholders.size}`
    placeholders.set(token, html)
    return `\n\n<!--RETBLK:${token}-->\n\n`
  }
  const stableId = (prefix: string, seed: string, index: number) =>
    `${prefix}-${hashString(`${nonce}:${prefix}:${index}:${seed}`)}`

  let text = content || ''
  for (const { kind, pattern, label } of VIZ_FENCES) {
    text = text.replace(pattern, (_match, json: string, offset: number) => {
      try {
        const config = parseJsonLoose(json)
        const id = stableId(kind, json, offset)
        blocks.push({ kind, id, config })
        return placeholder(`<div id="${id}" class="viz-mount ${SLOT_CLASS[kind]}"></div>`)
      } catch {
        return placeholder(
          `<div class="viz-error"><span aria-hidden="true">⚠</span> ${label} could not be parsed</div>`,
        )
      }
    })
  }
  text = text.replace(MERMAID_FENCE, (_match, diagram: string, offset: number) => {
    const id = stableId('mermaid', diagram, offset)
    return placeholder(
      `<div class="mermaid-diagram" data-mermaid-id="${id}"><pre class="mermaid">${escapeHtml(diagram.trim())}</pre></div>`,
    )
  })

  let html: string
  try {
    html = marked.parse(text, { async: false, breaks: true, gfm: true }) as string
  } catch {
    html = escapeHtml(text).replace(/\n/g, '<br>')
  }
  for (const [token, blockHtml] of placeholders) {
    // marked may wrap a placeholder in <p>; replace either form (function form: no $-patterns).
    html = html
      .replace(new RegExp(`<p>\\s*<!--RETBLK:${token}-->\\s*</p>`, 'g'), () => blockHtml)
      .replace(new RegExp(`<!--RETBLK:${token}-->`, 'g'), () => blockHtml)
  }
  html = html.replace(CITATION, (_match, type: string, num: string) => {
    const key = type.toLowerCase()
    const cfg = CITATION_TYPES[key] ?? CITATION_TYPES.source!
    return (
      `<span class="citation citation-${key}" data-type="${key}" data-num="${num}" title="${cfg.title} #${num}">` +
      `<span class="cit-icon">${cfg.icon}</span><span class="cit-abbr">${cfg.abbr}</span>` +
      `<sup class="cit-num">${num}</sup></span>`
    )
  })
  return { html: sanitizeHtml(html), blocks }
}
