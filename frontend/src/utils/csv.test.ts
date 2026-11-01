import { describe, expect, it } from 'vitest'
import { csvCell, toCsv } from './csv'

describe('csv', () => {
  it('quotes cells and doubles embedded quotes', () => {
    expect(csvCell('say "hi", ok')).toBe('"say ""hi"", ok"')
    expect(csvCell(null)).toBe('""')
    expect(csvCell(42)).toBe('"42"')
  })

  it('neutralizes values a spreadsheet would run as formulas', () => {
    for (const payload of ['=HYPERLINK("http://x","y")', '+1+1', '-2+3', '@SUM(A1)', '\t=1', '\r=1']) {
      expect(csvCell(payload).startsWith(`"'`)).toBe(true)
    }
    expect(csvCell('plain text')).toBe('"plain text"')
  })

  it('builds header plus rows', () => {
    expect(toCsv(['a', 'b'], [[1, '=2']])).toBe('"a","b"\n"1","\'=2"')
  })
})
