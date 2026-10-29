
<template>
  <section class="agent-shell enterprise-card" aria-label="Admin Assistant Chat">
    <!-- Header -->
    <header class="agent-header">
      <div class="agent-title">
        <div class="agent-title-row">
          <span class="agent-icon" aria-hidden="true">✨</span>
          <h3 class="agent-heading">Admin Assistant</h3>
        </div>
        <p class="agent-subtitle">
          Run administrative commands safely. Review responses before taking action.
        </p>
      </div>

      <div class="agent-actions">
        <span class="status-pill" :class="statusPillClass" role="status" aria-live="polite">
          <span class="status-dot" :class="statusDotClass" aria-hidden="true"></span>
          {{ statusLabel }}
        </span>

        <button
          class="btn btn-secondary btn-sm"
          type="button"
          @click="copyTranscript"
          :disabled="messages.length === 0"
          title="Copy conversation"
          aria-label="Copy conversation transcript"
        >
          Copy
        </button>

        <button
          class="btn btn-secondary btn-sm"
          type="button"
          @click="clearChat"
          :disabled="messages.length === 0 || sending"
          title="Clear conversation"
          aria-label="Clear conversation"
        >
          Clear
        </button>
      </div>
    </header>

    <!-- Error banner -->
    <div v-if="errorText" class="alert alert-error agent-alert" role="alert" aria-live="assertive">
      <div class="alert-content">
        <div class="alert-title">Request failed</div>
        <div>{{ errorText }}</div>
      </div>
    </div>

    <!-- Danger Zone confirmation -->
    <div v-if="pendingDangerous" class="alert alert-warning agent-alert" role="alert">
      <div class="alert-content">
        <div class="alert-title">Confirm action</div>
        <div>
          This will perform <strong>{{ dangerSummary }}</strong>. Proceed?
        </div>
        <div class="alert-actions">
          <button class="btn btn-primary btn-sm" type="button" @click="confirmSend" aria-label="Confirm action">
            Proceed
          </button>
          <button class="btn btn-secondary btn-sm" type="button" @click="cancelDanger" aria-label="Cancel action">
            Cancel
          </button>
        </div>
      </div>
    </div>

    <!-- Chat -->
    <div
      ref="chatRef"
      class="chat-container agent-chat"
      :style="{ maxHeight: resolvedMaxHeight }"
      role="log"
      aria-live="polite"
      aria-relevant="additions text"
    >
      <!-- Load older (windowing control) -->
      <div
        v-if="messages.length > MAX_VISIBLE && visibleStartIndex > 0"
        class="load-older"
      >
        <button class="btn btn-secondary btn-sm" type="button" @click="showOlder" aria-label="Show older messages">
          Show older messages
        </button>
      </div>

      <!-- Empty state -->
      <div v-if="messages.length === 0" class="agent-empty">
        <div class="agent-empty-title">No messages yet</div>
        <div class="agent-empty-text">
          Try a command like <code>list users</code> or <code>show active sessions</code>.
        </div>
      </div>

      <!-- Messages -->
      <div
        v-for="m in visibleMessages"
        :key="m.id"
        class="chat-message"
        :class="m.role"
      >
        <div class="chat-message-header">
          <span class="role-pill" :class="m.role">
            {{ m.role === 'user' ? 'You' : 'Assistant' }}
          </span>
          <span class="meta-dot" aria-hidden="true">•</span>
          <time class="msg-time" :datetime="m.tsIso">{{ m.tsDisplay }}</time>
        </div>

        <!-- Format-aware safe rendering -->
        <div
          class="chat-message-content"
          :aria-live="m.role === 'assistant' ? 'polite' : undefined"
          role="article"
        >
          <!-- Safe/plain text -->
          <div
            v-if="!renderAsHtml(m)"
            class="msg-text"
            v-text="m.content"
          />
          <!-- Rich path: sanitized + decoded; markdown rendered without new deps -->
          <div
            v-else
            class="msg-html"
            v-html="renderHtml(m)"
          />
        </div>

        <!-- Inline error + retry -->
        <div v-if="m._isError" class="msg-error">
          <span class="error-badge" aria-hidden="true">⚠</span>
          <span class="error-text">Last request failed.</span>
          <button
            v-if="m._originalCommand && !sending"
            class="retry-btn"
            type="button"
            @click="retryCommand(m._originalCommand, m.id)"
          >
            Retry
          </button>
        </div>
      </div>

      <!-- Typing / in-flight response -->
      <div v-if="sending" class="chat-message assistant">
        <div class="chat-message-header">
          <span class="role-pill assistant">Assistant</span>
          <span class="meta-dot" aria-hidden="true">•</span>
          <span class="msg-time">Working…</span>
        </div>
        <div class="chat-message-content typing">
          <span class="typing-dot"></span>
          <span class="typing-dot"></span>
          <span class="typing-dot"></span>
        </div>
      </div>
    </div>

    <!-- Composer -->
    <form class="agent-composer" @submit.prevent="onSubmit" aria-label="Command input">
      <div class="composer-field">
        <label class="form-label" for="agent-input">Command</label>

        <textarea
          id="agent-input"
          v-model="input"
          class="form-textarea"
          :placeholder="placeholder"
          rows="2"
          :disabled="sending"
          @keydown="onKeyDown"
          autocomplete="off"
          spellcheck="false"
          aria-label="Type an admin command"
        />

        <div class="composer-help">
          <span class="hint">
            Press <kbd>Enter</kbd> to send, <kbd>Shift</kbd>+<kbd>Enter</kbd> for a new line.
          </span>
          <span class="hint muted" v-if="maxChars">
            {{ input.length }}/{{ maxChars }}
          </span>
        </div>
      </div>

      <div class="composer-actions">
        <button
          class="btn btn-secondary"
          type="button"
          @click="insertExample"
          :disabled="sending"
          title="Insert an example command"
          aria-label="Insert example command"
        >
          Example
        </button>

        <button
          class="btn btn-primary"
          type="submit"
          :disabled="!canSend"
          :aria-disabled="!canSend"
          aria-label="Execute command"
        >
          <span v-if="sending" class="spinner" aria-hidden="true"></span>
          {{ sending ? 'Executing…' : 'Execute' }}
        </button>
      </div>
    </form>

    <!-- Small compliance note -->
    <footer class="agent-footer">
      <span class="muted">
        Tip: Verify outputs before applying destructive actions (delete, cleanup, unlock).
      </span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, onMounted } from 'vue'

import api from '@/utils/api'
import { sanitizeHtml as sanitize } from '@/utils/sanitize'


/**
 * Enterprise AIAgent Chat
 * - Safe by default (v-text)
 * - Rich path with explicit server-declared format + sanitization
 * - Optional "Danger Zone" confirmation for destructive commands
 * - Auto-scroll only if user is pinned to bottom
 * - Simple windowing for large transcripts
 * - No new dependencies required (basic Markdown renderer included)
 */

type Msg = {
  id: string
  role: 'user' | 'assistant'
  content: string
  tsIso: string
  tsDisplay: string
  format?: 'text' | 'html' | 'markdown'
  details?: Record<string, any>
  _isError?: boolean
  _originalCommand?: string
}

const props = defineProps({
  endpoint: { type: String, default: '/admin/agent' },
  placeholder: { type: String, default: 'Admin command or question…' },
  maxHeight: { type: [String, Number], default: 360 },
  maxChars: { type: Number, default: 0 }, // 0 => unlimited
  // Only allow rich rendering in controlled environments
  trustHtml: { type: Boolean, default: false }
})

const chatRef = ref<HTMLElement | null>(null)
const messages = ref<Msg[]>([])

const input = ref('')
const sending = ref(false)
const errorText = ref('')

const MAX_VISIBLE = 250
const visibleStartIndex = ref(0)

const resolvedMaxHeight = computed(() => {
  const v = props.maxHeight
  return typeof v === 'number' ? `${v}px` : v
})

const canSend = computed(() => {
  const trimmed = input.value.trim()
  if (!trimmed) return false
  if (sending.value) return false
  if (props.maxChars && trimmed.length > props.maxChars) return false
  return true
})

const statusLabel = computed(() => (sending.value ? 'Running' : 'Ready'))
const statusPillClass = computed(() => (sending.value ? 'status-running' : 'status-ready'))
const statusDotClass = computed(() => (sending.value ? 'dot-running' : 'dot-ready'))

function nowStamp() {
  const d = new Date()
  return {
    tsIso: d.toISOString(),
    tsDisplay: d.toLocaleString(undefined, { hour: '2-digit', minute: '2-digit' })
  }
}

function pushMessage(role: 'user' | 'assistant', content: string, extra: Partial<Msg> = {}) {
  const { tsIso, tsDisplay } = nowStamp()
  messages.value.push({
    id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    role,
    content: String(content ?? ''),
    tsIso,
    tsDisplay,
    ...extra
  })
  // Windowing: keep last MAX_VISIBLE + small buffer
  if (messages.value.length > MAX_VISIBLE * 3) {
    const trimTo = Math.max(0, messages.value.length - MAX_VISIBLE * 2)
    messages.value.splice(0, trimTo)
    visibleStartIndex.value = 0
  }
}

const visibleMessages = computed(() => {
  if (messages.value.length <= MAX_VISIBLE) return messages.value
  const start = Math.max(0, messages.value.length - MAX_VISIBLE - visibleStartIndex.value)
  return messages.value.slice(start)
})

function showOlder() {
  const next = visibleStartIndex.value + Math.floor(MAX_VISIBLE / 2)
  // Cap so we don't exceed total length - MAX_VISIBLE
  const maxOlder = Math.max(0, messages.value.length - MAX_VISIBLE)
  visibleStartIndex.value = Math.min(next, maxOlder)
}

const NEAR_PX = 64
function isNearBottom(el: HTMLElement) {
  return el.scrollHeight - el.scrollTop - el.clientHeight < NEAR_PX
}
async function scrollToBottomIfPinned() {
  await nextTick()
  const el = chatRef.value
  if (!el) return
  if (isNearBottom(el)) el.scrollTop = el.scrollHeight
}

function clearChat() {
  errorText.value = ''
  messages.value = []
  visibleStartIndex.value = 0
}

async function copyTranscript() {
  // Export as text; preserves markdown where present
  const transcript = messages.value
    .map(m => `[${m.tsDisplay}] ${m.role.toUpperCase()}: ${m.content}`)
    .join('\n')

  try {
    await navigator.clipboard.writeText(transcript)
  } catch {
    // Fallback: silently ignore; user can select manually.
  }
}

function insertExample() {
  const example = 'Show active sessions and cleanup sessions older than 60 minutes (dry run).'
  input.value = input.value ? `${input.value}\n${example}` : example
}

function onKeyDown(e: KeyboardEvent) {
  // Enter to send; Shift+Enter newline
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    if (canSend.value) onSubmit()
  }
}

/** ====================== SAFE RENDERING ====================== */
function decodeEntities(s: string): string {
  const txt = document.createElement('textarea')
  txt.innerHTML = s
  return txt.value
}

/** Narrow allowlist: formatting tags only, no attributes at all. */
function sanitizeHtml(html: string): string {
  return sanitize(html, {
    ALLOWED_TAGS: ['b', 'strong', 'i', 'em', 'code', 'pre', 'p', 'br', 'ul', 'ol', 'li', 'span'],
    ALLOWED_ATTR: [],
  })
}

function escapeHtml(s: string): string {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

/** Minimal Markdown renderer (safe + adequate for our use-cases) */
function renderMarkdown(md: string): string {
  // Handle fenced code blocks ```
  let text = md.replace(/```([\s\S]*?)```/g, (_m, code) => {
    return `<pre><code>${escapeHtml(String(code).trim())}</code></pre>`
  })

  // Inline code `code`
  text = text.replace(/`([^`]+?)`/g, (_m, code) => `<code>${escapeHtml(code)}</code>`)

  // Bold **text**
  text = text.replace(/\*\*([^*]+?)\*\*/g, '<strong>$1</strong>')

  // Italic *text* (avoid conflict with bullet -*)
  text = text.replace(/(^|[\s(])\*([^\s*][^*]*?)\*(?=[\s).,!?:;]|$)/g, '$1<em>$2</em>')

  // Split into lines to build lists & paragraphs
  const lines = text.split(/\r?\n/)
  const out: string[] = []
  let inList = false

  const flushList = () => {
    if (inList) {
      out.push('</ul>')
      inList = false
    }
  }

  for (let i = 0; i < lines.length; i++) {
    const line = (lines[i] ?? '').trimEnd()

    if (!line.trim()) {
      flushList()
      out.push('') // paragraph break
      continue
    }

    const m = line.match(/^- (.*)/)
    if (m) {
      if (!inList) {
        out.push('<ul>')
        inList = true
      }
      out.push(`<li>${m[1]}</li>`)
      continue
    }

    flushList()
    // paragraph line (convert single newlines inside paragraphs to <br/> later)
    out.push(`<p>${line}</p>`)
  }
  flushList()

  // Merge consecutive <p> blocks and handle soft breaks
  const html = out
    .join('\n')
    .replace(/<\/p>\s*<p>/g, '<br />') // paragraph join as soft break
    .replace(/^\s*<br \/>|\s*<br \/>$/g, '') // clean edges

  return sanitizeHtml(html)
}

function renderAsHtml(m: Msg): boolean {
  return props.trustHtml && (m.format === 'html' || m.format === 'markdown')
}

function renderHtml(m: Msg): string {
  if (m.format === 'markdown') {
    // Server now returns markdown — render it safely
    return renderMarkdown(m.content)
  }
  // Server may send escaped HTML fragments; decode then sanitize
  const decoded = decodeEntities(m.content)
  return sanitizeHtml(decoded.replace(/\n/g, '<br />'))
}
/** ==================== END SAFE RENDERING ==================== */

/** ====================== DANGER ZONE ====================== */
const pendingDangerous = ref(false)
const dangerSummary = ref('')
let pendingCommand = ''

function isDangerousCommand(cmd: string): string | '' {
  // Tweak keywords as per your policies
  const lower = cmd.toLowerCase()
  if (/\b(delete|cleanup|clean\s*sessions|unlock|force\s*logout)\b/.test(lower)) {
    if (/\bdelete\b/.test(lower)) return 'delete operation'
    if (/\bclean\s*sessions|cleanup\b/.test(lower)) return 'session cleanup'
    if (/\bunlock\b/.test(lower)) return 'account unlock'
    if (/\bforce\s*logout\b/.test(lower)) return 'force logout'
    return 'potentially destructive action'
  }
  return ''
}

function onSubmit() {
  const command = input.value.trim()
  if (!command) return
  if (props.maxChars && command.length > props.maxChars) {
    errorText.value = `Command exceeds maximum length of ${props.maxChars} characters.`
    return
  }

  // Danger confirmation gate
  const danger = isDangerousCommand(command)
  if (danger && !pendingDangerous.value) {
    pendingDangerous.value = true
    dangerSummary.value = danger
    pendingCommand = command
    return
  }

  // Otherwise send immediately
  send(command)
}

function confirmSend() {
  if (!pendingDangerous.value) return
  const cmd = pendingCommand
  pendingDangerous.value = false
  dangerSummary.value = ''
  pendingCommand = ''
  if (cmd) send(cmd)
}

function cancelDanger() {
  pendingDangerous.value = false
  dangerSummary.value = ''
  pendingCommand = ''
}
/** ==================== END DANGER ZONE ==================== */

async function send(command?: string) {
  const cmd = (command ?? input.value).trim()
  if (!cmd) return
  if (props.maxChars && cmd.length > props.maxChars) {
    errorText.value = `Command exceeds maximum length of ${props.maxChars} characters.`
    return
  }

  errorText.value = ''
  sending.value = true

  // Show what the admin asked (audit trail UX)
  pushMessage('user', cmd)
  input.value = ''
  await scrollToBottomIfPinned()

  try {
    const res = await api.post(props.endpoint, { command: cmd })

    const data = res?.data ?? {}
    const result: string =
      data?.result ??
      data?.message ??
      (typeof data === 'string' ? data : 'OK')

    const fmt: Msg['format'] = data?.format ?? 'text'
    const details = data?.details

    pushMessage('assistant', result, { format: fmt, details })
  } catch (e: any) {
    const msg = e?.response?.data?.message || e?.response?.data?.detail || e?.message || 'Unknown error'
    errorText.value = msg
    pushMessage('assistant', `Error: ${msg}`, { _isError: true, _originalCommand: cmd, format: 'text' })
  } finally {
    sending.value = false
    await scrollToBottomIfPinned()
  }
}

async function retryCommand(originalCommand: string, errorMsgId: string) {
  // Remove the error message and the user message before it (if adjacent)
  const idx = messages.value.findIndex(m => m.id === errorMsgId)
  if (idx >= 0) {
    const removeFrom = idx > 0 && messages.value[idx - 1]?.role === 'user' ? idx - 1 : idx
    messages.value.splice(removeFrom, idx - removeFrom + 1)
  }
  errorText.value = ''
  input.value = originalCommand
  onSubmit()
}

onMounted(() => {
  // Optional welcome message
  pushMessage(
    'assistant',
    'Hi! Tell me what you want to do—e.g., **list users**, **show audit logs**, or **cleanup old sessions (dry run)**.',
    { format: 'markdown' }
  )
  nextTick(() => {
    const el = chatRef.value
    if (el) el.scrollTop = el.scrollHeight
  })
})
</script>

<style scoped>
/* Component-specific refinements while leveraging your global classes */

.agent-shell {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.agent-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-md);
  flex-wrap: wrap;
}

.agent-title {
  min-width: 280px;
}

.agent-title-row {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}

.agent-icon {
  font-size: 1.1rem;
  color: var(--brand-primary);
}

.agent-heading {
  margin: 0;
  font-size: var(--text-xl);
}

.agent-subtitle {
  margin: 6px 0 0 0;
  color: var(--text-secondary);
  font-size: var(--text-sm);
  line-height: 1.4;
}

.agent-actions {
  display: flex;
  gap: var(--space-sm);
  align-items: center;
  flex-wrap: wrap;
}

/* Status pill */
.status-pill {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: var(--radius-full);
  border: 1px solid var(--border-light);
  background: var(--surface-elevated);
  color: var(--text-secondary);
  font-weight: 800;
  font-size: 0.85rem;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
}

.status-ready { border-color: var(--border-light); }
.dot-ready { background: var(--success); }

.status-running {
  border-color: color-mix(in srgb, var(--brand-primary), var(--border-light) 60%);
  background: color-mix(in srgb, var(--brand-subtle), var(--surface-elevated) 70%);
}
.dot-running { background: var(--brand-primary); }

/* Chat wrapper polish */
.agent-chat {
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-light);
  background: var(--chat-bg);
  padding: var(--space-md);
  overflow: auto;
}

.load-older {
  display: flex;
  justify-content: center;
  padding-bottom: var(--space-sm);
}

/* Empty state */
.agent-empty {
  padding: var(--space-lg);
  border: 1px dashed var(--border-medium);
  border-radius: var(--radius-lg);
  background: var(--surface-base);
  color: var(--text-secondary);
  text-align: center;
}

.agent-empty-title {
  font-weight: 950;
  color: var(--text-heading);
}

.agent-empty-text {
  margin-top: 6px;
  font-size: var(--text-sm);
  color: var(--text-tertiary);
}

/* Message block */
.chat-message {
  padding: var(--space-md);
  border-bottom: 1px solid var(--border-light);
}

.chat-message:last-child {
  border-bottom: 0;
}

.chat-message-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

/* Message meta */
.role-pill {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border-radius: var(--radius-full);
  font-size: 0.78rem;
  font-weight: 900;
  border: 1px solid var(--border-light);
  background: var(--surface-base);
  color: var(--text-secondary);
}

.role-pill.user {
  border-color: color-mix(in srgb, var(--brand-primary), var(--border-light) 60%);
  background: color-mix(in srgb, var(--brand-subtle), var(--surface-base) 75%);
  color: var(--text-heading);
}

.role-pill.assistant {
  border-color: var(--border-light);
  background: var(--surface-base);
}

.meta-dot {
  color: var(--text-tertiary);
}

.msg-time {
  color: var(--text-tertiary);
  font-size: 0.82rem;
}

/* Message content */
.chat-message-content {
  font-size: var(--text-sm);
  color: var(--text-body, var(--text-secondary));
}

.msg-text {
  white-space: pre-wrap;
  word-break: break-word;
}

.msg-html :deep(pre) {
  background: var(--surface-active);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md, 8px);
  padding: 10px;
  overflow: auto;
}

.msg-html :deep(code) {
  font-family: var(--font-mono);
}

.msg-html :deep(ul) {
  padding-left: 1.25rem;
}

/* Inline error */
.msg-error {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 6px;
}

.error-badge {
  color: var(--danger, #ef4444);
  font-weight: 900;
}

.error-text {
  color: var(--text-tertiary);
  font-size: 0.86rem;
}

/* Typing indicator */
.typing {
  display: inline-flex;
  gap: 6px;
  align-items: center;
}

.typing-dot {
  width: 7px;
  height: 7px;
  border-radius: 999px;
  background: var(--text-tertiary);
  opacity: 0.55;
  animation: bounce 1s infinite ease-in-out;
}

.typing-dot:nth-child(2) { animation-delay: 0.12s; }
.typing-dot:nth-child(3) { animation-delay: 0.24s; }

@keyframes bounce {
  0%, 80%, 100% { transform: translateY(0); opacity: 0.45; }
  40% { transform: translateY(-3px); opacity: 0.9; }
}

/* Composer */
.agent-composer {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--space-md);
  flex-wrap: wrap;
  padding-top: var(--space-xs);
}

.composer-field {
  flex: 1;
  min-width: 280px;
}

.composer-help {
  margin-top: 8px;
  display: flex;
  justify-content: space-between;
  gap: var(--space-sm);
  flex-wrap: wrap;
}

.hint {
  color: var(--text-tertiary);
  font-size: var(--text-xs);
}

kbd {
  font-family: var(--font-mono);
  font-size: 0.78rem;
  padding: 2px 6px;
  border-radius: 8px;
  background: var(--surface-active);
  border: 1px solid var(--border-light);
  color: var(--text-secondary);
}

.composer-actions {
  display: flex;
  gap: var(--space-sm);
  align-items: center;
}

/* Footer */
.agent-footer {
  padding-top: 2px;
}

/* Retry button */
.retry-btn {
  margin-top: 0;
  padding: 5px 12px;
  border-radius: var(--radius-md, 8px);
  border: 1px solid color-mix(in srgb, var(--danger, #ef4444), transparent 65%);
  background: color-mix(in srgb, var(--danger, #ef4444), transparent 88%);
  color: var(--text-secondary, rgba(255,255,255,0.7));
  font-size: 0.82rem;
  font-weight: 700;
  cursor: pointer;
  transition: background 0.12s ease, border-color 0.12s ease;
}
.retry-btn:hover {
  background: color-mix(in srgb, var(--danger, #ef4444), transparent 80%);
  border-color: color-mix(in srgb, var(--danger, #ef4444), transparent 50%);
}

/* Alert (danger confirmation) */
.agent-alert {
  border-radius: var(--radius-lg);
  padding: var(--space-sm) var(--space-md);
}

.alert-actions {
  margin-top: 8px;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
</style>
