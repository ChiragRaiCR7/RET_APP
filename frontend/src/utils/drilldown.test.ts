import { describe, expect, it } from 'vitest'
import { cellHasChange, changeSideClass, ignoredColumnFilter, toDrilldownView, truncateCell } from './drilldown'

const isIgnored = ignoredColumnFilter()

describe('drilldown', () => {
  const data = {
    header: ['ID', 'Name', 'Last Update Date'],
    stats: { modified: 1, added: 1, removed: 0 },
    truncated: false,
    row_count_A: 3,
    row_count_B: 4,
    deltaA: { headers: [], rows: [{ _kind_: 'MODIFIED', _changed_cols_: [1, 2, 99], Name: 'a' }] },
    deltaB: { headers: [], rows: [{ _kind_: 'ADDED', ID: '9', Name: 'new', 'Last Update Date': 'x' }] },
  }

  it('collects changed columns, skipping WHO columns and out-of-range indexes', () => {
    const { view, changedColumns } = toDrilldownView(data, isIgnored)
    expect([...changedColumns].sort()).toEqual(['ID', 'Name'])
    expect(view).toMatchObject({ sizeA: 3, sizeB: 4, modified: 1, added: 1, columns: data.header })
  })

  it('ignores WHO columns regardless of case and spacing', () => {
    expect(isIgnored('  last   UPDATE date ')).toBe(true)
    expect(isIgnored('Name')).toBe(false)
  })

  it('classifies cells by change kind and side', () => {
    const modified = data.deltaA.rows[0]!
    expect(cellHasChange(modified, 'Name', data.header, isIgnored)).toBe(true)
    expect(cellHasChange(modified, 'ID', data.header, isIgnored)).toBe(false)
    expect(cellHasChange(modified, 'Last Update Date', data.header, isIgnored)).toBe(false)
    expect(changeSideClass(modified, 'A')).toBe('cell-old')
    expect(changeSideClass(modified, 'B')).toBe('cell-new')
    expect(changeSideClass({ _kind_: 'REMOVED' }, 'B')).toBe('cell-old')
  })

  it('truncates long values', () => {
    expect(truncateCell('abcdef', 3)).toBe('abc…')
    expect(truncateCell(null, 3)).toBe('')
  })
})
