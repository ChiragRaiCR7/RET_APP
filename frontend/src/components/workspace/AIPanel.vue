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
                    'groupRow--excluded': group.isExcludedByAdmin,
                    'groupRow--selected': selectedGroupsForIndex.includes(group.name)
                  }"
                >
                  <input
                    class="groupRow__check"
                    type="checkbox"
                    :value="group.name"
                    v-model="selectedGroupsForIndex"
                    :disabled="indexing || group.isAutoEmbedded || group.isExcludedByAdmin"
                  />
                  <div class="groupRow__main">
                    <div class="groupRow__name">
                      <span v-if="indexing && selectedGroupsForIndex.includes(group.name) && !group.isIndexed" class="spinner spinner--inline" aria-hidden="true"></span>
                      {{ getGroupDisplayName(group.name) }}
                      <span
                        v-if="group.oracle_domain"
                        class="tag tag--domain"
                        :style="{ background: getDomainColor(group.oracle_domain), color: '#fff' }"
                      >{{ group.oracle_domain }}</span>
                      <span v-if="group.isAutoEmbedded" class="tag tag--auto">Auto</span>
                      <span v-if="group.isExcludedByAdmin" class="tag tag--danger">Excluded</span>
                    </div>

                    <div class="groupRow__status">
                      <span v-if="group.isExcludedByAdmin" class="tag tag--danger">🚫 Excluded by admin</span>
                      <span v-if="group.isIndexed" class="tag tag--ok">
                        ✅ {{ group.chunkCount ? group.chunkCount + ' chunks' : 'Indexed' }}
                      </span>
                      <span v-else-if="!group.isExcludedByAdmin" class="tag tag--muted">○ Not indexed</span>
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
                :disabled="indexing || stoppingIndexing || selectedGroupsForIndex.length === 0"
              >
                <span v-if="indexing" class="spinner" aria-hidden="true"></span>
                {{ indexing ? 'Indexing…' : `🚀 Index ${selectedGroupsForIndex.length} group(s)` }}
              </button>

              <button
                v-if="indexing"
                class="btn btn--danger btn--sm"
                type="button"
                @click="stopIndexing"
                :disabled="stoppingIndexing"
              >
                {{ stoppingIndexing ? 'Stopping…' : '⏹ Stop' }}
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

<script setup lang="ts">
/**
 * AIPanel.vue — Backend-aligned version
 *
 * ✅ Removes /ai/session endpoints (not present in backend)
 * ✅ Uses rag_router endpoints under /v2/ai/*
 * ✅ Session key = conversion session id (required by backend ownership check)
 */

import { ref, nextTick, onMounted, onUnmounted, watch, computed, h, render, type Component } from 'vue'
import api, { errorBody } from '@/utils/api'
import { useToastStore } from '@/stores/toastStore'
import { formatOracleGroupLabel, getOracleBusinessDomain, getDomainColor } from '@/utils/oracleApps'
import { normalizeGroupName } from '@/utils/groups'
import MessageRenderer from './charts/MessageRenderer.vue'
import ChartRenderer from './charts/ChartRenderer.vue'
import DataTable from './charts/DataTable.vue'
import StatsCardGrid from './charts/StatsCardGrid.vue'
import { toChartConfig, toStatCards, toTableProps } from '@/utils/vizConfig'
import type {
  ChatHistoryResponse,
  ChatResponse,
  EmbeddingGroupsResponse,
  EmbeddingTaskStatus,
  IndexGroupsResponse,
  RawChatSource,
  StopEmbeddingResponse
} from '@/types/api'

interface ChatSource {
  filename: string
  group: string | null
  score: number
  snippet: string
}

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  timestamp: string
  responseType?: string | null
  sources?: ChatSource[]
  visualizations?: unknown[]
}

interface Retrieval {
  doc: string
  group: string | null
  score?: number | null
  snippet: string
}

const EMBED_POLL_MS = 2500
// Stop polling after this many consecutive failed status checks (e.g. task lost on restart).
const EMBED_POLL_MAX_ERRORS = 8

const props = withDefaults(
  defineProps<{
    sessionId?: string | null // conversion session id
    scannedGroups?: (string | { name?: string })[]
  }>(),
  { sessionId: null, scannedGroups: () => [] }
)

const emit = defineEmits(['message-sent', 'groups-indexed'])
const toast = useToastStore()

// ----- State -----
const messages = ref<ChatMessage[]>([])
const inputText = ref('')
const isTyping = ref(false)

const messagesContainer = ref<HTMLElement | null>(null)
const inputField = ref<HTMLTextAreaElement | null>(null)
const modalCard = ref<HTMLElement | null>(null)

const retrievals = ref<Retrieval[]>([])
const inspectorExpanded = ref(true)

const showInstructionsModal = ref(false)
const sessionInstructions = ref('')

// Backend requires an existing owned session_id → use conversion session id only.
const conversionSessionId = ref<string | null>(null)

const availableGroups = ref<string[]>([])          // all groups from API (+ scanned)
const selectedGroupsForIndex = ref<string[]>([])   // selection for manual indexing
const loadingGroups = ref(false)
const indexing = ref(false)
const stoppingIndexing = ref(false)
const indexedGroupsList = ref<string[]>([])        // which are already indexed
const groupChunkCounts = ref<Record<string, number>>({})         // group -> chunks
const autoEmbeddedGroups = ref<string[]>([])       // from API
const adminExcludedGroups = ref<string[]>([])      // from API
const groupSearch = ref('')

let embedPollTimer: ReturnType<typeof setInterval> | null = null

// Smart scroll behavior
const userNearBottom = ref(true)
const showNewMessages = ref(false)

// Track programmatic renders to clean up (avoid leaks)
const mountedVizIds = new Set<string>()

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
    isAutoEmbedded: autoEmbeddedGroups.value.map(normalizeGroupName).includes(normalizeGroupName(name)),
    isExcludedByAdmin: adminExcludedGroups.value.map(normalizeGroupName).includes(normalizeGroupName(name)),
    oracle_domain: getOracleBusinessDomain(name)
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
    adminExcludedGroups.value = []
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
function toChatSource(s: RawChatSource): ChatSource {
  return {
    filename: s.file || s.source || s.doc || 'unknown',
    group: s.group || null,
    score: s.score ?? 0,
    snippet: s.snippet || ''
  }
}

function normalizeGroupNames(groups: unknown): string[] {
  if (!Array.isArray(groups)) return []
  return groups
    .map(g => (typeof g === 'string' ? g : (g as { name?: string } | null)?.name))
    .filter((name): name is string => !!name)
}

function getGroupDisplayName(group: string): string {
  return formatOracleGroupLabel(group)
}

function mergeGroupNames(base: string[], incoming: string[]): string[] {
  return Array.from(new Set([...(base || []), ...(incoming || [])]))
}

function refreshSelection() {
  const availableSet = new Set(availableGroups.value)
  selectedGroupsForIndex.value = selectedGroupsForIndex.value.filter(g => availableSet.has(g))

  // If empty, pick first non-indexed, non-auto few groups for convenience
  if (!selectedGroupsForIndex.value.length) {
    const autoSet = new Set(autoEmbeddedGroups.value.map(x => String(x).toUpperCase()))
    const excludedSet = new Set(adminExcludedGroups.value.map(x => String(x).toUpperCase()))
    selectedGroupsForIndex.value = availableGroups.value
      .filter(g => !autoSet.has(String(g).toUpperCase()))
      .filter(g => !excludedSet.has(String(g).toUpperCase()))
      .filter(g => !indexedGroupsList.value.includes(g))
      .slice(0, 5)
  }
}

function formatTime(ts: string | undefined): string {
  if (!ts) return ''
  const d = new Date(ts)
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function truncateText(text: string | undefined, maxLen: number): string {
  if (!text) return ''
  return text.length > maxLen ? text.slice(0, maxLen) + '…' : text
}

function getScoreClass(score: number | null | undefined): string {
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

function sendQuickPrompt(prompt: string) {
  inputText.value = prompt
  sendMessage()
}

// group="My Group" group=my-group top_k=12
function parseModifiers(text: string): { query: string; groupFilter: string | null; topK: number } {
  let query = text
  let groupFilter: string | null = null
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
    const n = parseInt(km[1] ?? '', 10)
    if (!Number.isNaN(n)) topK = Math.max(1, Math.min(n, 50))
    query = query.replace(topKRegex, '').trim()
  }

  return { query, groupFilter, topK }
}

function normalizeVisualizationBlocks(text: string): string {
  if (!text) return ''
  return text.replace(/```chart-data\s*\n([\s\S]*?)```/g, (_, jsonBlock: string) => `\n\n\`\`\`chart\n${jsonBlock}\n\`\`\`\n`)
}

// ----- Programmatic render mounts -----
interface VizPayload {
  id: string
  config: unknown
}

function _markVizError(id: string, msg: string) {
  nextTick().then(() => {
    const el = document.getElementById(id)
    if (!el) return
    // msg is always one of the fixed strings below, never model output.
    el.innerHTML = `<div class="viz-render-error"><span aria-hidden="true">⚠</span> ${msg}</div>`
  })
}

async function renderIntoContainer(id: string, component: Component, propsObj: Record<string, unknown>) {
  await nextTick()
  let el = document.getElementById(id)
  if (!el) {
    // Give the DOM one more animation frame to commit v-html output
    await new Promise(r => requestAnimationFrame(r))
    el = document.getElementById(id)
  }
  if (!el) return
  render(null, el)
  render(h(component, propsObj), el)
  mountedVizIds.add(id)
}

function handleChartRender({ id, config }: VizPayload) {
  const chartConfig = toChartConfig(config)
  if (!chartConfig) {
    _markVizError(id, 'Chart data unavailable')
    return
  }
  renderIntoContainer(id, ChartRenderer, { chartConfig })
}

function handleTableRender({ id, config }: VizPayload) {
  const table = toTableProps(config)
  if (!table) {
    _markVizError(id, 'Table data unavailable or empty')
    return
  }
  renderIntoContainer(id, DataTable, { ...table })
}

function handleStatsRender({ id, config }: VizPayload) {
  if (!config) return
  const stats = toStatCards(config)
  if (!stats) {
    _markVizError(id, 'No statistics data available')
    return
  }
  renderIntoContainer(id, StatsCardGrid, { stats })
}

// ----- Backend-aligned: chat history -----
async function loadChatHistory() {
  if (!conversionSessionId.value) return
  try {
    const res = await api.get<ChatHistoryResponse>(`/v2/ai/chat/history/${conversionSessionId.value}`, { params: { limit: 100 } })
    const apiMsgs = res.data?.messages || []
    messages.value = apiMsgs.map(m => ({
      role: m.role || 'assistant',
      content: m.content || '',
      timestamp: m.timestamp || new Date().toISOString(),
      responseType: m.response_type || m.responseType || null,
      sources: (m.sources || []).map(toChatSource)
    }))
  } catch {
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

    const res = await api.post<ChatResponse>('/v2/ai/chat', {
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
      sources: sources.map(toChatSource)
    })

    retrievals.value = sources.map((s: RawChatSource) => ({
      doc: s.file || s.source || s.doc || 'unknown',
      group: s.group || null,
      score: s.score,
      snippet: s.snippet || ''
    }))

    emit('message-sent', { text, response: res.data })
  } catch (e) {
    toast.error('Failed to get response: ' + (errorBody(e)?.detail || (e as Error).message))
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
    toast.error('Failed to clear memory: ' + (errorBody(e)?.detail || (e as Error).message))
  }
}

function openInstructions() {
  showInstructionsModal.value = true
}

function closeInstructions() {
  showInstructionsModal.value = false
}

function instructionsKey(sessionId: string): string {
  return `ret_ai_instructions_${sessionId}`
}

function loadLocalInstructions(sessionId: string) {
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
    toast.error('Transcript download failed: ' + (errorBody(e)?.detail || (e as Error).message))
  }
}

function downloadBlob(data: BlobPart, filename: string) {
  const url = window.URL.createObjectURL(new Blob([data]))
  const link = document.createElement('a')
  link.href = url
  link.setAttribute('download', filename)
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.URL.revokeObjectURL(url)
}

async function copyMessage(content: string) {
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
  const autoSet = new Set(autoEmbeddedGroups.value.map(normalizeGroupName))
  const excludedSet = new Set(adminExcludedGroups.value.map(normalizeGroupName))
  selectedGroupsForIndex.value = availableGroups.value.filter(
    g => !autoSet.has(normalizeGroupName(g)) && !excludedSet.has(normalizeGroupName(g))
  )
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
    const res = await api.get<EmbeddingGroupsResponse>('/v2/ai/embedding/groups', {
      params: { session_id: conversionSessionId.value }
    })

    const all = res.data.all_groups || res.data.groups || []
    const allNames = normalizeGroupNames(all)

    autoEmbeddedGroups.value = (res.data.auto_embedded_groups || []).map(x => String(x))
    adminExcludedGroups.value = (res.data.excluded_groups || []).map(x => String(x))
    availableGroups.value = mergeGroupNames(allNames, scannedGroupNames.value)

    // Build indexed list + chunk counts from all_groups
    const idx: string[] = []
    const counts: Record<string, number> = {}
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
  const autoSet = new Set(autoEmbeddedGroups.value.map(normalizeGroupName))
  const excludedSet = new Set(adminExcludedGroups.value.map(normalizeGroupName))
  const groupsToIndex = selectedGroupsForIndex.value.filter(
    g => !autoSet.has(normalizeGroupName(g)) && !excludedSet.has(normalizeGroupName(g))
  )
  if (!groupsToIndex.length) {
    toast.info('Selected groups are auto-embedded or excluded by admin.')
    return
  }

  indexing.value = true
  try {
    const res = await api.post<IndexGroupsResponse>('/v2/ai/embedding/groups', {
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
    toast.error('Indexing failed: ' + (errorBody(e)?.detail || (e as Error).message))
    indexing.value = false
  }
}

function stopEmbeddingPoll() {
  if (embedPollTimer) clearInterval(embedPollTimer)
  embedPollTimer = null
}

function startEmbeddingTaskPoll(taskId: string) {
  stopEmbeddingPoll()
  let consecutiveErrors = 0

  embedPollTimer = setInterval(async () => {
    try {
      const res = await api.get<EmbeddingTaskStatus>(`/v2/ai/embedding/tasks/${encodeURIComponent(taskId)}`)
      consecutiveErrors = 0
      const status = res.data.status

      if (status === 'completed') {
        stopEmbeddingPoll()
        indexing.value = false

        await loadSessionGroups()
        const completedGroups = res.data.groups || []
        emit('groups-indexed', completedGroups)
        selectedGroupsForIndex.value = []
        toast.success('Embedding complete! Your groups are ready for AI chat.')
      } else if (status === 'failed' || status === 'cancelled') {
        stopEmbeddingPoll()
        indexing.value = false
        toast.error(`Embedding ${status}: ${res.data.error || 'Unknown error'}`)
      }
    } catch (e) {
      consecutiveErrors += 1
      console.warn('Embedding status check failed:', (e as Error).message)
      if (consecutiveErrors >= EMBED_POLL_MAX_ERRORS) {
        stopEmbeddingPoll()
        indexing.value = false
        toast.error('Lost track of the embedding task. Reload the groups to see its current state.')
        await loadSessionGroups()
      }
    }
  }, EMBED_POLL_MS)
}

async function stopIndexing() {
  if (!conversionSessionId.value || stoppingIndexing.value) return
  stoppingIndexing.value = true

  try {
    const res = await api.post<StopEmbeddingResponse>(`/v2/ai/auto-embed/stop/${conversionSessionId.value}`)
    const stopped = Boolean(res?.data?.stopped)

    if (!stopped) {
      throw new Error(res?.data?.message || 'Stop request was not acknowledged by the server.')
    }

    if (embedPollTimer) {
      clearInterval(embedPollTimer)
      embedPollTimer = null
    }

    indexing.value = false

    const cancelled = Number(res?.data?.worker_tasks_cancelled || 0)
    const suppressed = Boolean(res?.data?.auto_embed_suppressed)

    let message = cancelled > 0
      ? `Embedding stopped. Cancelled ${cancelled} background task(s).`
      : 'Embedding stopped.'

    if (suppressed) {
      message += ' Auto-embedding is paused for this session until you manually index again.'
    }

    toast.info(message)
    await loadSessionGroups()
  } catch (e) {
    toast.error('Failed to stop embedding: ' + (errorBody(e)?.detail || (e as Error).message))
  } finally {
    stoppingIndexing.value = false
  }
}
</script>
<style scoped>
/* =========================
   Enterprise Tokens (fallbacks)
   ========================= */
.ret-ai {
  --bg0: var(--surface-base, #ffffff);
  --bg1: var(--surface-elevated, #f8fafc);
  --bg2: var(--surface-hover, #eef2f7);

  --text: var(--text-heading, #111827);
  --muted: var(--text-secondary, #374151);
  --muted2: var(--text-tertiary, #6b7280);

  --border: var(--border-light, #dbe3ee);
  --border2: var(--border-medium, #c4cfde);

  --primary: var(--brand-primary, #ffc000);
  --primary2: var(--brand-secondary, #f59e0b);
  --success: var(--success, #22c55e);
  --warn: var(--warning, #f59e0b);

  --r12: 12px;
  --r16: 16px;

  --shadow: var(--shadow-heavy, 0 18px 40px rgba(17, 24, 39, 0.14));
  --shadow2: var(--shadow-medium, 0 10px 24px rgba(17, 24, 39, 0.10));

  height: 100%;
  display: flex;
  flex-direction: column;
  border-radius: var(--r16);
  border: 1px solid var(--border);
  overflow: hidden;
  background:
    radial-gradient(1200px 600px at 20% -10%, color-mix(in srgb, var(--brand-primary), transparent 92%), transparent 55%),
    radial-gradient(900px 500px at 110% 10%, color-mix(in srgb, var(--info), transparent 94%), transparent 60%),
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
  background: linear-gradient(180deg, color-mix(in srgb, var(--brand-primary), transparent 96%), transparent);
  backdrop-filter: blur(10px);
}
.ret-ai__titleRow { display: flex; align-items: center; gap: 10px; }
.ret-ai__icon {
  width: 36px; height: 36px;
  border-radius: 14px;
  display: grid; place-items: center;
  border: 1px solid var(--border);
  background: var(--surface-elevated);
}
.ret-ai__title { margin: 0; font-size: 1.02rem; color: var(--text); letter-spacing: 0.2px; }
.ret-ai__badge {
  font-size: 0.72rem;
  font-weight: 800;
  padding: 3px 8px;
  border-radius: 999px;
  border: 1px solid color-mix(in srgb, var(--brand-primary), var(--border2) 55%);
  background: var(--brand-subtle);
  color: var(--text-heading);
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
  background: var(--surface-base);
  color: var(--muted);
}
.ret-ai__dot { width: 8px; height: 8px; border-radius: 999px; background: var(--warn); box-shadow: 0 0 0 4px color-mix(in srgb, var(--warning), transparent 80%); }
.ret-ai__sessionPill--ok .ret-ai__dot { background: var(--success); box-shadow: 0 0 0 4px color-mix(in srgb, var(--success), transparent 80%); }

/* Tools */
.ret-ai__tools {
  padding: 10px 16px;
  display: flex;
  justify-content: space-between;
  gap: 12px;
  border-bottom: 1px solid var(--border);
  background: var(--surface-base);
}
.ret-ai__toolGroup { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.ret-ai__toolGroup--right { justify-content: flex-end; }
.ret-ai__toolLabel { color: var(--muted2); font-weight: 700; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.08em; margin-right: 4px; }
.ret-ai__hintPill {
  border: 1px solid var(--border);
  background: var(--surface-elevated);
  color: var(--muted);
  padding: 7px 10px;
  border-radius: 999px;
  font-size: 0.78rem;
}
.ret-ai__hintPill code {
  background: var(--surface-base);
  padding: 2px 6px;
  border-radius: 10px;
  border: 1px solid var(--border);
  color: var(--text-primary);
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
  background: var(--surface-base);
  overflow: hidden;
}
.ret-ai__chatHeader {
  padding: 10px 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  border-bottom: 1px solid var(--border);
  background: var(--surface-elevated);
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
  background: var(--surface-elevated);
}
.msg--user .msg__avatar {
  background: linear-gradient(135deg, var(--brand-primary), var(--brand-secondary));
  border-color: var(--border2);
}
.msg__card {
  flex: 1;
  border-radius: 16px;
  border: 1px solid var(--border);
  background: var(--surface-elevated);
  padding: 10px 12px;
}
.msg--user .msg__card {
  background: color-mix(in srgb, var(--brand-subtle), var(--surface-elevated) 60%);
  border-color: var(--border-light);
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
  border: 1px solid color-mix(in srgb, var(--info), var(--border) 55%);
  background: var(--info-bg);
  color: var(--info);
  text-transform: capitalize;
}

.iconBtn {
  width: 34px;
  height: 34px;
  border-radius: 12px;
  border: 1px solid var(--border);
  background: var(--surface-base);
  cursor: pointer;
  transition: background 0.12s ease, border-color 0.12s ease, transform 0.12s ease;
}
.iconBtn:hover { background: var(--surface-hover); border-color: var(--border2); }
.iconBtn:active { transform: translateY(1px); }
.iconBtn:focus-visible { outline: 2px solid color-mix(in srgb, var(--brand-primary), transparent 25%); outline-offset: 2px; }

/* Typing */
.msg--typing .msg__card { padding: 14px 12px; }
.typing { display: inline-flex; gap: 6px; align-items: center; }
.typing span { width: 8px; height: 8px; border-radius: 999px; background: color-mix(in srgb, var(--brand-primary), transparent 35%); animation: bounce 1.1s infinite ease-in-out; }
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
  background: linear-gradient(180deg, color-mix(in srgb, var(--brand-subtle), var(--surface-base) 25%), var(--surface-elevated));
  text-align: center;
}
.welcome__icon {
  width: 56px; height: 56px;
  margin: 0 auto 10px;
  border-radius: 18px;
  display: grid; place-items: center;
  background: var(--brand-subtle);
  border: 1px solid color-mix(in srgb, var(--brand-primary), var(--border2) 55%);
}
.welcome__title { margin: 0; color: var(--text); }
.welcome__text { margin: 8px auto 0; color: var(--muted); line-height: 1.6; max-width: 62ch; }
.welcome__prompts { margin-top: 12px; display: flex; flex-wrap: wrap; justify-content: center; gap: 10px; }
.welcome__promptsLabel { width: 100%; color: var(--muted2); font-size: 0.82rem; }

.pill {
  padding: 8px 12px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: var(--surface-base);
  color: var(--muted);
  cursor: pointer;
  transition: background 0.12s ease, border-color 0.12s ease;
}
.pill:hover { background: var(--brand-subtle); border-color: color-mix(in srgb, var(--brand-primary), var(--border2) 50%); color: var(--text); }
.pill:disabled { opacity: 0.55; cursor: not-allowed; }

/* Composer */
.ret-ai__composer { padding: 12px; border-top: 1px solid var(--border); background: color-mix(in srgb, var(--surface-base), var(--surface-overlay) 45%); }
.composer { display: flex; gap: 10px; align-items: flex-end; }
.composer__input {
  flex: 1;
  resize: none;
  min-height: 46px;
  max-height: 160px;
  border-radius: 16px;
  border: 1px solid var(--border);
  background: var(--surface-base);
  color: var(--text);
  padding: 12px 12px;
  line-height: 1.5;
}
.composer__input:focus {
  outline: none;
  border-color: color-mix(in srgb, var(--brand-primary), var(--border2) 35%);
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--brand-primary), transparent 80%);
}
.composer__send { width: 52px; height: 46px; border-radius: 16px; display: inline-flex; justify-content: center; align-items: center; }
.composer__footer { margin-top: 8px; display: flex; justify-content: space-between; font-size: 0.78rem; }
.counter { color: var(--muted2); }
.counter--warn { color: var(--warning); }

/* Buttons */
.btn {
  border-radius: 12px;
  border: 1px solid var(--border);
  background: var(--surface-elevated);
  color: var(--text);
  padding: 9px 12px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  transition: transform 0.12s ease, background 0.12s ease, border-color 0.12s ease, opacity 0.12s ease;
}
.btn:hover { background: var(--surface-hover); border-color: var(--border2); box-shadow: var(--shadow-xs); }
.btn:active { transform: translateY(1px); }
.btn:disabled { opacity: 0.55; cursor: not-allowed; }
.btn:focus-visible { outline: 2px solid color-mix(in srgb, var(--brand-primary), transparent 25%); outline-offset: 2px; }

.btn--primary {
  background: linear-gradient(135deg, var(--primary), var(--primary2));
  border-color: color-mix(in srgb, var(--brand-primary), #000 8%);
  color: var(--brand-on);
}
.btn--ghost { background: transparent; }
.btn--soft { background: linear-gradient(180deg, var(--surface-base), var(--surface-raised)); }
.btn--sm { padding: 7px 10px; font-size: 0.85rem; }
.btn--danger { background: var(--error-bg); border-color: var(--error-border); color: var(--error); }
.btn--danger:hover { background: color-mix(in srgb, var(--error-bg), var(--surface-hover) 25%); }

/* Side panel column */
.ret-ai__side { display: flex; flex-direction: column; gap: 12px; min-height: 0; }
.panel {
  border-radius: var(--r16);
  border: 1px solid var(--border);
  background: var(--surface-base);
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
  background: var(--surface-elevated);
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
  background: var(--surface-elevated);
  padding: 10px;
}
.source__top { display: flex; align-items: center; gap: 8px; }
.source__idx {
  width: 28px; height: 28px;
  border-radius: 10px;
  display: grid; place-items: center;
  border: 1px solid color-mix(in srgb, var(--brand-primary), var(--border2) 55%);
  background: var(--brand-subtle);
  font-weight: 900;
  color: var(--text-heading);
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
  background: var(--surface-raised);
  white-space: nowrap;
}
.score--high { border-color: var(--success-border); background: var(--success-bg); color: var(--success); }
.score--mid  { border-color: var(--warning-border); background: var(--warning-bg); color: var(--warning); }
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
  background: var(--surface-base);
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
  background: var(--surface-base);
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
  border-bottom: 1px solid var(--border);
}
.groupRow:last-child { border-bottom: none; }
.groupRow:hover { background: var(--surface-hover); }
.groupRow--selected { background: var(--brand-subtle); }
.groupRow--indexed { border-left: 4px solid var(--success); background: color-mix(in srgb, var(--success), transparent 92%); }
.groupRow--auto { border-left: 3px solid var(--brand-primary); }
.groupRow--excluded { border-left: 3px solid var(--error); background: color-mix(in srgb, var(--error), transparent 92%); }

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
  background: var(--surface-elevated);
  color: var(--muted);
}
.tag--auto { border-color: color-mix(in srgb, var(--brand-primary), var(--border2) 55%); background: var(--brand-subtle); color: var(--text-heading); }
.tag--ok { border-color: var(--success-border); background: var(--success-bg); color: var(--success); }
.tag--muted { color: var(--muted2); }
.tag--danger { border-color: var(--error-border); background: var(--error-bg); color: var(--error); }
.tag--domain { border-color: transparent; font-size: 0.7rem; padding: 1px 6px; font-weight: 700; }

.embed__actions { display: flex; gap: 10px; flex-wrap: wrap; }
.embed__indexBtn { width: 100%; justify-content: center; }

/* Callout */
.callout {
  margin: 0;
  padding: 10px;
  border-radius: 14px;
  border: 1px solid var(--success-border);
  background: var(--success-bg);
  color: var(--success);
}
.callout__names { color: inherit; font-weight: 700; }

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
  border: 1px solid color-mix(in srgb, var(--brand-primary), var(--border2) 55%);
  background: color-mix(in srgb, var(--brand-subtle), var(--surface-base) 18%);
  color: var(--text-heading);
  padding: 10px 14px;
  cursor: pointer;
  box-shadow: var(--shadow2);
}
.newMsgBtn:hover { filter: brightness(1.06); }

/* Modal */
.modal {
  position: fixed;
  inset: 0;
  background: var(--scrim);
  display: grid;
  place-items: center;
  z-index: 1200;
  padding: 18px;
}
.modal__card {
  width: min(720px, 96vw);
  border-radius: 18px;
  border: 1px solid var(--border);
  background: var(--surface-elevated);
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
  background: var(--surface-base);
  color: var(--text);
  padding: 12px;
  resize: vertical;
}
.modal__textarea:focus {
  outline: none;
  border-color: color-mix(in srgb, var(--brand-primary), var(--border2) 35%);
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--brand-primary), transparent 80%);
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
  border: 2px solid color-mix(in srgb, var(--text-secondary), transparent 70%);
  border-top-color: var(--text-primary);
  display: inline-block;
  animation: spin 0.75s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
.spinner--inline { width: 12px; height: 12px; border-width: 1.5px; flex-shrink: 0; }

.muted { color: var(--muted2); }

/* Inline visualization error — shown when a block cannot render */
.viz-render-error {
  display: inline-flex;
  align-items: center;
  gap: 0.4em;
  padding: 0.5rem 0.9rem;
  background: var(--error-bg, rgba(220, 38, 38, 0.1));
  border: 1px solid var(--error-border, rgba(220, 38, 38, 0.25));
  border-radius: var(--r12, 10px);
  color: var(--error, #dc2626);
  font-size: 0.83rem;
  margin: 0.5rem 0;
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

@media (prefers-reduced-motion: reduce) {
  * { animation: none !important; transition: none !important; scroll-behavior: auto !important; }
}
</style>