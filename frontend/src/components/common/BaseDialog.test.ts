import { createApp, h, nextTick, ref } from 'vue'
import { afterEach, describe, expect, it } from 'vitest'
import BaseDialog from './BaseDialog.vue'

let unmount: () => void = () => {}
afterEach(() => unmount())

function render(initiallyOpen: boolean) {
  const open = ref(initiallyOpen)
  const closes = ref(0)
  const host = document.createElement('div')
  document.body.append(host)
  const app = createApp({
    render: () => h(BaseDialog, { open: open.value, onClose: () => closes.value++ }, () => h('p', { class: 'body' }, 'hi')),
  })
  app.mount(host)
  unmount = () => { app.unmount(); host.remove() }
  return { open, closes, dialog: host.querySelector('dialog') as HTMLDialogElement }
}

describe('BaseDialog', () => {
  it('opens modally, mounts content only while open, and closes on demand', async () => {
    const { open, dialog } = render(false)
    expect(dialog.open).toBe(false)
    expect(dialog.querySelector('.body')).toBeNull()
    open.value = true
    await nextTick()
    expect(dialog.open).toBe(true)
    expect(dialog.querySelector('.body')).not.toBeNull()
    open.value = false
    await nextTick()
    expect(dialog.open).toBe(false)
  })

  it('asks the parent to close on Escape (cancel) and backdrop click, not inner clicks', () => {
    const { closes, dialog } = render(true)
    const cancel = new Event('cancel', { cancelable: true })
    dialog.dispatchEvent(cancel)
    expect(cancel.defaultPrevented).toBe(true)
    expect(closes.value).toBe(1)
    dialog.querySelector('.body')!.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    expect(closes.value).toBe(1)
    dialog.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    expect(closes.value).toBe(2)
  })
})
