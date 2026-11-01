// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'
import { sanitizeHtml } from './sanitize'

describe('sanitizeHtml', () => {
  it('removes script, event handlers and javascript: URLs from chat answers', () => {
    const dirty =
      '<p>Total <img src=x onerror="window.pwned=1"> rows</p>' +
      '<script>window.pwned=1</script>' +
      '<a href="javascript:alert(1)">open</a>' +
      '<svg><animate onbegin="alert(1)"/></svg>'
    const clean = sanitizeHtml(dirty)
    expect(clean).not.toMatch(/onerror|onbegin|<script|javascript:/i)
    expect(clean).toContain('Total')
  })

  it('keeps the structural markup the message renderer emits', () => {
    const citation =
      '<span class="citation citation-csv" data-type="csv" data-num="2" title="CSV data source #2">' +
      '<span class="cit-icon">📊</span><sup class="cit-num">2</sup></span>'
    const mount = '<div id="chart-abc" class="viz-mount chart-slot"></div>'
    const diagram = '<div class="mermaid-diagram" data-mermaid-id="m1"><pre class="mermaid">graph TD; A--&gt;B</pre></div>'
    expect(sanitizeHtml(citation)).toBe(citation)
    expect(sanitizeHtml(mount)).toBe(mount)
    expect(sanitizeHtml(diagram)).toBe(diagram)
  })

  it('supports a stricter allowlist', () => {
    const clean = sanitizeHtml('<p class="x"><b>ok</b><a href="https://x.example">link</a></p>', {
      ALLOWED_TAGS: ['p', 'b'],
      ALLOWED_ATTR: [],
    })
    expect(clean).toBe('<p><b>ok</b>link</p>')
  })
})
