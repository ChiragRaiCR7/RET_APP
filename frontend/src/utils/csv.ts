/**
 * CSV building for downloads. Cell values come from uploaded files and model answers,
 * so a value that starts like a spreadsheet formula is neutralized: Excel and Sheets
 * would otherwise evaluate `=HYPERLINK(...)` or `=cmd|...` when the file is opened.
 */

const FORMULA_START = /^[=+\-@\t\r]/

export function csvCell(value: unknown): string {
  let text = value == null ? '' : String(value)
  if (FORMULA_START.test(text)) text = `'${text}`
  return `"${text.replace(/"/g, '""')}"`
}

export function toCsv(headers: readonly unknown[], rows: readonly (readonly unknown[])[]): string {
  return [headers, ...rows].map((row) => row.map(csvCell).join(',')).join('\n')
}

/** Starts a browser download of `content` as a CSV file. */
export function downloadCsv(filename: string, content: string): void {
  const url = URL.createObjectURL(new Blob([content], { type: 'text/csv;charset=utf-8;' }))
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}
