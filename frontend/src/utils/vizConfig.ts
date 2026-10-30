/**
 * Normalizes the loosely shaped visualization JSON that models put in answers into the
 * props the chart, table and KPI components expect. Input is untrusted: anything that
 * cannot be shaped is reported as null so the caller can show an error in the slot.
 */
import type { ChartConfig } from '@/components/workspace/charts/ChartRenderer.vue'
import type { TableColumn } from '@/components/workspace/charts/DataTable.vue'
import type { StatCard } from '@/components/workspace/charts/StatsCardGrid.vue'

type Plain = Record<string, unknown>

export interface TableProps {
  data: Plain[]
  columns: TableColumn[]
  title: string | null
  sortable: boolean
  exportable: boolean
  showSummary: boolean
  summary: Plain | null
  maxRows: number
  tableClass: string
}

const DEFAULT_TABLE_ROWS = 15
const STATS_META_KEYS = ['title', 'description', 'subtitle']

function isPlain(value: unknown): value is Plain {
  return !!value && typeof value === 'object' && !Array.isArray(value)
}

export function toChartConfig(raw: unknown): ChartConfig | null {
  return isPlain(raw) && raw.type && isPlain(raw.data) ? (raw as unknown as ChartConfig) : null
}

function normalizeColumns(columns: unknown[]): TableColumn[] {
  return columns.map((c, idx) => {
    if (typeof c === 'string') return { key: c, label: c }
    if (isPlain(c)) {
      const key = String(c.key || c.label || `col_${idx + 1}`)
      return { key, label: String(c.label || c.key || `Column ${idx + 1}`) }
    }
    return { key: `col_${idx + 1}`, label: `Column ${idx + 1}` }
  })
}

/** Accepts {columns?, data|rows} with row arrays, row objects or primitives, or a bare array. */
export function toTableProps(raw: unknown): TableProps | null {
  let cfg: unknown = Array.isArray(raw) ? { data: raw } : raw
  if (typeof cfg === 'string') {
    try {
      cfg = JSON.parse(cfg)
    } catch {
      return null
    }
  }
  if (!isPlain(cfg)) return null

  const columns = Array.isArray(cfg.columns) ? cfg.columns : []
  const rows: unknown[] = Array.isArray(cfg.data) ? cfg.data : Array.isArray(cfg.rows) ? cfg.rows : []
  if (!rows.length) return null

  let data: Plain[]
  let cols: TableColumn[]
  const first = rows[0]
  if (Array.isArray(first)) {
    cols = columns.length
      ? normalizeColumns(columns)
      : first.map((_, idx) => ({ key: `col_${idx + 1}`, label: `Column ${idx + 1}` }))
    data = rows.map((r) => {
      const values = Array.isArray(r) ? r : []
      return Object.fromEntries(cols.map((c, i) => [c.key, values[i]]))
    })
  } else if (isPlain(first)) {
    cols = columns.length ? normalizeColumns(columns) : Object.keys(first).map((k) => ({ key: k, label: k }))
    data = rows.filter(isPlain)
  } else {
    cols = [{ key: 'value', label: 'Value' }]
    data = rows.map((value) => ({ value }))
  }

  return {
    data,
    columns: cols,
    title: typeof cfg.title === 'string' ? cfg.title : null,
    sortable: cfg.sortable !== false,
    exportable: cfg.exportable !== false,
    showSummary: cfg.showSummary === true,
    summary: isPlain(cfg.summary) ? cfg.summary : null,
    maxRows: typeof cfg.maxRows === 'number' && cfg.maxRows > 0 ? cfg.maxRows : DEFAULT_TABLE_ROWS,
    tableClass: typeof cfg.tableClass === 'string' ? cfg.tableClass : '',
  }
}

/** Accepts {stats: [...]}, {cards: [...]} or a flat {"Label": value} object. */
export function toStatCards(raw: unknown): StatCard[] | null {
  if (!isPlain(raw)) return null
  let stats: unknown[] | null = null
  if (Array.isArray(raw.stats)) stats = raw.stats
  else if (Array.isArray(raw.cards)) stats = raw.cards
  else {
    stats = Object.entries(raw)
      .filter(([k]) => !STATS_META_KEYS.includes(k.toLowerCase()))
      .map(([label, value]) => ({ label, value: value == null ? '—' : String(value) }))
  }
  const cards = stats.filter(isPlain).map((s) => s as unknown as StatCard)
  return cards.length ? cards : null
}
