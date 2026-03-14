
<template>
  <section class="ret-chat" aria-label="RET AI Chat">
    <!-- Header -->
    <header class="ret-chat__header">
      <div class="ret-chat__brand">
        <div class="ret-chat__brandIcon" aria-hidden="true">🤖</div>
        <div class="ret-chat__brandMeta">
          <h2 class="ret-chat__title">RET AI Assistant</h2>
          <div class="ret-chat__status" :class="statusClass" aria-live="polite">
            <span class="ret-chat__dot" aria-hidden="true"></span>
            <span>{{ sessionId ? 'Connected' : 'No Session' }}</span>
          </div>
        </div>
      </div>

      <div class="ret-chat__actions">
        <button
          v-if="indexStats.totalDocuments > 0"
          class="btn btn--soft"
          type="button"
          @click="toggleStats"
          :aria-expanded="showStats ? 'true' : 'false'"
          aria-controls="stats-panel"
          title="View Index Stats"
        >
          <span aria-hidden="true">📊</span>
          <span class="btn__label">{{ indexStats.totalDocuments }} docs</span>
          <span class="btn__sep">•</span>
          <span class="btn__label">{{ indexStats.totalChunks }} chunks</span>
        </button>

        <button class="btn btn--icon" type="button" @click="clearChat" aria-label="Clear chat" title="Clear Chat">
          🗑️
        </button>

        <button
          class="btn btn--icon"
          type="button"
          @click="downloadTranscript"
          :disabled="!sessionId"
          aria-label="Download transcript"
          title="Download Transcript"
        >
          📥
        </button>
      </div>
    </header>

    <!-- Stats Panel -->
    <div
      v-if="showStats"
      id="stats-panel"
      class="ret-chat__stats"
      role="region"
      aria-label="Index statistics"
    >
      <div class="statsGrid">
        <div class="statCard">
          <div class="statCard__value">{{ indexStats.totalDocuments }}</div>
          <div class="statCard__label">Documents</div>
        </div>
        <div class="statCard">
          <div class="statCard__value">{{ indexStats.totalChunks }}</div>
          <div class="statCard__label">Chunks</div>
        </div>
        <div class="statCard">
          <div class="statCard__value">{{ indexStats.groups?.length || 0 }}</div>
          <div class="statCard__label">Groups</div>
        </div>
      </div>

      <div v-if="indexStats.groups?.length" class="tagRow" aria-label="Indexed groups">
        <span class="tagRow__label">Indexed Groups</span>
        <span v-for="g in indexStats.groups" :key="g" class="tag">{{ g }}</span>
      </div>
    </div>

    <!-- Messages -->
    <main class="ret-chat__body">
      <div
        class="ret-chat__messages"
        ref="messagesContainer"
        role="log"
        aria-live="polite"
        aria-relevant="additions"
        tabindex="0"
        @scroll="onScroll"
      >
        <!-- Welcome State -->
        <div v-if="messages.length === 1" class="welcome">
          <div class="welcome__icon" aria-hidden="true">🤖</div>
          <h3 class="welcome__title">Welcome to RET AI</h3>
          <p class="welcome__subtitle">
            Ask questions about your indexed XML data. Answers include citation support and retrieved document inspection.
          </p>

          <div class="welcome__quick">
            <button
              v-for="prompt in quickPrompts"
              :key="prompt"
              class="pill"
              type="button"
              @click="sendMessage(prompt)"
              :disabled="!sessionId || sending"
            >
              {{ prompt }}
            </button>
          </div>
        </div>

        <!-- Messages list -->
        <article
          v-for="(m, i) in messages"
          :key="i"
          class="msg"
          :class="m.role === 'user' ? 'msg--user' : 'msg--assistant'"
        >
          <div class="msg__avatar" aria-hidden="true">
            {{ m.role === 'user' ? '👤' : '🤖' }}
          </div>

          <div class="msg__card">
            <header class="msg__header">
              <span class="msg__role">{{ m.role === 'user' ? 'You' : 'RET AI' }}</span>
              <time class="msg__time" :datetime="m.timestamp">{{ formatTime(m.timestamp) }}</time>
            </header>

            <!-- content -->
            <div class="msg__content" v-html="formatMessage(m.content)"></div>

            <!-- retry button for failed messages -->
            <button
              v-if="m._isError && m._originalQuery && !sending"
              class="retryBtn"
              type="button"
              @click="retryMessage(m._originalQuery, i)"
              title="Retry this message"
            >
              Retry
            </button>

            <!-- sources (assistant only) -->
            <div v-if="m.role === 'assistant' && m.sources?.length" class="sources">
              <button
                class="sources__toggle"
                type="button"
                @click="m._expanded = !m._expanded"
                :aria-expanded="m._expanded ? 'true' : 'false'"
              >
                <span class="sources__title">📚 {{ m.sources.length }} Source{{ m.sources.length !== 1 ? 's' : '' }}</span>
                <span class="sources__chev" aria-hidden="true">{{ m._expanded ? '▲' : '▼' }}</span>
              </button>

              <div v-if="m._expanded" class="sources__list">
                <div v-for="(src, si) in m.sources" :key="si" class="source">
                  <div class="source__top">
                    <div class="source__doc" :title="src.doc">📄 {{ src.doc }}</div>
                    <div v-if="src.score != null" class="score" :class="getScoreClass(src.score)">
                      {{ Math.round(src.score * 100) }}%
                    </div>
                  </div>
                  <div class="source__snippet">{{ truncateText(src.snippet, 220) }}</div>
                  <div v-if="src.method" class="source__meta">
                    <span class="chip" :class="`chip--${src.method}`">{{ src.method }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </article>

        <!-- Typing indicator -->
        <div v-if="sending" class="msg msg--assistant msg--typing" aria-label="Assistant is typing">
          <div class="msg__avatar" aria-hidden="true">🤖</div>
          <div class="msg__card">
            <div class="typing">
              <span></span><span></span><span></span>
            </div>
          </div>
        </div>
      </div>

      <!-- “New messages” button when user is not at bottom -->
      <button
        v-if="showNewMessages"
        class="newMsgBtn"
        type="button"
        @click="scrollToBottom(true)"
      >
        New messages ↓
      </button>
    </main>

    <!-- Retrieval Inspector -->
    <aside v-if="retrievals.length" class="inspector" aria-label="RAG Retrieval Inspector">
      <div class="inspector__header">
        <div class="inspector__title">
          <span aria-hidden="true">🔍</span>
          <strong>RAG Retrieval Inspector</strong>
          <span class="muted">({{ retrievals.length }} retrieved)</span>
        </div>

        <button class="btn btn--soft" type="button" @click="inspectorExpanded = !inspectorExpanded">
          {{ inspectorExpanded ? 'Collapse' : 'Expand' }}
        </button>
      </div>

      <div v-if="inspectorExpanded" class="inspector__content">
        <div class="cards">
          <div v-for="(r, idx) in retrievals" :key="idx" class="card">
            <div class="card__top">
              <div class="card__k">#{{ idx + 1 }}</div>
              <div class="card__doc" :title="r.doc">📄 {{ r.doc }}</div>
              <div v-if="r.score != null" class="score" :class="getScoreClass(r.score)">
                {{ Math.round(r.score * 100) }}%
              </div>
            </div>
            <div v-if="r.group" class="card__meta"><span class="muted">Group:</span> {{ r.group }}</div>
            <p v-if="r.snippet" class="card__snippet">{{ truncateText(r.snippet, 240) }}</p>
            <div v-if="r.method" class="card__meta">
              <span class="chip" :class="`chip--${r.method}`">{{ r.method }}</span>
            </div>
          </div>
        </div>
      </div>
    </aside>

    <!-- Input -->
    <footer class="ret-chat__composer">
      <div v-if="!sessionId" class="banner banner--warn" role="status">
        ⚠️ No session active. Please scan a ZIP file first.
      </div>

      <form class="composer" @submit.prevent="handleSend">
        <div class="composer__field">
          <label class="srOnly" for="chatInput">Message</label>
          <textarea
            id="chatInput"
            ref="inputEl"
            v-model="input"
            class="composer__input"
            placeholder="Ask about your indexed data… (Enter to send, Shift+Enter for new line)"
            :disabled="!sessionId || sending"
            rows="1"
            @keydown.enter.exact.prevent="handleSend"
            @input="autoGrow"
          ></textarea>

          <div class="composer__meta">
            <span class="counter" :class="{ 'counter--warn': input.length > 3500 }">
              {{ input.length }}/4000
            </span>
          </div>
        </div>

        <button class="btn btn--primary" type="submit" :disabled="!canSend">
          <span v-if="sending" class="spinner" aria-hidden="true"></span>
          <span v-else aria-hidden="true">➤</span>
          <span class="srOnly">Send</span>
        </button>
      </form>

      <div class="hint">
        Tip: use <code>group="NAME"</code> to filter • <code>top_k=8</code> to limit results
      </div>
    </footer>
  </section>
</template>

<script setup>
import { ref, computed, watch, onMounted, nextTick } from 'vue'
import api from '@/utils/api'

const props = defineProps({
  indexedGroups: { type: Array, default: () => [] },
  sessionId: { type: String, default: null }
})

const emit = defineEmits(['chat-error', 'stats-updated'])

// ---------- State ----------
const messages = ref([
  {
    role: 'assistant',
    content: "Hello! I'm your RET AI Assistant. Ask me about your indexed data, and I’ll answer with source citations.",
    timestamp: new Date().toISOString()
  }
])

const input = ref('')
const sending = ref(false)
const retrievals = ref([])
const showStats = ref(false)
const inspectorExpanded = ref(true)

const inputEl = ref(null)
const messagesContainer = ref(null)

const showNewMessages = ref(false)
const userIsNearBottom = ref(true)

const indexStats = ref({
  totalDocuments: 0,
  totalChunks: 0,
  groups: []
})

const quickPrompts = [
  'Summarize the main data',
  'What groups are indexed?',
  'Show key statistics',
  'List unique values'
]

// ---------- Derived ----------
const canSend = computed(() => {
  return !!props.sessionId && !sending.value && input.value.trim().length > 0
})

const statusClass = computed(() => ({
  'ret-chat__status--ok': !!props.sessionId,
  'ret-chat__status--off': !props.sessionId
}))

// ---------- Watch session ----------
watch(
  () => props.sessionId,
  async (newId) => {
    if (newId) {
      await Promise.all([loadChatHistory(), loadIndexStats()])
      scrollToBottom(true)
    } else {
      resetChat()
    }
  },
  { immediate: true }
)

// ---------- API ----------
async function loadChatHistory() {
  try {
    const resp = await api.get(`/v2/ai/chat/history/${props.sessionId}`)
    if (resp.data?.history?.length) {
      messages.value = resp.data.history.map(m => ({
        ...m,
        timestamp: m.timestamp || new Date().toISOString(),
        _expanded: false
      }))
    }
  } catch {
    resetChat()
  }
}

async function loadIndexStats() {
  try {
    const resp = await api.get(`/v2/ai/embedding/stats/${props.sessionId}`)
    indexStats.value = {
      totalDocuments: resp.data.total_documents || 0,
      totalChunks: resp.data.total_chunks || 0,
      groups: resp.data.groups || []
    }
    emit('stats-updated', indexStats.value)
  } catch {
    indexStats.value = { totalDocuments: 0, totalChunks: 0, groups: [] }
  }
}

// ---------- Actions ----------
function resetChat() {
  messages.value = [
    {
      role: 'assistant',
      content: "Hello! I'm your RET AI Assistant. Ask me about your indexed data, and I’ll answer with source citations.",
      timestamp: new Date().toISOString()
    }
  ]
  retrievals.value = []
  showNewMessages.value = false
}

function clearChat() {
  resetChat()
  if (props.sessionId) {
    api.delete(`/v2/ai/chat/history/${props.sessionId}`).catch(() => {})
  }
}

function toggleStats() {
  showStats.value = !showStats.value
}

async function handleSend() {
  if (!canSend.value) return
  const text = input.value.trim()
  await sendMessage(text)
}

function parseModifiers(text) {
  // Supports:
  // group=NAME, group="My Group", group='My Group'
  // top_k=8
  let query = text
  let groupFilter = null
  let topK = 8

  const groupRegex = /group=(?:"([^"]+)"|'([^']+)'|([^\s]+))/i
  const groupMatch = text.match(groupRegex)
  if (groupMatch) {
    groupFilter = (groupMatch[1] || groupMatch[2] || groupMatch[3] || '').trim()
    query = query.replace(groupRegex, '').trim()
  }

  const topKRegex = /top_k=(\d+)/i
  const topKMatch = text.match(topKRegex)
  if (topKMatch) {
    const n = parseInt(topKMatch[1], 10)
    if (!Number.isNaN(n)) topK = Math.max(1, Math.min(n, 50))
    query = query.replace(topKRegex, '').trim()
  }

  return { query, groupFilter, topK }
}

async function sendMessage(text) {
  const { query, groupFilter, topK } = parseModifiers(text)

  messages.value.push({
    role: 'user',
    content: text,
    timestamp: new Date().toISOString()
  })

  input.value = ''
  sending.value = true

  // Only autoscroll if user is near bottom; otherwise show new message button
  if (userIsNearBottom.value) scrollToBottom(true)

  try {
    const resp = await api.post('/v2/ai/chat', {
      session_id: props.sessionId,
      question: query,
      group_filter: groupFilter,
      top_k: topK,
      use_rag: true
    })

    const answer = resp.data.answer || resp.data.response || 'No response received.'
    const sources = resp.data.sources || resp.data.retrievals || []

    const mappedSources = sources.map(s => ({
      doc: s.source || s.doc || s.file || 'unknown',
      score: s.score,
      snippet: s.snippet || s.content || '',
      group: s.group,
      method: s.method || 'hybrid'
    }))

    messages.value.push({
      role: 'assistant',
      content: answer,
      sources: mappedSources,
      timestamp: new Date().toISOString(),
      _expanded: false
    })

    retrievals.value = mappedSources

  } catch (e) {
    const errorMsg = e.response?.data?.detail || e.message || 'An error occurred'
    messages.value.push({
      role: 'assistant',
      content: `<strong>Error:</strong> ${escapeHtml(errorMsg)}`,
      timestamp: new Date().toISOString(),
      _isError: true,
      _originalQuery: text,
    })
    emit('chat-error', errorMsg)
  } finally {
    sending.value = false

    // Scroll behavior: if user isn't near bottom, don't yank them
    if (userIsNearBottom.value) {
      scrollToBottom(true)
    } else {
      showNewMessages.value = true
    }
  }
}

async function retryMessage(originalQuery, errorIndex) {
  // Remove the error message and the user message before it
  const removeFrom = errorIndex > 0 && messages.value[errorIndex - 1]?.role === 'user'
    ? errorIndex - 1
    : errorIndex
  messages.value.splice(removeFrom, errorIndex - removeFrom + 1)
  await sendMessage(originalQuery)
}

async function downloadTranscript() {
  if (!props.sessionId) return

  try {
    const resp = await api.get(`/v2/ai/transcript/download`, {
      params: { session_id: props.sessionId, format: 'markdown' },
      responseType: 'blob'
    })

    const url = window.URL.createObjectURL(new Blob([resp.data]))
    const link = document.createElement('a')
    link.href = url
    link.setAttribute('download', `chat_transcript_${props.sessionId}.md`)
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.URL.revokeObjectURL(url)

  } catch {
    // fallback local transcript
    const transcript = messages.value
      .map(m => `## ${m.role === 'user' ? 'You' : 'RET AI'}\n${m.content}\n`)
      .join('\n---\n\n')

    const blob = new Blob([transcript], { type: 'text/markdown' })
    const url = window.URL.createObjectURL(blob)

    const link = document.createElement('a')
    link.href = url
    link.setAttribute('download', 'chat_transcript.md')
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.URL.revokeObjectURL(url)
  }
}

// ---------- Rendering Helpers ----------
function formatMessage(content) {
  if (!content) return ''

  // 1) escape all HTML first (prevents injection)
  let html = escapeHtml(String(content))

  // 2) basic markdown-lite (safe because we've already escaped)
  // code blocks ```...```
  html = html.replace(/```([\s\S]*?)```/g, (m, code) => {
    return `<pre class="md-pre"><code>${code}</code></pre>`
  })

  // inline code `...`
  html = html.replace(/`([^`]+)`/g, '<code class="md-code">$1</code>')

  // headings
  html = html
    .replace(/^### (.+)$/gm, '<h3 class="md-h3">$1</h3>')
    .replace(/^## (.+)$/gm, '<h2 class="md-h2">$1</h2>')
    .replace(/^# (.+)$/gm, '<h1 class="md-h1">$1</h1>')

  // bold/italic
  html = html
    .replace(/\*\*\*(.*?)\*\*\*/g, '<strong><em>$1</em></strong>')
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')

  // citations [source:1]
  html = html.replace(/\[source:(\d+)\]/gi, (_, num) => {
    return `
      <span class="citation" data-source="${num}" title="Source ${num}">
        <span class="citation__icon">📄</span>
        <span class="citation__num">${num}</span>
      </span>`
  })

  // csv references [csv:1]
  html = html.replace(/\[csv:(\d+)\]/g, '<span class="csvRef">📊 CSV:$1</span>')

  // line breaks
  html = html.replace(/\n/g, '<br />')
  return html
}

function escapeHtml(unsafe) {
  return unsafe.replace(/[&<>"']/g, (ch) => {
    switch (ch) {
      case '&': return '&amp;'
      case '<': return '&lt;'
      case '>': return '&gt;'
      case '"': return '&quot;'
      case "'": return '&#039;'
      default: return ch
    }
  })
}

function formatTime(ts) {
  if (!ts) return ''
  const date = new Date(ts)
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function truncateText(text, maxLen) {
  if (!text) return ''
  return text.length > maxLen ? text.slice(0, maxLen) + '…' : text
}

function getScoreClass(score) {
  if (score == null) return ''
  if (score >= 0.8) return 'score--high'
  if (score >= 0.5) return 'score--mid'
  return 'score--low'
}

// ---------- Composer UI ----------
function autoGrow() {
  const el = inputEl.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 140) + 'px'
}

function onScroll() {
  const el = messagesContainer.value
  if (!el) return

  const threshold = 80
  const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
  userIsNearBottom.value = distanceFromBottom < threshold

  if (userIsNearBottom.value) {
    showNewMessages.value = false
  }
}

async function scrollToBottom(force = false) {
  await nextTick()
  const el = messagesContainer.value
  if (!el) return

  if (force || userIsNearBottom.value) {
    el.scrollTop = el.scrollHeight
    showNewMessages.value = false
  }
}

onMounted(() => {
  scrollToBottom(true)
})
</script>

<style scoped>
/* =========================
   Enterprise Design Tokens
   ========================= */
.ret-chat {
  --bg0: #0b1220;
  --bg1: #0f1a2e;
  --bg2: #121f38;
  --card: rgba(255, 255, 255, 0.04);
  --card2: rgba(255, 255, 255, 0.06);
  --border: rgba(255, 255, 255, 0.10);
  --border2: rgba(255, 255, 255, 0.14);

  --text: rgba(255, 255, 255, 0.92);
  --muted: rgba(255, 255, 255, 0.62);
  --muted2: rgba(255, 255, 255, 0.48);

  --primary: #6d5efc;
  --primary2: #8b7bff;
  --success: #22c55e;
  --warn: #f59e0b;
  --danger: #ef4444;

  --radius: 12px;
  --radius2: 16px;

  --shadow: 0 10px 30px rgba(0,0,0,0.35);
  --shadow2: 0 6px 18px rgba(0,0,0,0.25);

  display: flex;
  flex-direction: column;
  height: 100%;
  border-radius: var(--radius2);
  overflow: hidden;
  background:
    radial-gradient(1200px 600px at 30% -10%, rgba(109, 94, 252, 0.25), transparent 55%),
    radial-gradient(900px 500px at 110% 10%, rgba(34, 197, 94, 0.10), transparent 60%),
    linear-gradient(180deg, var(--bg0), var(--bg1));
  border: 1px solid var(--border);
  box-shadow: var(--shadow);
}

/* =========================
   Header
   ========================= */
.ret-chat__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 16px;
  background: linear-gradient(180deg, rgba(255,255,255,0.06), rgba(255,255,255,0.02));
  border-bottom: 1px solid var(--border);
  backdrop-filter: blur(10px);
}

.ret-chat__brand {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.ret-chat__brandIcon {
  width: 40px;
  height: 40px;
  border-radius: 14px;
  display: grid;
  place-items: center;
  background: linear-gradient(135deg, rgba(109,94,252,0.25), rgba(255,255,255,0.06));
  border: 1px solid var(--border);
  box-shadow: var(--shadow2);
}

.ret-chat__brandMeta {
  display: grid;
  gap: 2px;
  min-width: 0;
}

.ret-chat__title {
  margin: 0;
  font-size: 0.98rem;
  letter-spacing: 0.2px;
  color: var(--text);
}

.ret-chat__status {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 0.78rem;
  color: var(--muted);
}

.ret-chat__dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: var(--warn);
  box-shadow: 0 0 0 4px rgba(245,158,11,0.15);
}

.ret-chat__status--ok .ret-chat__dot {
  background: var(--success);
  box-shadow: 0 0 0 4px rgba(34,197,94,0.15);
}
.ret-chat__status--off .ret-chat__dot {
  background: var(--warn);
}

.ret-chat__actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

/* Buttons */
.btn {
  border-radius: 12px;
  border: 1px solid var(--border);
  background: rgba(255,255,255,0.04);
  color: var(--text);
  padding: 9px 12px;
  cursor: pointer;
  transition: transform 0.12s ease, background 0.12s ease, border-color 0.12s ease, opacity 0.12s ease;
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.btn:hover { background: rgba(255,255,255,0.06); border-color: var(--border2); }
.btn:active { transform: translateY(1px); }
.btn:disabled { opacity: 0.55; cursor: not-allowed; }
.btn:focus-visible { outline: 2px solid rgba(109,94,252,0.65); outline-offset: 2px; }

.btn--icon {
  width: 40px;
  height: 40px;
  padding: 0;
  justify-content: center;
  border-radius: 14px;
}

.btn--soft {
  background: rgba(255,255,255,0.03);
}
.btn--primary {
  background: linear-gradient(135deg, var(--primary), var(--primary2));
  border-color: rgba(255,255,255,0.20);
}
.btn--primary:hover { filter: brightness(1.06); }
.btn__sep { color: var(--muted2); }
.btn__label { color: var(--muted); }

/* =========================
   Stats Panel
   ========================= */
.ret-chat__stats {
  padding: 14px 16px;
  border-bottom: 1px solid var(--border);
  background: rgba(255,255,255,0.02);
}

.statsGrid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.statCard {
  padding: 12px;
  border-radius: 14px;
  border: 1px solid var(--border);
  background: var(--card);
}
.statCard__value {
  font-size: 1.4rem;
  font-weight: 800;
  color: rgba(109, 94, 252, 0.95);
}
.statCard__label {
  font-size: 0.75rem;
  color: var(--muted2);
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.tagRow {
  margin-top: 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}
.tagRow__label {
  color: var(--muted2);
  font-size: 0.8rem;
  margin-right: 6px;
}
.tag {
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid rgba(109,94,252,0.35);
  color: rgba(209, 205, 255, 0.95);
  background: rgba(109,94,252,0.12);
  font-size: 0.78rem;
}

/* =========================
   Body / Messages
   ========================= */
.ret-chat__body {
  position: relative;
  flex: 1;
  min-height: 0;
}

.ret-chat__messages {
  height: 100%;
  overflow: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  scroll-behavior: smooth;
}

/* Welcome */
.welcome {
  margin: 24px auto;
  width: min(680px, 100%);
  padding: 20px;
  text-align: center;
  border-radius: 18px;
  background: linear-gradient(180deg, rgba(255,255,255,0.05), rgba(255,255,255,0.02));
  border: 1px solid var(--border);
}
.welcome__icon {
  width: 56px;
  height: 56px;
  margin: 0 auto 12px;
  border-radius: 18px;
  display: grid;
  place-items: center;
  background: rgba(109,94,252,0.14);
  border: 1px solid rgba(109,94,252,0.3);
}
.welcome__title { margin: 0; color: var(--text); }
.welcome__subtitle {
  margin: 8px auto 0;
  color: var(--muted);
  line-height: 1.6;
  max-width: 54ch;
}
.welcome__quick {
  margin-top: 14px;
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 10px;
}
.pill {
  border-radius: 999px;
  padding: 8px 12px;
  border: 1px solid var(--border);
  background: rgba(255,255,255,0.03);
  color: var(--muted);
  cursor: pointer;
  transition: background 0.12s ease, border-color 0.12s ease;
}
.pill:hover { background: rgba(109,94,252,0.10); border-color: rgba(109,94,252,0.30); color: var(--text); }
.pill:disabled { opacity: 0.5; cursor: not-allowed; }

/* Messages */
.msg {
  display: flex;
  gap: 10px;
  width: min(860px, 100%);
  animation: fadeUp 0.18s ease;
}
@keyframes fadeUp {
  from { opacity: 0; transform: translateY(6px); }
  to { opacity: 1; transform: translateY(0); }
}

.msg--user { margin-left: auto; flex-direction: row-reverse; }
.msg__avatar {
  width: 40px;
  height: 40px;
  border-radius: 14px;
  display: grid;
  place-items: center;
  border: 1px solid var(--border);
  background: rgba(255,255,255,0.03);
  flex: 0 0 auto;
}

.msg--user .msg__avatar {
  background: linear-gradient(135deg, rgba(109,94,252,0.85), rgba(139,123,255,0.75));
  border-color: rgba(255,255,255,0.22);
}

.msg__card {
  flex: 1;
  border-radius: 16px;
  border: 1px solid var(--border);
  background: var(--card);
  padding: 10px 12px;
  box-shadow: 0 1px 0 rgba(255,255,255,0.04) inset;
}

.msg--user .msg__card {
  background: linear-gradient(180deg, rgba(109,94,252,0.12), rgba(255,255,255,0.03));
  border-color: rgba(109,94,252,0.38);
}

.msg__header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 6px;
}
.msg__role {
  font-weight: 700;
  font-size: 0.86rem;
  color: var(--text);
}
.msg__time {
  font-size: 0.72rem;
  color: var(--muted2);
}

.msg__content {
  color: var(--muted);
  line-height: 1.65;
  font-size: 0.93rem;
}

/* markdown lite styles */
.md-pre {
  margin: 10px 0;
  padding: 10px;
  border-radius: 14px;
  border: 1px solid var(--border);
  background: rgba(0,0,0,0.25);
  overflow: auto;
}
.md-pre code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
  font-size: 0.88rem;
  color: rgba(255,255,255,0.86);
}
.md-code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
  padding: 2px 6px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: rgba(0,0,0,0.22);
  color: rgba(255,255,255,0.86);
}

.md-h1, .md-h2, .md-h3 { color: var(--text); margin: 10px 0 6px; }
.md-h1 { font-size: 1.12rem; }
.md-h2 { font-size: 1.05rem; }
.md-h3 { font-size: 1.00rem; }

/* citations */
.citation {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin: 0 2px;
  padding: 2px 8px;
  border-radius: 10px;
  border: 1px solid rgba(109,94,252,0.35);
  background: rgba(109,94,252,0.12);
  color: rgba(209,205,255,0.95);
  font-weight: 700;
  font-size: 0.82em;
}
.citation__icon { opacity: 0.9; }
.csvRef {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin: 0 2px;
  padding: 2px 8px;
  border-radius: 10px;
  border: 1px solid rgba(245,158,11,0.35);
  background: rgba(245,158,11,0.10);
  color: rgba(255, 229, 188, 0.95);
  font-weight: 700;
  font-size: 0.82em;
}

/* sources */
.sources { margin-top: 10px; padding-top: 10px; border-top: 1px dashed rgba(255,255,255,0.14); }
.sources__toggle {
  width: 100%;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  background: transparent;
  border: none;
  color: var(--muted2);
  cursor: pointer;
  padding: 2px 2px;
}
.sources__toggle:hover { color: rgba(209,205,255,0.95); }
.sources__list { margin-top: 10px; display: grid; gap: 10px; }
.source {
  border-radius: 14px;
  border: 1px solid var(--border);
  background: rgba(0,0,0,0.18);
  padding: 10px;
}
.source__top { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.source__doc { font-weight: 700; font-size: 0.82rem; color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.source__snippet { margin-top: 6px; color: var(--muted2); font-size: 0.82rem; line-height: 1.5; }
.source__meta { margin-top: 8px; display: flex; gap: 8px; align-items: center; }

.score {
  font-size: 0.76rem;
  font-weight: 800;
  padding: 3px 8px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: rgba(255,255,255,0.04);
  white-space: nowrap;
}
.score--high { border-color: rgba(34,197,94,0.35); background: rgba(34,197,94,0.12); color: rgba(196, 255, 219, 0.95); }
.score--mid  { border-color: rgba(245,158,11,0.35); background: rgba(245,158,11,0.12); color: rgba(255, 240, 205, 0.95); }
.score--low  { color: var(--muted2); }

.chip {
  font-size: 0.72rem;
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  border-radius: 999px;
  padding: 4px 10px;
  border: 1px solid var(--border);
  color: var(--muted);
  background: rgba(255,255,255,0.03);
}
.chip--hybrid { border-color: rgba(109,94,252,0.35); background: rgba(109,94,252,0.10); color: rgba(209,205,255,0.95); }
.chip--dense  { border-color: rgba(34,197,94,0.35); background: rgba(34,197,94,0.10); color: rgba(196, 255, 219, 0.95); }
.chip--sparse { border-color: rgba(245,158,11,0.35); background: rgba(245,158,11,0.10); color: rgba(255, 240, 205, 0.95); }

/* typing */
.msg--typing .msg__card { padding: 14px 12px; }
.typing { display: inline-flex; gap: 6px; align-items: center; }
.typing span {
  width: 8px; height: 8px; border-radius: 999px;
  background: rgba(255,255,255,0.35);
  animation: bounce 1.1s infinite ease-in-out;
}
.typing span:nth-child(2) { animation-delay: 0.15s; }
.typing span:nth-child(3) { animation-delay: 0.30s; }
@keyframes bounce {
  0%, 100% { transform: translateY(0); opacity: 0.5; }
  50% { transform: translateY(-5px); opacity: 1; }
}

/* retry button */
.retryBtn {
  margin-top: 8px;
  padding: 6px 14px;
  border-radius: 10px;
  border: 1px solid rgba(239,68,68,0.35);
  background: rgba(239,68,68,0.10);
  color: rgba(255, 200, 200, 0.95);
  font-size: 0.82rem;
  font-weight: 700;
  cursor: pointer;
  transition: background 0.12s ease, border-color 0.12s ease;
}
.retryBtn:hover {
  background: rgba(239,68,68,0.18);
  border-color: rgba(239,68,68,0.50);
}

/* new message floating button */
.newMsgBtn {
  position: absolute;
  right: 16px;
  bottom: 16px;
  border-radius: 999px;
  border: 1px solid rgba(109,94,252,0.35);
  background: rgba(109,94,252,0.18);
  color: rgba(255,255,255,0.92);
  padding: 10px 14px;
  cursor: pointer;
  box-shadow: var(--shadow2);
}
.newMsgBtn:hover { filter: brightness(1.06); }

/* =========================
   Inspector
   ========================= */
.inspector {
  border-top: 1px solid var(--border);
  background: rgba(255,255,255,0.02);
  padding: 12px 16px;
  max-height: 260px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.inspector__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.inspector__title { display: flex; align-items: center; gap: 8px; color: var(--text); }
.muted { color: var(--muted2); font-size: 0.85em; }

.inspector__content {
  overflow: auto;
  padding-right: 6px;
}

.cards {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}
@media (max-width: 980px) { .cards { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 640px) { .cards { grid-template-columns: 1fr; } }

.card {
  border-radius: 14px;
  border: 1px solid var(--border);
  background: var(--card);
  padding: 10px;
}
.card__top { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.card__k {
  width: 28px; height: 28px; border-radius: 10px;
  display: grid; place-items: center;
  background: rgba(109,94,252,0.12);
  border: 1px solid rgba(109,94,252,0.25);
  color: rgba(209,205,255,0.95);
  font-weight: 900;
}
.card__doc { font-weight: 800; color: var(--text); flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.card__snippet { margin: 8px 0 0; color: var(--muted2); font-size: 0.83rem; line-height: 1.5; }
.card__meta { margin-top: 8px; color: var(--muted2); font-size: 0.8rem; }

/* =========================
   Composer
   ========================= */
.ret-chat__composer {
  padding: 14px 16px;
  border-top: 1px solid var(--border);
  background: linear-gradient(180deg, rgba(255,255,255,0.02), rgba(255,255,255,0.03));
}

.banner {
  padding: 10px 12px;
  border-radius: 14px;
  border: 1px solid var(--border);
  margin-bottom: 10px;
  color: var(--text);
  background: rgba(255,255,255,0.03);
}
.banner--warn { border-color: rgba(245,158,11,0.35); background: rgba(245,158,11,0.10); color: rgba(255, 240, 205, 0.95); }

.composer {
  display: flex;
  gap: 10px;
  align-items: flex-end;
}

.composer__field {
  flex: 1;
  position: relative;
}

.composer__input {
  width: 100%;
  resize: none;
  min-height: 46px;
  max-height: 140px;
  border-radius: 16px;
  border: 1px solid var(--border);
  background: rgba(0,0,0,0.18);
  color: var(--text);
  padding: 12px 44px 12px 12px;
  line-height: 1.5;
  box-shadow: 0 1px 0 rgba(255,255,255,0.04) inset;
}
.composer__input:focus {
  outline: none;
  border-color: rgba(109,94,252,0.55);
  box-shadow: 0 0 0 4px rgba(109,94,252,0.18);
}
.composer__input:disabled { opacity: 0.6; cursor: not-allowed; }

.composer__meta {
  position: absolute;
  right: 12px;
  bottom: 10px;
}

.counter {
  font-size: 0.72rem;
  color: var(--muted2);
}
.counter--warn { color: rgba(255, 240, 205, 0.95); }

.spinner {
  width: 18px; height: 18px;
  border-radius: 999px;
  border: 2px solid rgba(255,255,255,0.30);
  border-top-color: rgba(255,255,255,0.90);
  display: inline-block;
  animation: spin 0.75s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

.hint {
  margin-top: 10px;
  color: var(--muted2);
  font-size: 0.78rem;
}
.hint code {
  border: 1px solid var(--border);
  background: rgba(0,0,0,0.18);
  padding: 2px 6px;
  border-radius: 10px;
  color: rgba(255,255,255,0.84);
}

.srOnly {
  position: absolute !important;
  width: 1px !important;
  height: 1px !important;
  padding: 0 !important;
  margin: -1px !important;
  overflow: hidden !important;
  clip: rect(0,0,0,0) !important;
  white-space: nowrap !important;
  border: 0 !important;
}

/* Reduce motion */
@media (prefers-reduced-motion: reduce) {
  * { animation: none !important; transition: none !important; scroll-behavior: auto !important; }
}
</style>