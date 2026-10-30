// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'
import { renderMessage } from './messageMarkdown'

describe('renderMessage', () => {
  it('renders markdown and strips HTML injected through quoted file content', () => {
    const { html } = renderMessage('**Total**: 3\n\n<img src=x onerror="alert(1)"><script>x()</script>', 'n')
    expect(html).toContain('<strong>Total</strong>')
    expect(html).not.toMatch(/onerror|<script/)
  })

  it('extracts chart, table and stats blocks into stable placeholders', () => {
    const answer = [
      'Intro',
      '```chart\n{"type":"bar","data":{"labels":["a"],"datasets":[{"data":[1]}]},}\n```',
      '```table\n[{"a":1}]\n```',
      '```kpi\n{"Rows": 10}\n```',
    ].join('\n\n')
    const first = renderMessage(answer, 'nonce')
    expect(first.blocks.map((b) => b.kind)).toEqual(['chart', 'table', 'stats'])
    expect(first.blocks[0]!.config).toMatchObject({ type: 'bar' }) // trailing comma tolerated
    for (const block of first.blocks) expect(first.html).toContain(`id="${block.id}"`)
    // Same content and nonce -> same ids, so re-renders remount into the same slots.
    expect(renderMessage(answer, 'nonce').blocks.map((b) => b.id)).toEqual(first.blocks.map((b) => b.id))
  })

  it('reports unparseable blocks instead of dropping them', () => {
    const { html, blocks } = renderMessage('```chart\nnot json\n```', 'n')
    expect(blocks).toEqual([])
    expect(html).toContain('Chart data could not be parsed')
  })

  it('escapes mermaid source and keeps $-sequences literal', () => {
    const { html } = renderMessage('```mermaid\ngraph TD; A["$& <b>x</b>"]-->B\n```', 'n')
    expect(html).toContain('<pre class="mermaid">')
    expect(html).toContain('$&amp;')
    expect(html).not.toContain('<b>x</b>')
  })

  it('turns citations into chips', () => {
    const { html } = renderMessage('See [csv:2] and [XML:1].', 'n')
    expect(html).toContain('class="citation citation-csv" data-type="csv" data-num="2"')
    expect(html).toContain('citation-xml')
  })
})
