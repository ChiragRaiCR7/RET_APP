import { describe, expect, it } from 'vitest'
import { toChartConfig, toStatCards, toTableProps } from './vizConfig'

describe('toTableProps', () => {
  it('maps array rows onto declared or generated columns', () => {
    const t = toTableProps({ columns: ['a', { key: 'b', label: 'B' }], data: [[1, 2], [3, 4]], title: 'T' })!
    expect(t.columns).toEqual([{ key: 'a', label: 'a' }, { key: 'b', label: 'B' }])
    expect(t.data).toEqual([{ a: 1, b: 2 }, { a: 3, b: 4 }])
    expect(t.title).toBe('T')
    expect(toTableProps([[1, 2]])!.columns.map((c) => c.key)).toEqual(['col_1', 'col_2'])
  })

  it('keeps object rows, wraps primitives, and defaults options', () => {
    const objects = toTableProps({ rows: [{ x: 1, y: 2 }] })!
    expect(objects.columns.map((c) => c.key)).toEqual(['x', 'y'])
    expect(objects).toMatchObject({ sortable: true, exportable: true, showSummary: false, maxRows: 15 })
    expect(toTableProps({ data: ['p', 'q'] })!.data).toEqual([{ value: 'p' }, { value: 'q' }])
  })

  it('rejects empty or unusable input', () => {
    expect(toTableProps(null)).toBeNull()
    expect(toTableProps({ data: [] })).toBeNull()
    expect(toTableProps('not json')).toBeNull()
    expect(toTableProps(42)).toBeNull()
  })
})

describe('toStatCards', () => {
  it('accepts stats, cards, or a flat object without its meta keys', () => {
    expect(toStatCards({ stats: [{ label: 'Rows', value: 3 }] })).toEqual([{ label: 'Rows', value: 3 }])
    expect(toStatCards({ cards: [{ label: 'A', value: 1 }] })).toHaveLength(1)
    expect(toStatCards({ title: 'x', 'Distinct Fields': 80, Empty: null })).toEqual([
      { label: 'Distinct Fields', value: '80' },
      { label: 'Empty', value: '—' },
    ])
    expect(toStatCards({ title: 'only meta' })).toBeNull()
    expect(toStatCards([1, 2])).toBeNull()
  })
})

describe('toChartConfig', () => {
  it('requires a type and a data object', () => {
    expect(toChartConfig({ type: 'bar', data: { labels: [] } })).not.toBeNull()
    expect(toChartConfig({ type: 'bar' })).toBeNull()
    expect(toChartConfig('bar')).toBeNull()
  })
})
