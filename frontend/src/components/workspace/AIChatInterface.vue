<template>
  <div class="ai-chat-interface">
    <!-- Chat Header with Stats -->
    <div class="chat-header">
      <div class="header-left">
        <span class="chat-icon">🤖</span>
        <div class="header-info">
          <h3 class="chat-title">RET AI Assistant</h3>
          <span class="chat-status" :class="{ connected: sessionId, offline: !sessionId }">
            {{ sessionId ? 'Connected' : 'No Session' }}
          </span>
        </div>
      </div>
      <div class="header-actions">
        <button v-if="indexStats.totalDocuments > 0" class="stats-badge" @click="showStats = !showStats">
          📊 {{ indexStats.totalDocuments }} docs / {{ indexStats.totalChunks }} chunks
        </button>
        <button class="btn-icon" @click="clearChat" title="Clear Chat">
          🗑️
        </button>
        <button class="btn-icon" @click="downloadTranscript" title="Download Transcript">
          📥
        </button>
      </div>
    </div>

    <!-- Index Stats Modal -->
    <div v-if="showStats" class="stats-panel">
      <div class="stats-grid">
        <div class="stat-item">
          <span class="stat-value">{{ indexStats.totalDocuments }}</span>
          <span class="stat-label">Documents</span>
        </div>
        <div class="stat-item">
          <span class="stat-value">{{ indexStats.totalChunks }}</span>
          <span class="stat-label">Chunks</span>
        </div>
        <div class="stat-item">
          <span class="stat-value">{{ indexStats.groups?.length || 0 }}</span>
          <span class="stat-label">Groups</span>
        </div>
      </div>
      <div v-if="indexStats.groups?.length" class="indexed-groups">
        <span class="groups-label">Indexed Groups:</span>
        <span v-for="g in indexStats.groups" :key="g" class="group-tag">{{ g }}</span>
      </div>
    </div>

    <!-- Messages Container -->
    <div class="chat-messages" ref="messagesContainer" role="log" aria-live="polite">
      <!-- Welcome Message -->
      <div v-if="messages.length === 1" class="welcome-state">
        <div class="welcome-icon-large">🤖</div>
        <h3>Welcome to RET AI</h3>
        <p>Ask questions about your indexed XML data. I use advanced RAG with citation support.</p>
        <div class="quick-prompts">
          <button 
            v-for="prompt in quickPrompts" 
            :key="prompt"
            class="quick-prompt-btn"
            @click="sendMessage(prompt)"
          >
            {{ prompt }}
          </button>
        </div>
      </div>

      <!-- Message List -->
      <div 
        v-for="(m, i) in messages" 
        :key="i" 
        :class="['chat-message', m.role]"
      >
        <div class="message-avatar">
          {{ m.role === 'user' ? '👤' : '🤖' }}
        </div>
        <div class="message-content-wrapper">
          <div class="message-header">
            <span class="message-role">{{ m.role === 'user' ? 'You' : 'RET AI' }}</span>
            <span class="message-time">{{ formatTime(m.timestamp) }}</span>
          </div>
          <div class="message-content" v-html="formatMessage(m.content)"></div>
          
          <!-- Sources for assistant messages -->
          <div v-if="m.role === 'assistant' && m.sources?.length" class="sources-section">
            <button class="sources-toggle" @click="m._expanded = !m._expanded">
              <span>📚 {{ m.sources.length }} Source{{ m.sources.length !== 1 ? 's' : '' }}</span>
              <span class="toggle-icon">{{ m._expanded ? '▲' : '▼' }}</span>
            </button>
            <div v-if="m._expanded" class="sources-list">
              <div v-for="(src, si) in m.sources" :key="si" class="source-item">
                <div class="source-header">
                  <span class="source-file">📄 {{ src.doc }}</span>
                  <span v-if="src.score" :class="['source-score', getScoreClass(src.score)]">
                    {{ (src.score * 100).toFixed(0) }}%
                  </span>
                </div>
                <div class="source-snippet">{{ truncateText(src.snippet, 200) }}</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Typing Indicator -->
      <div v-if="sending" class="chat-message assistant typing">
        <div class="message-avatar">🤖</div>
        <div class="message-content-wrapper">
          <div class="typing-indicator">
            <span></span><span></span><span></span>
          </div>
        </div>
      </div>
    </div>

    <!-- Query Plan & Retrievals Inspector -->
    <div v-if="lastQueryPlan || retrievals.length" class="inspector-panel">
      <div class="inspector-tabs">
        <button 
          :class="['tab-btn', { active: activeTab === 'plan' }]"
          @click="activeTab = 'plan'"
          v-if="lastQueryPlan"
        >
          🔍 Query Plan
        </button>
        <button 
          :class="['tab-btn', { active: activeTab === 'sources' }]"
          @click="activeTab = 'sources'"
          v-if="retrievals.length"
        >
          📚 Sources ({{ retrievals.length }})
        </button>
      </div>
      
      <div class="inspector-content">
        <!-- Query Plan Tab -->
        <div v-if="activeTab === 'plan' && lastQueryPlan" class="plan-content">
          <div v-for="(step, idx) in lastQueryPlan.steps || []" :key="idx" class="plan-step">
            <span class="step-number">{{ idx + 1 }}</span>
            <div class="step-content">
              <strong>{{ step.intent }}</strong>
              <p>{{ step.description }}</p>
            </div>
          </div>
        </div>
        
        <!-- Sources Tab -->
        <div v-if="activeTab === 'sources' && retrievals.length" class="sources-content">
          <table class="sources-table">
            <thead>
              <tr>
                <th>Source</th>
                <th>Score</th>
                <th>Method</th>
                <th>Snippet</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(r, idx) in retrievals" :key="idx">
                <td class="source-name">{{ r.doc }}</td>
                <td>
                  <span :class="['score-badge', getScoreClass(r.score)]">
                    {{ r.score ? (r.score * 100).toFixed(0) + '%' : 'N/A' }}
                  </span>
                </td>
                <td class="method-badge">{{ r.method || 'hybrid' }}</td>
                <td class="snippet-cell">{{ truncateText(r.snippet, 100) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- Input Area -->
    <div class="chat-input-area">
      <div v-if="!sessionId" class="session-warning">
        ⚠️ No session active. Please scan a ZIP file first.
      </div>
      <form @submit.prevent="handleSend" class="input-form">
        <div class="input-wrapper">
          <textarea
            ref="inputEl"
            v-model="input"
            class="chat-input"
            placeholder="Ask about your indexed data... (Enter to send, Shift+Enter for new line)"
            :disabled="!sessionId || sending"
            rows="1"
            @keydown.enter.exact.prevent="handleSend"
            @input="autoGrow"
          ></textarea>
          <div class="input-actions">
            <span class="char-count" :class="{ warning: input.length > 3500 }">
              {{ input.length }}/4000
            </span>
          </div>
        </div>
        <button 
          type="submit" 
          class="send-btn" 
          :disabled="!input.trim() || !sessionId || sending"
        >
          <span v-if="sending" class="btn-spinner"></span>
          <span v-else class="send-icon">➤</span>
        </button>
      </form>
      <div class="input-hints">
        Use <code>group=NAME</code> to filter • <code>top_k=N</code> to limit results
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, nextTick } from 'vue'
import api from '@/utils/api'

const props = defineProps({
  indexedGroups: {
    type: Array,
    default: () => []
  },
  sessionId: {
    type: String,
    default: null
  }
})

const emit = defineEmits(['chat-error', 'stats-updated'])

// State
const messages = ref([
  { 
    role: 'assistant', 
    content: 'Hello! I\'m your RET AI Assistant. Ask me about your indexed data, and I\'ll provide answers with source citations.',
    timestamp: new Date().toISOString()
  }
])
const input = ref('')
const sending = ref(false)
const retrievals = ref([])
const lastQueryPlan = ref(null)
const showStats = ref(false)
const activeTab = ref('sources')
const inputEl = ref(null)
const messagesContainer = ref(null)
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

// Load chat history and stats when session changes
watch(() => props.sessionId, async (newId) => {
  if (newId) {
    await Promise.all([
      loadChatHistory(),
      loadIndexStats()
    ])
  } else {
    resetChat()
  }
}, { immediate: true })

async function loadChatHistory() {
  try {
    const resp = await api.get(`/v2/ai/chat/history/${props.sessionId}`)
    if (resp.data?.history?.length) {
      messages.value = resp.data.history.map(m => ({
        ...m,
        timestamp: m.timestamp || new Date().toISOString()
      }))
    }
  } catch (e) {
    // History not available, start fresh
    resetChat()
  }
}

async function loadIndexStats() {
  try {
    const resp = await api.get(`/v2/ai/index/stats/${props.sessionId}`)
    indexStats.value = {
      totalDocuments: resp.data.total_documents || 0,
      totalChunks: resp.data.total_chunks || 0,
      groups: resp.data.groups || []
    }
    emit('stats-updated', indexStats.value)
  } catch (e) {
    // Stats not available
    indexStats.value = { totalDocuments: 0, totalChunks: 0, groups: [] }
  }
}

function resetChat() {
  messages.value = [
    { 
      role: 'assistant', 
      content: 'Hello! I\'m your RET AI Assistant. Ask me about your indexed data, and I\'ll provide answers with source citations.',
      timestamp: new Date().toISOString()
    }
  ]
  retrievals.value = []
  lastQueryPlan.value = null
}

function clearChat() {
  resetChat()
  // Also clear on server if needed
  if (props.sessionId) {
    api.delete(`/v2/ai/chat/history/${props.sessionId}`).catch(() => {})
  }
}

async function handleSend() {
  const text = input.value.trim()
  if (!text || !props.sessionId || sending.value) return
  await sendMessage(text)
}

async function sendMessage(text) {
  // Parse query modifiers
  let query = text
  let groupFilter = null
  let topK = 8
  
  const groupMatch = text.match(/group=(\w+)/i)
  if (groupMatch) {
    groupFilter = groupMatch[1]
    query = query.replace(/group=\w+/i, '').trim()
  }
  
  const topKMatch = text.match(/top_k=(\d+)/i)
  if (topKMatch) {
    topK = parseInt(topKMatch[1])
    query = query.replace(/top_k=\d+/i, '').trim()
  }
  
  // Add user message
  messages.value.push({ 
    role: 'user', 
    content: text,
    timestamp: new Date().toISOString()
  })
  
  input.value = ''
  sending.value = true
  scrollToBottom()
  
  try {
    // Use the new RAG chat endpoint
    const resp = await api.post('/v2/ai/chat', {
      session_id: props.sessionId,
      question: query,
      group_filter: groupFilter,
      top_k: topK,
      use_rag: true
    })
    
    const answer = resp.data.answer || resp.data.response || 'No response received.'
    const sources = resp.data.sources || resp.data.retrievals || []
    
    messages.value.push({ 
      role: 'assistant', 
      content: answer,
      sources: sources.map(s => ({
        doc: s.source || s.doc || s.file || 'unknown',
        score: s.score,
        snippet: s.snippet || s.content || '',
        method: s.method || 'hybrid'
      })),
      timestamp: new Date().toISOString(),
      _expanded: false
    })
    
    // Update retrievals for inspector
    retrievals.value = sources.map(s => ({
      doc: s.source || s.doc || s.file || 'unknown',
      score: s.score,
      snippet: s.snippet || s.content || '',
      method: s.method || 'hybrid'
    }))
    
    // Store query plan
    lastQueryPlan.value = resp.data.query_plan || null
    
  } catch (e) {
    const errorMsg = e.response?.data?.detail || e.message || 'An error occurred'
    messages.value.push({ 
      role: 'assistant', 
      content: `❌ **Error:** ${errorMsg}`,
      timestamp: new Date().toISOString()
    })
    emit('chat-error', errorMsg)
  } finally {
    sending.value = false
    scrollToBottom()
  }
}

async function downloadTranscript() {
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
  } catch (e) {
    // Fallback: create local transcript
    const transcript = messages.value.map(m => 
      `## ${m.role === 'user' ? 'You' : 'RET AI'}\n${m.content}\n`
    ).join('\n---\n\n')
    
    const blob = new Blob([transcript], { type: 'text/markdown' })
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.setAttribute('download', 'chat_transcript.md')
    document.body.appendChild(link)
    link.click()
    link.remove()
  }
}

function formatMessage(content) {
  if (!content) return ''
  return escapeHtml(content)
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\[source:(\d+)\]/g, '<span class="citation">[source:$1]</span>')
    .replace(/\n/g, '<br>')
}

function formatTime(ts) {
  if (!ts) return ''
  const date = new Date(ts)
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function truncateText(text, maxLen) {
  if (!text) return ''
  return text.length > maxLen ? text.slice(0, maxLen) + '...' : text
}

function getScoreClass(score) {
  if (!score) return ''
  if (score >= 0.8) return 'score-high'
  if (score >= 0.5) return 'score-medium'
  return 'score-low'
}

function escapeHtml(unsafe) {
  if (!unsafe) return ''
  return unsafe
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

function autoGrow() {
  const el = inputEl.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 120) + 'px'
}

async function scrollToBottom() {
  await nextTick()
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
}

onMounted(() => {
  scrollToBottom()
})
</script>

<style scoped>
.ai-chat-interface {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--bg-panel, #1a1a2e);
  border-radius: var(--radius-lg, 12px);
  overflow: hidden;
}

/* Header */
.chat-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-md, 16px);
  background: linear-gradient(135deg, var(--bg-alt, #16213e), var(--bg-panel, #1a1a2e));
  border-bottom: 1px solid var(--border-color, #2a2a4a);
}

.header-left {
  display: flex;
  align-items: center;
  gap: var(--space-sm, 8px);
}

.chat-icon {
  font-size: 1.8rem;
}

.chat-title {
  margin: 0;
  font-size: 1.1rem;
  font-weight: 600;
}

.chat-status {
  font-size: 0.75rem;
  padding: 2px 8px;
  border-radius: var(--radius-full, 9999px);
}

.chat-status.connected {
  background: var(--success-subtle, #10b98120);
  color: var(--success, #10b981);
}

.chat-status.offline {
  background: var(--warning-subtle, #f59e0b20);
  color: var(--warning, #f59e0b);
}

.header-actions {
  display: flex;
  gap: var(--space-sm, 8px);
  align-items: center;
}

.stats-badge {
  background: var(--bg-alt, #16213e);
  border: 1px solid var(--border-color, #2a2a4a);
  color: var(--text-secondary, #a0a0c0);
  padding: 6px 12px;
  border-radius: var(--radius-full, 9999px);
  font-size: 0.8rem;
  cursor: pointer;
  transition: all 0.2s;
}

.stats-badge:hover {
  background: var(--primary-subtle, #4f46e520);
  border-color: var(--primary, #4f46e5);
}

.btn-icon {
  width: 36px;
  height: 36px;
  border-radius: var(--radius, 8px);
  background: transparent;
  border: 1px solid var(--border-color, #2a2a4a);
  cursor: pointer;
  font-size: 1rem;
  transition: all 0.2s;
}

.btn-icon:hover {
  background: var(--bg-alt, #16213e);
}

/* Stats Panel */
.stats-panel {
  padding: var(--space-md, 16px);
  background: var(--bg-alt, #16213e);
  border-bottom: 1px solid var(--border-color, #2a2a4a);
}

.stats-grid {
  display: flex;
  gap: var(--space-lg, 24px);
  margin-bottom: var(--space-sm, 8px);
}

.stat-item {
  display: flex;
  flex-direction: column;
}

.stat-value {
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--primary, #4f46e5);
}

.stat-label {
  font-size: 0.75rem;
  color: var(--text-muted, #6b7280);
  text-transform: uppercase;
}

.indexed-groups {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-xs, 4px);
  align-items: center;
}

.groups-label {
  font-size: 0.8rem;
  color: var(--text-muted, #6b7280);
  margin-right: var(--space-sm, 8px);
}

.group-tag {
  background: var(--primary-subtle, #4f46e520);
  color: var(--primary, #4f46e5);
  padding: 2px 10px;
  border-radius: var(--radius-full, 9999px);
  font-size: 0.75rem;
}

/* Messages */
.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-md, 16px);
  display: flex;
  flex-direction: column;
  gap: var(--space-md, 16px);
}

.welcome-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: var(--space-2xl, 48px);
  color: var(--text-secondary, #a0a0c0);
}

.welcome-icon-large {
  font-size: 3rem;
  margin-bottom: var(--space-md, 16px);
  animation: float 3s ease-in-out infinite;
}

@keyframes float {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-8px); }
}

.welcome-state h3 {
  margin: 0 0 var(--space-sm, 8px);
  color: var(--text-primary, #e0e0f0);
}

.welcome-state p {
  max-width: 400px;
  line-height: 1.6;
}

.quick-prompts {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-sm, 8px);
  margin-top: var(--space-lg, 24px);
  justify-content: center;
}

.quick-prompt-btn {
  padding: var(--space-sm, 8px) var(--space-md, 16px);
  background: var(--bg-alt, #16213e);
  border: 1px solid var(--border-color, #2a2a4a);
  border-radius: var(--radius-full, 9999px);
  color: var(--text-secondary, #a0a0c0);
  cursor: pointer;
  font-size: 0.85rem;
  transition: all 0.2s;
}

.quick-prompt-btn:hover {
  background: var(--primary-subtle, #4f46e520);
  border-color: var(--primary, #4f46e5);
  color: var(--primary, #4f46e5);
}

/* Chat Message */
.chat-message {
  display: flex;
  gap: var(--space-sm, 8px);
  max-width: 85%;
  animation: slideIn 0.3s ease;
}

@keyframes slideIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

.chat-message.user {
  align-self: flex-end;
  flex-direction: row-reverse;
}

.chat-message.assistant {
  align-self: flex-start;
}

.message-avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: var(--bg-alt, #16213e);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.2rem;
  flex-shrink: 0;
}

.chat-message.user .message-avatar {
  background: linear-gradient(135deg, var(--primary, #4f46e5), var(--primary-light, #818cf8));
}

.message-content-wrapper {
  background: var(--bg-alt, #16213e);
  border-radius: var(--radius-lg, 12px);
  padding: var(--space-sm, 8px) var(--space-md, 16px);
  border: 1px solid var(--border-color, #2a2a4a);
}

.chat-message.user .message-content-wrapper {
  background: linear-gradient(135deg, var(--primary-subtle, #4f46e520), var(--bg-alt, #16213e));
  border-color: var(--primary, #4f46e5);
}

.message-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-xs, 4px);
  gap: var(--space-md, 16px);
}

.message-role {
  font-weight: 600;
  font-size: 0.85rem;
  color: var(--text-primary, #e0e0f0);
}

.message-time {
  font-size: 0.7rem;
  color: var(--text-muted, #6b7280);
}

.message-content {
  line-height: 1.6;
  color: var(--text-secondary, #a0a0c0);
}

.message-content :deep(code) {
  background: var(--bg-panel, #1a1a2e);
  padding: 2px 6px;
  border-radius: 4px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.9em;
}

.message-content :deep(.citation) {
  background: var(--primary-subtle, #4f46e520);
  color: var(--primary, #4f46e5);
  padding: 2px 6px;
  border-radius: 4px;
  font-weight: 600;
  font-size: 0.85em;
}

/* Sources Section */
.sources-section {
  margin-top: var(--space-sm, 8px);
  padding-top: var(--space-sm, 8px);
  border-top: 1px solid var(--border-color, #2a2a4a);
}

.sources-toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: var(--space-xs, 4px);
  background: transparent;
  border: none;
  cursor: pointer;
  color: var(--text-muted, #6b7280);
  font-size: 0.85rem;
}

.sources-toggle:hover {
  color: var(--primary, #4f46e5);
}

.sources-list {
  margin-top: var(--space-sm, 8px);
  display: flex;
  flex-direction: column;
  gap: var(--space-sm, 8px);
}

.source-item {
  background: var(--bg-panel, #1a1a2e);
  border-radius: var(--radius, 8px);
  padding: var(--space-sm, 8px);
}

.source-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-xs, 4px);
}

.source-file {
  font-size: 0.8rem;
  font-weight: 600;
}

.source-score {
  font-size: 0.75rem;
  padding: 2px 6px;
  border-radius: var(--radius, 8px);
}

.source-snippet {
  font-size: 0.8rem;
  color: var(--text-muted, #6b7280);
  line-height: 1.4;
}

/* Typing Indicator */
.chat-message.typing .message-content-wrapper {
  padding: var(--space-md, 16px);
}

.typing-indicator {
  display: flex;
  gap: 4px;
}

.typing-indicator span {
  width: 8px;
  height: 8px;
  background: var(--text-muted, #6b7280);
  border-radius: 50%;
  animation: typing 1.4s ease-in-out infinite;
}

.typing-indicator span:nth-child(1) { animation-delay: 0s; }
.typing-indicator span:nth-child(2) { animation-delay: 0.2s; }
.typing-indicator span:nth-child(3) { animation-delay: 0.4s; }

@keyframes typing {
  0%, 60%, 100% { transform: translateY(0); }
  30% { transform: translateY(-6px); }
}

/* Inspector Panel */
.inspector-panel {
  border-top: 1px solid var(--border-color, #2a2a4a);
  max-height: 200px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.inspector-tabs {
  display: flex;
  gap: var(--space-xs, 4px);
  padding: var(--space-sm, 8px);
  background: var(--bg-alt, #16213e);
}

.tab-btn {
  padding: var(--space-xs, 4px) var(--space-sm, 8px);
  border: none;
  background: transparent;
  color: var(--text-muted, #6b7280);
  cursor: pointer;
  border-radius: var(--radius, 8px);
  font-size: 0.85rem;
  transition: all 0.2s;
}

.tab-btn:hover {
  background: var(--bg-panel, #1a1a2e);
}

.tab-btn.active {
  background: var(--primary-subtle, #4f46e520);
  color: var(--primary, #4f46e5);
}

.inspector-content {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-sm, 8px);
}

.plan-content {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm, 8px);
}

.plan-step {
  display: flex;
  gap: var(--space-sm, 8px);
  align-items: flex-start;
}

.step-number {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--primary-subtle, #4f46e520);
  color: var(--primary, #4f46e5);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.8rem;
  flex-shrink: 0;
}

.step-content {
  font-size: 0.85rem;
}

.step-content p {
  margin: var(--space-xs, 4px) 0 0;
  color: var(--text-muted, #6b7280);
}

.sources-table {
  width: 100%;
  font-size: 0.8rem;
  border-collapse: collapse;
}

.sources-table th,
.sources-table td {
  padding: var(--space-xs, 4px) var(--space-sm, 8px);
  text-align: left;
  border-bottom: 1px solid var(--border-color, #2a2a4a);
}

.sources-table th {
  color: var(--text-muted, #6b7280);
  font-weight: 600;
}

.source-name {
  max-width: 150px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.score-badge {
  padding: 2px 8px;
  border-radius: var(--radius, 8px);
  font-size: 0.75rem;
}

.method-badge {
  text-transform: uppercase;
  font-size: 0.7rem;
  color: var(--text-muted, #6b7280);
}

.snippet-cell {
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-muted, #6b7280);
}

/* Input Area */
.chat-input-area {
  padding: var(--space-md, 16px);
  background: var(--bg-alt, #16213e);
  border-top: 1px solid var(--border-color, #2a2a4a);
}

.session-warning {
  padding: var(--space-sm, 8px);
  margin-bottom: var(--space-sm, 8px);
  background: var(--warning-subtle, #f59e0b20);
  border: 1px solid var(--warning, #f59e0b);
  border-radius: var(--radius, 8px);
  color: var(--warning, #f59e0b);
  font-size: 0.85rem;
  text-align: center;
}

.input-form {
  display: flex;
  gap: var(--space-sm, 8px);
  align-items: flex-end;
}

.input-wrapper {
  flex: 1;
  position: relative;
}

.chat-input {
  width: 100%;
  padding: var(--space-sm, 8px) var(--space-md, 16px);
  border: 2px solid var(--border-color, #2a2a4a);
  border-radius: var(--radius-lg, 12px);
  background: var(--bg-panel, #1a1a2e);
  color: var(--text-primary, #e0e0f0);
  font-family: inherit;
  font-size: 0.95rem;
  resize: none;
  min-height: 44px;
  max-height: 120px;
  transition: border-color 0.2s;
}

.chat-input:focus {
  outline: none;
  border-color: var(--primary, #4f46e5);
}

.chat-input::placeholder {
  color: var(--text-muted, #6b7280);
}

.chat-input:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.input-actions {
  position: absolute;
  bottom: 8px;
  right: 12px;
}

.char-count {
  font-size: 0.7rem;
  color: var(--text-muted, #6b7280);
}

.char-count.warning {
  color: var(--warning, #f59e0b);
}

.send-btn {
  width: 48px;
  height: 44px;
  border-radius: var(--radius-lg, 12px);
  background: linear-gradient(135deg, var(--primary, #4f46e5), var(--primary-light, #818cf8));
  color: white;
  border: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
  flex-shrink: 0;
}

.send-btn:hover:not(:disabled) {
  transform: scale(1.05);
  box-shadow: 0 4px 12px rgba(79, 70, 229, 0.4);
}

.send-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.send-icon {
  font-size: 1.2rem;
}

.btn-spinner {
  width: 18px;
  height: 18px;
  border: 2px solid transparent;
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.input-hints {
  margin-top: var(--space-xs, 4px);
  font-size: 0.75rem;
  color: var(--text-muted, #6b7280);
  padding: 0 var(--space-sm, 8px);
}

.input-hints code {
  background: var(--bg-panel, #1a1a2e);
  padding: 2px 4px;
  border-radius: 3px;
  font-family: monospace;
  font-size: 0.85em;
}

/* Score Classes */
.score-high {
  background: var(--success-subtle, #10b98120);
  color: var(--success, #10b981);
}

.score-medium {
  background: var(--warning-subtle, #f59e0b20);
  color: var(--warning, #f59e0b);
}

.score-low {
  background: var(--bg-alt, #16213e);
  color: var(--text-muted, #6b7280);
}
</style>

