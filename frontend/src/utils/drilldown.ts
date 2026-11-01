/**
 * Shared logic for comparison drilldowns (the modal in ComparisonPanel and the full-page
 * ComparisonDrilldownView): shaping the API response, finding changed columns, and
 * classifying cells. Kept in one place so the two views cannot drift apart again.
 */
import type { DeltaRow, DrilldownResponse } from '@/types/api'

/** Oracle "WHO" audit columns: they change on every save and hide the real differences. */
export const WHO_COLUMNS: readonly string[] = [
  'Created By',
  'Last Updated By',
  'Creation Date',
  'Last Update Date',
  'Last Update Login',
]

export type Side = 'A' | 'B'
export type ColumnFilter = (column: string) => boolean

export interface DrilldownView {
  sizeA: number
  sizeB: number
  modified: number
  added: number
  removed: number
  columns: string[]
  deltaA: DeltaRow[]
  deltaB: DeltaRow[]
  truncated: boolean
}

export function normalizeColName(name: unknown): string {
  return String(name || '').trim().toLowerCase().replace(/\s+/g, ' ')
}

/** Returns a predicate that is true for columns to ignore (case and spacing insensitive). */
export function ignoredColumnFilter(columns: readonly string[] = WHO_COLUMNS): ColumnFilter {
  const set = new Set(columns.map(normalizeColName))
  return (column) => set.has(normalizeColName(column))
}

function rowKind(row: DeltaRow | null | undefined): string {
  return String(row?._kind_ || '').toUpperCase()
}

/** Shapes a drilldown response and collects the non-ignored columns that changed. */
export function toDrilldownView(
  data: DrilldownResponse,
  isIgnored: ColumnFilter,
): { view: DrilldownView; changedColumns: Set<string> } {
  const header = data.header || []
  const deltaA = data.deltaA?.rows || []
  const deltaB = data.deltaB?.rows || []
  const stats = data.stats || {}
  const changedColumns = new Set<string>()

  for (const row of [...deltaA, ...deltaB]) {
    for (const c of row._changed_cols_ || []) {
      const name = typeof c === 'number' ? header[c] : c
      // An out-of-range index has no column name; skip it rather than storing the number.
      if (name && !isIgnored(name)) changedColumns.add(name)
    }
    const kind = rowKind(row)
    if (kind === 'ADDED' || kind === 'REMOVED') {
      for (const h of header) if (!isIgnored(h)) changedColumns.add(h)
    }
  }

  return {
    view: {
      sizeA: data.row_count_A || 0,
      sizeB: data.row_count_B || 0,
      modified: stats.modified || 0,
      added: stats.added || 0,
      removed: stats.removed || 0,
      columns: header,
      deltaA,
      deltaB,
      truncated: !!data.truncated,
    },
    changedColumns,
  }
}

export function cellHasChange(
  row: DeltaRow,
  column: string,
  columns: readonly string[],
  isIgnored: ColumnFilter,
): boolean {
  if (isIgnored(column)) return false
  const kind = rowKind(row)
  if (kind === 'ADDED' || kind === 'REMOVED') {
    const v = row?.[column]
    return v !== null && v !== undefined && String(v).trim() !== ''
  }
  const changed = row?._changed_cols_ || []
  const idx = columns.indexOf(column)
  return (idx >= 0 && changed.includes(idx)) || changed.includes(column)
}

/** 'cell-old' for values on the A side of a change, 'cell-new' for the B side. */
export function changeSideClass(row: DeltaRow, side: Side): 'cell-old' | 'cell-new' {
  const kind = rowKind(row)
  if (kind === 'REMOVED') return 'cell-old'
  if (kind === 'ADDED') return 'cell-new'
  return side === 'A' ? 'cell-old' : 'cell-new'
}

export function truncateCell(value: unknown, maxLen: number): string {
  if (value === null || value === undefined) return ''
  const s = String(value)
  return s.length > maxLen ? `${s.slice(0, maxLen)}…` : s
}
