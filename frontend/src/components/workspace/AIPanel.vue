<template>
  <section class="ret-ai" aria-label="RET AI Panel">
    <!-- Header -->
    <header class="ret-ai__header">
      <div class="ret-ai__titleBlock">
        <div class="ret-ai__titleRow">
          <span class="ret-ai__icon" aria-hidden="true">🤖</span>
          <h3 class="ret-ai__title">Ask RET AI</h3>
          <span class="ret-ai__badge">RAG</span>
        </div>
        <p class="ret-ai__subtitle">
          Hybrid retrieval (vector + keyword) over indexed documents for grounded answers and visualizations.
        </p>
      </div>

      <div class="ret-ai__headerRight">
        <div class="ret-ai__sessionPill" :class="sessionPillClass" role="status" aria-live="polite">
          <span class="ret-ai__dot" aria-hidden="true"></span>
          <span class="ret-ai__sessionText">{{ conversionSessionId ? 'Session Active' : 'No Session' }}</span>
        </div>
      </div>
    </header>

    <!-- Tools bar -->
    <div class="ret-ai__tools" role="toolbar" aria-label="Session tools">
      <div class="ret-ai__toolGroup">
        <span class="ret-ai__toolLabel">Session tools</span>

        <button class="btn btn--soft" type="button" @click="clearSessionMemory" :disabled="!conversionSessionId">
          <span aria-hidden="true">🗑️</span>
          <span>Clear memory</span>
        </button>

        <button class="btn btn--soft" type="button" @click="openInstructions">
          <span aria-hidden="true">📋</span>
          <span>Instructions</span>
        </button>

        <button class="btn btn--soft" type="button" @click="downloadTranscript" :disabled="messages.length === 0 || !conversionSessionId">
          <span aria-hidden="true">⬇️</span>
          <span>Download</span>
        </button>
      </div>

      <div class="ret-ai__toolGroup ret-ai__toolGroup--right">
        <div class="ret-ai__hintPill">
          Tip: <code>group="NAME"</code> • <code>top_k=8</code>
        </div>
      </div>
    </div>

    <!-- Body layout -->
    <div class="ret-ai__layout">
      <!-- Chat Column -->
      <div class="ret-ai__chatCard">
        <div class="ret-ai__chatHeader">
          <div class="ret-ai__chatHeaderLeft">
            <strong>Chat</strong>
            <span class="muted">• grounded answers with RAG</span>
          </div>

          <div class="ret-ai__chatHeaderRight">
            <button
              class="btn btn--ghost"
              type="button"
              @click="scrollToBottom(true)"
              :disabled="messages.length === 0"
              title="Scroll to latest"
            >
              ⬇️ Latest
            </button>
          </div>
        </div>

        <!-- Chat Area -->
        <div
          class="ret-ai__chat"
          ref="messagesContainer"
          role="log"
          aria-live="polite"
          aria-relevant="additions"
          tabindex="0"
          @scroll="onChatScroll"
        >
          <!-- Welcome -->
          <div v-if="messages.length === 0" class="welcome">
            <div class="welcome__icon" aria-hidden="true">🤖</div>
            <h4 class="welcome__title">Welcome to RET AI Assistant</h4>
            <p class="welcome__text">
              Ask anything about your indexed documents. I’ll retrieve relevant sources and generate grounded answers,
              including charts and tables when appropriate.
            </p>

            <div class="welcome__prompts">
              <div class="welcome__promptsLabel">Try asking:</div>
              <button class="pill" type="button" @click="sendQuickPrompt('Summarize the key findings in my documents')" :disabled="isTyping || !conversionSessionId">
                Summarize key findings
              </button>
              <button class="pill" type="button" @click="sendQuickPrompt('What are the main topics covered?')" :disabled="isTyping || !conversionSessionId">
                Main topics
              </button>
              <button class="pill" type="button" @click="sendQuickPrompt('Show me data patterns')" :disabled="isTyping || !conversionSessionId">
                Data patterns
              </button>
            </div>
          </div>

          <!-- Messages -->
          <article
            v-for="(msg, idx) in messages"
            :key="idx"
            class="msg"
            :class="msg.role === 'user' ? 'msg--user' : 'msg--assistant'"
          >
            <div class="msg__avatar" aria-hidden="true">{{ msg.role === 'user' ? '👤' : '🤖' }}</div>

            <div class="msg__card">
              <header class="msg__header">
                <div class="msg__meta">
                  <span class="msg__role">{{ msg.role === 'user' ? 'You' : 'RET AI' }}</span>
                  <time class="msg__time" :datetime="msg.timestamp">{{ formatTime(msg.timestamp) }}</time>
                  <span v-if="msg.responseType && msg.role === 'assistant'" class="badge">
                    {{ msg.responseType }}
                  </span>
                </div>

                <div class="msg__actions">
                  <button
                    class="iconBtn"
                    type="button"
                    @click="copyMessage(msg.content)"
                    title="Copy"
                    aria-label="Copy message"
                  >
                    📋
                  </button>
                </div>
              </header>

              <div class="msg__content">
                <MessageRenderer
                  :content="msg.content"
                  :role="msg.role"
                  @render-chart="handleChartRender"
                  @render-table="handleTableRender"
                  @render-stats="handleStatsRender"
                />
              </div>
            </div>
          </article>

          <!-- Typing -->
          <div v-if="isTyping" class="msg msg--assistant msg--typing" aria-label="Assistant is typing">
            <div class="msg__avatar" aria-hidden="true">🤖</div>
            <div class="msg__card">
              <div class="typing">
                <span></span><span></span><span></span>
              </div>
            </div>
          </div>
        </div>

        <!-- New messages floating button -->
        <button v-if="showNewMessages" class="newMsgBtn" type="button" @click="scrollToBottom(true)">
          New messages ↓
        </button>

        <!-- Input -->
        <div class="ret-ai__composer">
          <div class="composer">
            <label class="srOnly" for="chatInput">Message</label>
            <textarea
              id="chatInput"
              v-model="inputText"
              ref="inputField"
              class="composer__input"
              :placeholder="conversionSessionId ? 'Ask about your indexed documents…' : 'Convert files first to enable RAG…'"
              rows="1"
              :disabled="isTyping || !conversionSessionId"
              @keydown.enter.exact.prevent="sendMessage"
              @input="autoResize"
            ></textarea>

            <button class="btn btn--primary composer__send" type="button" @click="sendMessage" :disabled="!canSend">
              <span v-if="isTyping" class="spinner" aria-hidden="true"></span>
              <span v-else aria-hidden="true">➤</span>
              <span class="srOnly">Send</span>
            </button>
          </div>

          <div class="composer__footer">
            <span class="muted">Enter to send • Shift+Enter new line</span>
            <span class="counter" :class="{ 'counter--warn': inputText.length > 3500 }">
              {{ inputText.length }}/4000
            </span>
          </div>
        </div>
      </div>

      <!-- Right Column: RAG Inspector + Embedding -->
      <div class="ret-ai__side">
        <!-- RAG Inspector -->
        <section class="panel" v-if="retrievals.length" aria-label="RAG Retrieval Inspector">
          <header class="panel__header">
            <div class="panel__title">
              <span aria-hidden="true">🔍</span>
              <strong>Retrieval Inspector</strong>
              <span class="muted">• {{ retrievals.length }} retrieved</span>
            </div>

            <button class="btn btn--soft" type="button" @click="inspectorExpanded = !inspectorExpanded">
              {{ inspectorExpanded ? 'Collapse' : 'Expand' }}
            </button>
          </header>

          <div v-if="inspectorExpanded" class="panel__content">
            <div class="cards">
              <div v-for="(r, idx) in retrievals" :key="idx" class="source">
                <div class="source__top">
                  <span class="source__idx">#{{ idx + 1 }}</span>
                  <span class="source__doc" :title="r.doc">📄 {{ r.doc }}</span>
                  <span v-if="r.score != null" class="score" :class="getScoreClass(r.score)">
                    {{ Math.round(r.score * 100) }}%
                  </span>
                </div>
                <div v-if="r.group" class="source__meta"><span class="muted">Group:</span> {{ r.group }}</div>
                <p v-if="r.snippet" class="source__snippet">{{ truncateText(r.snippet, 220) }}</p>
              </div>
            </div>
          </div>
        </section>

        <!-- Embedding Status -->
        <section class="panel" aria-label="Embedding Status">
          <header class="panel__header">
            <div class="panel__title">
              <span aria-hidden="true">📊</span>
              <strong>Embedding Status</strong>
            </div>
          </header>

          <div class="panel__content">
            <p class="panel__desc">
              Manage which groups are embedded for AI retrieval. Auto-embedded groups are highlighted.
            </p>

            <div v-if="conversionSessionId" class="embed">
              <div class="embed__topRow">
                <div class="search">
                  <span class="search__icon" aria-hidden="true">🔎</span>
                  <input
                    v-model="groupSearch"
                    class="search__input"
                    type="text"
                    placeholder="Search groups…"
                    :disabled="loadingGroups || indexing"
                  />
                </div>

                <div class="embed__count muted">
                  {{ filteredGroupsWithStatus.length }} / {{ availableGroups.length }}
                </div>
              </div>

              <div class="embed__list" :class="{ 'is-loading': loadingGroups }">
                <div v-if="loadingGroups" class="loading">
                  <span class="spinner" aria-hidden="true"></span>
                  Loading groups…
                </div>

                <div v-else-if="filteredGroupsWithStatus.length === 0" class="empty">
                  <div class="empty__icon" aria-hidden="true">📂</div>
                  <div class="empty__title">No groups found</div>
                  <div class="empty__text">Try clearing search or convert files in Utility tab.</div>
                </div>

                <label
                  v-else
                  v-for="group in filteredGroupsWithStatus"
                  :key="group.name"
                  class="groupRow"
                  :class="{
                    'groupRow--indexed': group.isIndexed,
                    'groupRow--auto': group.isAutoEmbedded,
                    'groupRow--selected': selectedGroupsForIndex.includes(group.name)
                  }"
                >
                  <input
                    class="groupRow__check"
                    type="checkbox"
                    :value="group.name"
                    v-model="selectedGroupsForIndex"
                    :disabled="indexing || group.isAutoEmbedded"
                  />
                  <div class="groupRow__main">
                    <div class="groupRow__name">
                      {{ group.name }}
                      <span v-if="group.isAutoEmbedded" class="tag tag--auto">Auto</span>
                    </div>

                    <div class="groupRow__status">
                      <span v-if="group.isIndexed" class="tag tag--ok">
                        ✅ {{ group.chunkCount ? group.chunkCount + ' chunks' : 'Indexed' }}
                      </span>
                      <span v-else class="tag tag--muted">○ Not indexed</span>
                    </div>
                  </div>
                </label>
              </div>

              <div class="embed__actions">
                <button class="btn btn--soft btn--sm" type="button" @click="selectAllGroups" :disabled="indexing || !availableGroups.length">
                  Select all
                </button>
                <button class="btn btn--soft btn--sm" type="button" @click="selectAutoGroups" :disabled="indexing || !availableGroups.length">
                  Select auto
                </button>
                <button class="btn btn--ghost btn--sm" type="button" @click="clearGroupSelection" :disabled="indexing">
                  Clear
                </button>
              </div>

              <button
                class="btn btn--primary embed__indexBtn"
                type="button"
                @click="indexConvertedFiles"
                :disabled="indexing || selectedGroupsForIndex.length === 0"
              >
                <span v-if="indexing" class="spinner" aria-hidden="true"></span>
                {{ indexing ? 'Indexing…' : `🚀 Index ${selectedGroupsForIndex.length} group(s)` }}
              </button>

              <p v-if="indexedGroupsList.length > 0" class="callout">
                ✅ <strong>{{ indexedGroupsList.length }}</strong> group(s) indexed:
                <span class="callout__names">{{ indexedGroupsList.join(', ') }}</span>
              </p>
            </div>

            <div v-else class="empty">
              <div class="empty__icon" aria-hidden="true">ℹ️</div>
              <div class="empty__title">No conversion session</div>
              <div class="empty__text">
                Upload &amp; convert files in <strong>Utility</strong> tab to enable indexing and RAG chat.
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>

    <!-- Instructions Modal -->
    <div
      v-if="showInstructionsModal"
      class="modal"
      role="dialog"
      aria-modal="true"
      aria-label="Session instructions"
      @keydown.esc="closeInstructions"
      @click.self="closeInstructions"
    >
      <div class="modal__card" ref="modalCard" tabindex="-1">
        <header class="modal__header">
          <h4 class="modal__title">Session Instructions</h4>
          <button class="iconBtn" type="button" @click="closeInstructions" aria-label="Close modal">✕</button>
        </header>

        <div class="modal__body">
          <p class="muted">
            Instructions guide the AI’s behavior for this session (tone, formatting, focus, constraints).
            <br />
            <strong>Note:</strong> Stored locally (backend has no instructions endpoint).
          </p>
          <textarea
            v-model="sessionInstructions"
            class="modal__textarea"
            rows="7"
            placeholder="e.g. Answer in bullets, cite groups, prefer tables for numeric summaries…"
          ></textarea>
        </div>

        <footer class="modal__footer">
          <button class="btn btn--ghost" type="button" @click="closeInstructions">Cancel</button>
          <button class="btn btn--primary" type="button" @click="saveInstructions">Save</button>
        </footer>
      </div>
    </div>
  </section>
</template>

<script setup>
/**
 * AIPanel.vue — Backend-aligned version
 *
 * ✅ Removes /ai/session endpoints (not present in backend)
 * ✅ Uses rag_router endpoints under /v2/ai/*
 * ✅ Session key = conversion session id (required by backend ownership check)
 */

import { ref, nextTick, onMounted, onUnmounted, watch, computed, h, render } from 'vue'
import api from '@/utils/api'
import { useToastStore } from '@/stores/toastStore'
import MessageRenderer from './charts/MessageRenderer.vue'
import ChartRenderer from './charts/ChartRenderer.vue'
import DataTable from './charts/DataTable.vue'
import StatsCardGrid from './charts/StatsCardGrid.vue'

const props = defineProps({
  sessionId: { type: String, default: null }, // conversion session id
  scannedGroups: { type: Array, default: () => [] }
})

const emit = defineEmits(['message-sent', 'groups-indexed'])
const toast = useToastStore()

// ----- State -----
const messages = ref([])
const inputText = ref('')
const isTyping = ref(false)

const messagesContainer = ref(null)
const inputField = ref(null)
const modalCard = ref(null)

const retrievals = ref([])
const inspectorExpanded = ref(true)

const showInstructionsModal = ref(false)
const sessionInstructions = ref('')

// Backend requires an existing owned session_id → use conversion session id only.
const conversionSessionId = ref(null)

const availableGroups = ref([])          // all groups from API (+ scanned)
const selectedGroupsForIndex = ref([])   // selection for manual indexing
const loadingGroups = ref(false)
const indexing = ref(false)
const indexedGroupsList = ref([])        // which are already indexed
const groupChunkCounts = ref({})         // group -> chunks
const autoEmbeddedGroups = ref([])       // from API
const groupSearch = ref('')

let embedPollTimer = null

// Smart scroll behavior
const userNearBottom = ref(true)
const showNewMessages = ref(false)

// Track programmatic renders to clean up (avoid leaks)
const mountedVizIds = new Set()

// ----- Computeds -----
const canSend = computed(() => {
  return !!conversionSessionId.value && inputText.value.trim().length > 0 && !isTyping.value
})

const sessionPillClass = computed(() => ({
  'ret-ai__sessionPill--ok': !!conversionSessionId.value,
  'ret-ai__sessionPill--warn': !conversionSessionId.value
}))

const scannedGroupNames = computed(() => normalizeGroupNames(props.scannedGroups))

const groupsWithStatus = computed(() =>
  availableGroups.value.map(name => ({
    name,
    isIndexed: indexedGroupsList.value.includes(name),
    chunkCount: groupChunkCounts.value[name] || 0,
    isAutoEmbedded: autoEmbeddedGroups.value.map(x => String(x).toUpperCase()).includes(String(name).toUpperCase())
  }))
)

const filteredGroupsWithStatus = computed(() => {
  const q = groupSearch.value.trim().toLowerCase()
  if (!q) return groupsWithStatus.value
  return groupsWithStatus.value.filter(g => g.name.toLowerCase().includes(q))
})

// ----- Lifecycle -----
watch(
  () => props.sessionId,
  async (newVal) => {
    conversionSessionId.value = newVal || null

    // Reset UI state when session changes
    retrievals.value = []
    selectedGroupsForIndex.value = []
    indexedGroupsList.value = []
    groupChunkCounts.value = {}
    autoEmbeddedGroups.value = []
    availableGroups.value = []
    messages.value = []

    if (conversionSessionId.value) {
      loadLocalInstructions(conversionSessionId.value)
      await loadChatHistory()
      await loadSessionGroups()
      await nextTick()
      scrollToBottom(true)
    }
  },
  { immediate: true }
)

watch(
  () => props.scannedGroups,
  (newGroups) => {
    const names = normalizeGroupNames(newGroups)
    if (!names.length) return
    availableGroups.value = mergeGroupNames(availableGroups.value, names)
    refreshSelection()
  },
  { deep: true, immediate: true }
)

onMounted(async () => {
  // If session already exists on mount, watchers will load.
  watch(showInstructionsModal, async (open) => {
    if (open) {
      await nextTick()
      modalCard.value?.focus()
    }
  })
})

onUnmounted(() => {
  if (embedPollTimer) clearInterval(embedPollTimer)
  // Unmount any programmatic renders
  for (const id of mountedVizIds) {
    const el = document.getElementById(id)
    if (el) render(null, el)
  }
  mountedVizIds.clear()
})

// ----- Helpers -----
function normalizeGroupNames(groups) {
  if (!Array.isArray(groups)) return []
  return groups.map(g => (typeof g === 'string' ? g : g?.name)).filter(Boolean)
}

function mergeGroupNames(base, incoming) {
  return Array.from(new Set([...(base || []), ...(incoming || [])]))
}

function refreshSelection() {
  const availableSet = new Set(availableGroups.value)
  selectedGroupsForIndex.value = selectedGroupsForIndex.value.filter(g => availableSet.has(g))

  // If empty, pick first non-indexed, non-auto few groups for convenience
  if (!selectedGroupsForIndex.value.length) {
    const autoSet = new Set(autoEmbeddedGroups.value.map(x => String(x).toUpperCase()))
    selectedGroupsForIndex.value = availableGroups.value
      .filter(g => !autoSet.has(String(g).toUpperCase()))
      .filter(g => !indexedGroupsList.value.includes(g))
      .slice(0, 5)
  }
}

function formatTime(ts) {
  if (!ts) return ''
  const d = new Date(ts)
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
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

function autoResize() {
  const el = inputField.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 160) + 'px'
}

// Smart scroll
function onChatScroll() {
  const el = messagesContainer.value
  if (!el) return
  const threshold = 90
  const dist = el.scrollHeight - el.scrollTop - el.clientHeight
  userNearBottom.value = dist < threshold
  if (userNearBottom.value) showNewMessages.value = false
}

async function scrollToBottom(force = false) {
  await nextTick()
  const el = messagesContainer.value
  if (!el) return
  if (force || userNearBottom.value) {
    el.scrollTop = el.scrollHeight
    showNewMessages.value = false
  }
}

function sendQuickPrompt(prompt) {
  inputText.value = prompt
  sendMessage()
}

// group="My Group" group=my-group top_k=12
function parseModifiers(text) {
  let query = text
  let groupFilter = null
  let topK = 8

  const groupRegex = /group=(?:"([^"]+)"|'([^']+)'|([^\s]+))/i
  const gm = text.match(groupRegex)
  if (gm) {
    groupFilter = (gm[1] || gm[2] || gm[3] || '').trim()
    query = query.replace(groupRegex, '').trim()
  }

  const topKRegex = /top_k=(\d+)/i
  const km = text.match(topKRegex)
  if (km) {
    const n = parseInt(km[1], 10)
    if (!Number.isNaN(n)) topK = Math.max(1, Math.min(n, 50))
    query = query.replace(topKRegex, '').trim()
  }

  return { query, groupFilter, topK }
}

function normalizeVisualizationBlocks(text) {
  if (!text) return ''
  return text.replace(/```chart-data\s*\n([\s\S]*?)```/g, (_, jsonBlock) => `\n\n\`\`\`chart\n${jsonBlock}\n\`\`\`\n`)
}

// ----- Programmatic render mounts -----
async function renderIntoContainer(id, component, propsObj) {
  await nextTick()
  const el = document.getElementById(id)
  if (!el) return
  render(null, el)
  render(h(component, propsObj), el)
  mountedVizIds.add(id)
}

function handleChartRender({ id, config }) {
  if (!config || !config.type || !config.data) return
  renderIntoContainer(id, ChartRenderer, { chartConfig: config })
}

function handleTableRender({ id, config }) {
  if (!config || !Array.isArray(config.data)) return
  renderIntoContainer(id, DataTable, {
    data: config.data,
    columns: config.columns || [],
    title: config.title || null,
    sortable: config.sortable !== false,
    exportable: config.exportable !== false,
    showSummary: config.showSummary === true,
    summary: config.summary || null,
    maxRows: config.maxRows || 10,
    tableClass: config.tableClass || ''
  })
}

function handleStatsRender({ id, config }) {
  if (!config || !Array.isArray(config.stats)) return
  renderIntoContainer(id, StatsCardGrid, { stats: config.stats })
}

// ----- Backend-aligned: chat history -----
async function loadChatHistory() {
  if (!conversionSessionId.value) return
  try {
    const res = await api.get(`/v2/ai/chat/history/${conversionSessionId.value}`, { params: { limit: 100 } })
    const apiMsgs = res.data?.messages || []
    messages.value = apiMsgs.map(m => ({
      role: m.role || 'assistant',
      content: m.content || '',
      timestamp: m.timestamp || new Date().toISOString(),
      responseType: m.response_type || m.responseType || null,
      sources: m.sources || []
    }))
  } catch (e) {
    // If no history yet, that's fine.
    messages.value = []
  }
}

// ----- Chat send -----
async function sendMessage() {
  const text = inputText.value.trim()
  if (!text || isTyping.value) return

  if (!conversionSessionId.value) {
    toast.warning('Convert files first to enable AI chat.')
    return
  }

  messages.value.push({ role: 'user', content: text, timestamp: new Date().toISOString() })
  inputText.value = ''
  autoResize()

  if (userNearBottom.value) await scrollToBottom(true)

  isTyping.value = true

  try {
    const { query, groupFilter, topK } = parseModifiers(text)

    // Apply local session instructions (backend has no instructions endpoint)
    const finalQuery = (sessionInstructions.value || '').trim()
      ? `INSTRUCTIONS:\n${sessionInstructions.value.trim()}\n\nQUESTION:\n${query}`
      : query

    const res = await api.post('/v2/ai/chat', {
      session_id: conversionSessionId.value,
      message: finalQuery,
      group_filter: groupFilter,
      top_k: topK,
      use_rag: true
    })

    const answer = normalizeVisualizationBlocks(res.data.answer || '')
    const sources = res.data.sources || []
    const responseType = res.data.response_type || res.data.responseType || 'factual'

    messages.value.push({
      role: 'assistant',
      content: answer,
      timestamp: new Date().toISOString(),
      responseType,
      visualizations: res.data.visualizations || [],
      sources: sources.map(s => ({
        filename: s.file || s.source || s.doc || 'unknown',
        group: s.group || null,
        score: s.score ?? 0,
        snippet: s.snippet || ''
      }))
    })

    retrievals.value = sources.map(s => ({
      doc: s.file || s.source || s.doc || 'unknown',
      group: s.group || null,
      score: s.score,
      snippet: s.snippet || ''
    }))

    emit('message-sent', { text, response: res.data })
  } catch (e) {
    toast.error('Failed to get response: ' + (e.response?.data?.detail || e.message))
    messages.value.push({
      role: 'assistant',
      content: 'Sorry, I encountered an error processing your request. Please try again.',
      timestamp: new Date().toISOString()
    })
  } finally {
    isTyping.value = false
    if (userNearBottom.value) {
      await scrollToBottom(true)
    } else {
      showNewMessages.value = true
    }
  }
}

// ----- Tools -----
async function clearSessionMemory() {
  if (!conversionSessionId.value) return
  if (!confirm('Clear all chat history for this session?')) return

  try {
    await api.delete(`/v2/ai/chat/history/${conversionSessionId.value}`)
    messages.value = []
    retrievals.value = []
    toast.success('Session memory cleared')
  } catch (e) {
    toast.error('Failed to clear memory: ' + (e.response?.data?.detail || e.message))
  }
}

function openInstructions() {
  showInstructionsModal.value = true
}

function closeInstructions() {
  showInstructionsModal.value = false
}

function instructionsKey(sessionId) {
  return `ret_ai_instructions_${sessionId}`
}

function loadLocalInstructions(sessionId) {
  try {
    sessionInstructions.value = localStorage.getItem(instructionsKey(sessionId)) || ''
  } catch {
    sessionInstructions.value = ''
  }
}

async function saveInstructions() {
  if (!conversionSessionId.value) {
    toast.warning('No active conversion session to attach instructions.')
    return
  }

  try {
    localStorage.setItem(instructionsKey(conversionSessionId.value), sessionInstructions.value || '')
    showInstructionsModal.value = false
    toast.success('Instructions saved locally')
  } catch {
    toast.error('Failed to save instructions (storage blocked)')
  }
}

async function downloadTranscript() {
  if (!conversionSessionId.value) return
  try {
    const res = await api.post(
      '/v2/ai/transcript/download',
      {
        session_id: conversionSessionId.value,
        format: 'txt',
        include_sources: true
      },
      { responseType: 'blob' }
    )

    // Try to extract filename from Content-Disposition
    const cd = res.headers?.['content-disposition'] || ''
    const match = cd.match(/filename="([^"]+)"/)
    const filename = match?.[1] || `RET_transcript_${conversionSessionId.value}.txt`

    downloadBlob(res.data, filename)
  } catch (e) {
    toast.error('Transcript download failed: ' + (e.response?.data?.detail || e.message))
  }
}

function downloadBlob(data, filename) {
  const url = window.URL.createObjectURL(new Blob([data]))
  const link = document.createElement('a')
  link.href = url
  link.setAttribute('download', filename)
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.URL.revokeObjectURL(url)
}

async function copyMessage(content) {
  try {
    await navigator.clipboard.writeText(String(content ?? ''))
    toast.success('Copied to clipboard')
  } catch {
    toast.error('Copy failed (clipboard blocked)')
  }
}

// ----- Group selection -----
function selectAllGroups() {
  // Select all non-auto groups
  const autoSet = new Set(autoEmbeddedGroups.value.map(x => String(x).toUpperCase()))
  selectedGroupsForIndex.value = availableGroups.value.filter(g => !autoSet.has(String(g).toUpperCase()))
}
function selectAutoGroups() {
  // Auto groups are not selectable for manual indexing (backend skips them anyway),
  // but keeping this for UX if you later change backend behavior.
  toast.info('Auto-embedded groups are managed by admin and are not manually indexed.')
}
function clearGroupSelection() {
  selectedGroupsForIndex.value = []
}

// ----- Load groups -----
async function loadSessionGroups() {
  if (!conversionSessionId.value) return

  loadingGroups.value = true
  try {
    const res = await api.get('/v2/ai/embedding/groups', {
      params: { session_id: conversionSessionId.value }
    })

    const all = res.data.all_groups || res.data.groups || []
    const allNames = all.map(g => (typeof g === 'string' ? g : g?.name)).filter(Boolean)

    autoEmbeddedGroups.value = (res.data.auto_embedded_groups || []).map(x => String(x))
    availableGroups.value = mergeGroupNames(allNames, scannedGroupNames.value)

    // Build indexed list + chunk counts from all_groups
    const idx = []
    const counts = {}
    for (const g of all) {
      if (typeof g === 'object' && g?.name) {
        if (g.indexed) idx.push(g.name)
        counts[g.name] = g.chunk_count || 0
      }
    }
    indexedGroupsList.value = idx
    groupChunkCounts.value = counts

    refreshSelection()
  } catch (e) {
    console.error('Failed to load session groups:', e)
    availableGroups.value = scannedGroupNames.value
    selectedGroupsForIndex.value = []
    indexedGroupsList.value = []
    groupChunkCounts.value = {}
    refreshSelection()
  } finally {
    loadingGroups.value = false
  }
}

// ----- Index converted files -----
async function indexConvertedFiles() {
  if (!conversionSessionId.value) {
    toast.error('No conversion session available. Please convert files first.')
    return
  }
  if (!selectedGroupsForIndex.value.length) return

  // Strip auto-embedded groups (backend skips them; we avoid confusing UX)
  const autoSet = new Set(autoEmbeddedGroups.value.map(x => String(x).toUpperCase()))
  const groupsToIndex = selectedGroupsForIndex.value.filter(g => !autoSet.has(String(g).toUpperCase()))
  if (!groupsToIndex.length) {
    toast.info('Selected groups are auto-embedded or already managed by admin.')
    return
  }

  indexing.value = true
  try {
    const res = await api.post('/v2/ai/embedding/groups', {
      session_id: conversionSessionId.value,
      groups: groupsToIndex,
      background: true
    })

    if (res.data.status === 'queued' && res.data.task_id) {
      toast.info('Embedding started in background. This may take a few minutes…')
      startEmbeddingTaskPoll(res.data.task_id)
      return
    }

    // Non-background success response
    if (res.data.status === 'success') {
      const embedded = res.data.embedded_groups || []
      toast.success(`Embedding complete for ${embedded.length} group(s).`)
      await loadSessionGroups()
      emit('groups-indexed', embedded)
      selectedGroupsForIndex.value = []
      indexing.value = false
      return
    }

    toast.warning(res.data.message || 'Indexing response received, but status is unclear.')
    indexing.value = false
  } catch (e) {
    toast.error('Indexing failed: ' + (e.response?.data?.detail || e.message))
    indexing.value = false
  }
}

function startEmbeddingTaskPoll(taskId) {
  if (embedPollTimer) clearInterval(embedPollTimer)

  embedPollTimer = setInterval(async () => {
    try {
      const res = await api.get(`/v2/ai/embedding/tasks/${taskId}`)
      const status = res.data.status

      if (status === 'completed') {
        clearInterval(embedPollTimer)
        embedPollTimer = null
        indexing.value = false

        await loadSessionGroups()
        const completedGroups = res.data.groups || []
        emit('groups-indexed', completedGroups)
        selectedGroupsForIndex.value = []
        toast.success('Embedding complete! Your groups are ready for AI chat.')
      } else if (status === 'failed' || status === 'cancelled') {
        clearInterval(embedPollTimer)
        embedPollTimer = null
        indexing.value = false
        toast.error(`Embedding ${status}: ${res.data.error || 'Unknown error'}`)
      }
    } catch (e) {
      console.debug('Embedding task poll error:', e.message)
    }
  }, 2500)
}
</script>
<style scoped>
/* =========================
   Enterprise Tokens (fallbacks)
   ========================= */
.ret-ai {
  --bg0: var(--surface-base, #0b1220);
  --bg1: var(--surface-elevated, #0f1a2e);
  --bg2: var(--surface-active, #121f38);

  --text: var(--text-heading, rgba(255,255,255,0.92));
  --muted: var(--text-secondary, rgba(255,255,255,0.62));
  --muted2: var(--text-tertiary, rgba(255,255,255,0.48));

  --border: var(--border-light, rgba(255,255,255,0.10));
  --border2: var(--border-medium, rgba(255,255,255,0.14));

  --primary: var(--brand-primary, #6d5efc);
  --primary2: var(--brand-light, #8b7bff);
  --success: var(--success, #22c55e);
  --warn: var(--warning, #f59e0b);

  --r12: 12px;
  --r16: 16px;

  --shadow: var(--shadow-heavy, 0 10px 30px rgba(0,0,0,0.35));
  --shadow2: var(--shadow-medium, 0 6px 18px rgba(0,0,0,0.25));

  height: 100%;
  display: flex;
  flex-direction: column;
  border-radius: var(--r16);
  border: 1px solid var(--border);
  overflow: hidden;
  background:
    radial-gradient(1200px 600px at 20% -10%, rgba(109, 94, 252, 0.22), transparent 55%),
    radial-gradient(900px 500px at 110% 10%, rgba(34, 197, 94, 0.10), transparent 60%),
    linear-gradient(180deg, var(--bg0), var(--bg1));
  box-shadow: var(--shadow);
}

/* Header */
.ret-ai__header {
  padding: 14px 16px;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  border-bottom: 1px solid var(--border);
  background: linear-gradient(180deg, rgba(255,255,255,0.06), rgba(255,255,255,0.02));
  backdrop-filter: blur(10px);
}
.ret-ai__titleRow { display: flex; align-items: center; gap: 10px; }
.ret-ai__icon {
  width: 36px; height: 36px;
  border-radius: 14px;
  display: grid; place-items: center;
  border: 1px solid var(--border);
  background: rgba(255,255,255,0.04);
}
.ret-ai__title { margin: 0; font-size: 1.02rem; color: var(--text); letter-spacing: 0.2px; }
.ret-ai__badge {
  font-size: 0.72rem;
  font-weight: 800;
  padding: 3px 8px;
  border-radius: 999px;
  border: 1px solid rgba(109,94,252,0.35);
  background: rgba(109,94,252,0.14);
  color: rgba(230,226,255,0.95);
  text-transform: uppercase;
  letter-spacing: 0.08em;
}
.ret-ai__subtitle { margin: 6px 0 0; color: var(--muted); font-size: 0.85rem; line-height: 1.5; max-width: 78ch; }

.ret-ai__sessionPill {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: rgba(255,255,255,0.03);
  color: var(--muted);
}
.ret-ai__dot { width: 8px; height: 8px; border-radius: 999px; background: var(--warn); box-shadow: 0 0 0 4px rgba(245,158,11,0.15); }
.ret-ai__sessionPill--ok .ret-ai__dot { background: var(--success); box-shadow: 0 0 0 4px rgba(34,197,94,0.15); }

/* Tools */
.ret-ai__tools {
  padding: 10px 16px;
  display: flex;
  justify-content: space-between;
  gap: 12px;
  border-bottom: 1px solid var(--border);
  background: rgba(255,255,255,0.02);
}
.ret-ai__toolGroup { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.ret-ai__toolGroup--right { justify-content: flex-end; }
.ret-ai__toolLabel { color: var(--muted2); font-weight: 700; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.08em; margin-right: 4px; }
.ret-ai__hintPill {
  border: 1px solid var(--border);
  background: rgba(0,0,0,0.18);
  color: var(--muted);
  padding: 7px 10px;
  border-radius: 999px;
  font-size: 0.78rem;
}
.ret-ai__hintPill code {
  background: rgba(255,255,255,0.05);
  padding: 2px 6px;
  border-radius: 10px;
  border: 1px solid var(--border);
  color: rgba(255,255,255,0.86);
}

/* Layout */
.ret-ai__layout {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 1.5fr 1fr;
  gap: 12px;
  padding: 12px;
}
@media (max-width: 980px) {
  .ret-ai__layout { grid-template-columns: 1fr; }
}

/* Chat Card */
.ret-ai__chatCard {
  position: relative;
  min-height: 0;
  display: flex;
  flex-direction: column;
  border-radius: var(--r16);
  border: 1px solid var(--border);
  background: rgba(255,255,255,0.02);
  overflow: hidden;
}
.ret-ai__chatHeader {
  padding: 10px 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  border-bottom: 1px solid var(--border);
  background: rgba(255,255,255,0.03);
}
.ret-ai__chat { flex: 1; min-height: 0; overflow: auto; padding: 14px; display: flex; flex-direction: column; gap: 12px; scroll-behavior: smooth; }

/* Messages */
.msg { display: flex; gap: 10px; width: min(900px, 100%); }
.msg--user { margin-left: auto; flex-direction: row-reverse; }
.msg__avatar {
  width: 40px; height: 40px;
  border-radius: 14px;
  display: grid; place-items: center;
  border: 1px solid var(--border);
  background: rgba(255,255,255,0.03);
}
.msg--user .msg__avatar {
  background: linear-gradient(135deg, rgba(109,94,252,0.9), rgba(139,123,255,0.8));
  border-color: rgba(255,255,255,0.22);
}
.msg__card {
  flex: 1;
  border-radius: 16px;
  border: 1px solid var(--border);
  background: rgba(255,255,255,0.03);
  padding: 10px 12px;
}
.msg--user .msg__card {
  background: linear-gradient(180deg, rgba(109,94,252,0.12), rgba(255,255,255,0.03));
  border-color: rgba(109,94,252,0.34);
}
.msg__header { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 6px; }
.msg__meta { display: flex; align-items: baseline; flex-wrap: wrap; gap: 8px; }
.msg__role { font-weight: 800; font-size: 0.86rem; color: var(--text); }
.msg__time { font-size: 0.74rem; color: var(--muted2); }
.msg__content { color: var(--muted); line-height: 1.65; }
.msg__actions { display: flex; gap: 6px; }

.badge {
  font-size: 0.72rem;
  font-weight: 800;
  padding: 2px 8px;
  border-radius: 999px;
  border: 1px solid rgba(109,94,252,0.35);
  background: rgba(109,94,252,0.12);
  color: rgba(230,226,255,0.95);
  text-transform: capitalize;
}

.iconBtn {
  width: 34px;
  height: 34px;
  border-radius: 12px;
  border: 1px solid var(--border);
  background: rgba(255,255,255,0.03);
  cursor: pointer;
  transition: background 0.12s ease, border-color 0.12s ease, transform 0.12s ease;
}
.iconBtn:hover { background: rgba(255,255,255,0.06); border-color: var(--border2); }
.iconBtn:active { transform: translateY(1px); }
.iconBtn:focus-visible { outline: 2px solid rgba(109,94,252,0.6); outline-offset: 2px; }

/* Typing */
.msg--typing .msg__card { padding: 14px 12px; }
.typing { display: inline-flex; gap: 6px; align-items: center; }
.typing span { width: 8px; height: 8px; border-radius: 999px; background: rgba(255,255,255,0.35); animation: bounce 1.1s infinite ease-in-out; }
.typing span:nth-child(2){ animation-delay: 0.12s; }
.typing span:nth-child(3){ animation-delay: 0.24s; }
@keyframes bounce { 0%,100%{ transform: translateY(0); opacity: 0.5; } 50%{ transform: translateY(-5px); opacity: 1; } }

/* Welcome */
.welcome {
  margin: 18px auto;
  width: min(720px, 100%);
  padding: 18px;
  border-radius: 18px;
  border: 1px solid var(--border);
  background: rgba(255,255,255,0.03);
  text-align: center;
}
.welcome__icon {
  width: 56px; height: 56px;
  margin: 0 auto 10px;
  border-radius: 18px;
  display: grid; place-items: center;
  background: rgba(109,94,252,0.14);
  border: 1px solid rgba(109,94,252,0.30);
}
.welcome__title { margin: 0; color: var(--text); }
.welcome__text { margin: 8px auto 0; color: var(--muted); line-height: 1.6; max-width: 62ch; }
.welcome__prompts { margin-top: 12px; display: flex; flex-wrap: wrap; justify-content: center; gap: 10px; }
.welcome__promptsLabel { width: 100%; color: var(--muted2); font-size: 0.82rem; }

.pill {
  padding: 8px 12px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: rgba(255,255,255,0.03);
  color: var(--muted);
  cursor: pointer;
  transition: background 0.12s ease, border-color 0.12s ease;
}
.pill:hover { background: rgba(109,94,252,0.10); border-color: rgba(109,94,252,0.30); color: var(--text); }
.pill:disabled { opacity: 0.55; cursor: not-allowed; }

/* Composer */
.ret-ai__composer { padding: 12px; border-top: 1px solid var(--border); background: rgba(255,255,255,0.02); }
.composer { display: flex; gap: 10px; align-items: flex-end; }
.composer__input {
  flex: 1;
  resize: none;
  min-height: 46px;
  max-height: 160px;
  border-radius: 16px;
  border: 1px solid var(--border);
  background: rgba(0,0,0,0.18);
  color: var(--text);
  padding: 12px 12px;
  line-height: 1.5;
}
.composer__input:focus {
  outline: none;
  border-color: rgba(109,94,252,0.55);
  box-shadow: 0 0 0 4px rgba(109,94,252,0.18);
}
.composer__send { width: 52px; height: 46px; border-radius: 16px; display: inline-flex; justify-content: center; align-items: center; }
.composer__footer { margin-top: 8px; display: flex; justify-content: space-between; font-size: 0.78rem; }
.counter { color: var(--muted2); }
.counter--warn { color: rgba(255, 240, 205, 0.95); }

/* Buttons */
.btn {
  border-radius: 12px;
  border: 1px solid var(--border);
  background: rgba(255,255,255,0.04);
  color: var(--text);
  padding: 9px 12px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  transition: transform 0.12s ease, background 0.12s ease, border-color 0.12s ease, opacity 0.12s ease;
}
.btn:hover { background: rgba(255,255,255,0.06); border-color: var(--border2); }
.btn:active { transform: translateY(1px); }
.btn:disabled { opacity: 0.55; cursor: not-allowed; }
.btn:focus-visible { outline: 2px solid rgba(109,94,252,0.65); outline-offset: 2px; }

.btn--primary {
  background: linear-gradient(135deg, var(--primary), var(--primary2));
  border-color: rgba(255,255,255,0.20);
}
.btn--ghost { background: transparent; }
.btn--soft { background: rgba(255,255,255,0.03); }
.btn--sm { padding: 7px 10px; font-size: 0.85rem; }

/* Side panel column */
.ret-ai__side { display: flex; flex-direction: column; gap: 12px; min-height: 0; }
.panel {
  border-radius: var(--r16);
  border: 1px solid var(--border);
  background: rgba(255,255,255,0.02);
  overflow: hidden;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.panel__header {
  padding: 10px 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  border-bottom: 1px solid var(--border);
  background: rgba(255,255,255,0.03);
}
.panel__title { display: flex; align-items: center; gap: 8px; color: var(--text); }
.panel__content { padding: 12px; overflow: auto; }
.panel__desc { margin: 0 0 10px; color: var(--muted); font-size: 0.86rem; line-height: 1.55; }

/* Inspector cards */
.cards { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
@media (max-width: 980px) { .cards { grid-template-columns: 1fr; } }
.source {
  border-radius: 14px;
  border: 1px solid var(--border);
  background: rgba(0,0,0,0.18);
  padding: 10px;
}
.source__top { display: flex; align-items: center; gap: 8px; }
.source__idx {
  width: 28px; height: 28px;
  border-radius: 10px;
  display: grid; place-items: center;
  border: 1px solid rgba(109,94,252,0.25);
  background: rgba(109,94,252,0.12);
  font-weight: 900;
  color: rgba(230,226,255,0.95);
}
.source__doc {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 800;
  color: var(--text);
  font-size: 0.86rem;
}
.source__meta { margin-top: 8px; color: var(--muted2); font-size: 0.8rem; }
.source__snippet { margin: 8px 0 0; color: var(--muted); font-size: 0.84rem; line-height: 1.5; }

.score {
  font-size: 0.76rem;
  font-weight: 900;
  padding: 3px 8px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: rgba(255,255,255,0.04);
  white-space: nowrap;
}
.score--high { border-color: rgba(34,197,94,0.35); background: rgba(34,197,94,0.12); color: rgba(196, 255, 219, 0.95); }
.score--mid  { border-color: rgba(245,158,11,0.35); background: rgba(245,158,11,0.12); color: rgba(255, 240, 205, 0.95); }
.score--low  { color: var(--muted2); }

/* Embedding list */
.embed { display: flex; flex-direction: column; gap: 10px; }
.embed__topRow { display: flex; align-items: center; gap: 10px; }
.embed__count { margin-left: auto; }

.search {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  border-radius: 14px;
  border: 1px solid var(--border);
  background: rgba(0,0,0,0.18);
  padding: 8px 10px;
}
.search__input {
  width: 100%;
  background: transparent;
  border: none;
  outline: none;
  color: var(--text);
}
.search__icon { color: var(--muted2); }

.embed__list {
  border-radius: 14px;
  border: 1px solid var(--border);
  background: rgba(0,0,0,0.12);
  overflow: auto;
  max-height: 320px;
}
.loading {
  padding: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: var(--muted2);
}
.groupRow {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px;
  cursor: pointer;
  border-bottom: 1px solid rgba(255,255,255,0.06);
}
.groupRow:last-child { border-bottom: none; }
.groupRow:hover { background: rgba(255,255,255,0.03); }
.groupRow--selected { background: rgba(109,94,252,0.10); }
.groupRow--indexed { border-left: 3px solid rgba(34,197,94,0.85); }
.groupRow--auto { border-left: 3px solid rgba(109,94,252,0.85); }

.groupRow__check { width: 18px; height: 18px; accent-color: var(--primary); }
.groupRow__main { flex: 1; display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.groupRow__name { font-weight: 800; color: var(--text); font-size: 0.88rem; display: flex; align-items: center; gap: 8px; }
.groupRow__status { display: flex; align-items: center; gap: 8px; }

.tag {
  font-size: 0.72rem;
  font-weight: 900;
  padding: 2px 8px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: rgba(255,255,255,0.04);
  color: var(--muted);
}
.tag--auto { border-color: rgba(109,94,252,0.35); background: rgba(109,94,252,0.14); color: rgba(230,226,255,0.95); }
.tag--ok { border-color: rgba(34,197,94,0.35); background: rgba(34,197,94,0.12); color: rgba(196, 255, 219, 0.95); }
.tag--muted { color: var(--muted2); }

.embed__actions { display: flex; gap: 10px; flex-wrap: wrap; }
.embed__indexBtn { width: 100%; justify-content: center; }

/* Callout */
.callout {
  margin: 0;
  padding: 10px;
  border-radius: 14px;
  border: 1px solid rgba(34,197,94,0.25);
  background: rgba(34,197,94,0.08);
  color: rgba(196, 255, 219, 0.95);
}
.callout__names { color: rgba(196, 255, 219, 0.95); font-weight: 700; }

/* Empty */
.empty {
  padding: 16px;
  text-align: center;
  color: var(--muted);
}
.empty__icon { font-size: 1.8rem; margin-bottom: 6px; }
.empty__title { font-weight: 900; color: var(--text); }
.empty__text { margin-top: 6px; color: var(--muted); line-height: 1.5; }

/* New messages button */
.newMsgBtn {
  position: absolute;
  right: 16px;
  bottom: 86px; /* above composer */
  border-radius: 999px;
  border: 1px solid rgba(109,94,252,0.35);
  background: rgba(109,94,252,0.18);
  color: rgba(255,255,255,0.92);
  padding: 10px 14px;
  cursor: pointer;
  box-shadow: var(--shadow2);
}
.newMsgBtn:hover { filter: brightness(1.06); }

/* Modal */
.modal {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.55);
  display: grid;
  place-items: center;
  z-index: 1200;
  padding: 18px;
}
.modal__card {
  width: min(720px, 96vw);
  border-radius: 18px;
  border: 1px solid var(--border);
  background: rgba(18,31,56,0.92);
  box-shadow: var(--shadow);
  outline: none;
}
.modal__header {
  padding: 12px 14px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid var(--border);
}
.modal__title { margin: 0; color: var(--text); }
.modal__body { padding: 14px; }
.modal__textarea {
  width: 100%;
  margin-top: 10px;
  border-radius: 16px;
  border: 1px solid var(--border);
  background: rgba(0,0,0,0.20);
  color: var(--text);
  padding: 12px;
  resize: vertical;
}
.modal__textarea:focus {
  outline: none;
  border-color: rgba(109,94,252,0.55);
  box-shadow: 0 0 0 4px rgba(109,94,252,0.18);
}
.modal__footer {
  padding: 12px 14px;
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  border-top: 1px solid var(--border);
}

/* Spinner */
.spinner {
  width: 18px; height: 18px;
  border-radius: 999px;
  border: 2px solid rgba(255,255,255,0.30);
  border-top-color: rgba(255,255,255,0.90);
  display: inline-block;
  animation: spin 0.75s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

.muted { color: var(--muted2); }

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

@media (prefers-reduced-motion: reduce) {
  * { animation: none !important; transition: none !important; scroll-behavior: auto !important; }
}
</style>