<template>
  <div>
    <div class="chat-container" role="log" aria-live="polite">
      <div v-for="(m, i) in messages" :key="i" :class="['chat-message', m.role === 'user' ? 'user' : 'assistant']">
        <div class="chat-message-header">{{ m.role }}</div>
        <div class="chat-message-content" v-html="formatMessage(m.content)"></div>
      </div>
    </div>

    <form @submit.prevent="send" style="display:flex; gap:8px; margin-top: var(--space-md);">
      <input v-model="input" class="form-input" placeholder="Ask RET about your dataset or conversion steps..." aria-label="Chat input" :disabled="!sessionId" />
      <button class="btn btn-primary" :disabled="sending || !sessionId">
        <span v-if="sending" class="spinner" style="margin-right:4px"></span>
        Send
      </button>
    </form>

    <p v-if="!sessionId" class="text-muted" style="margin-top: var(--space-sm); font-size: 0.875rem;">
      ⚠️ No session active. Please scan a ZIP file first.
    </p>

    <!-- Query Plan (if available) -->
    <details v-if="lastQueryPlan" style="margin-top: var(--space-md)">
      <summary style="cursor:pointer; color: var(--primary)">🔍 Query Plan</summary>
      <div style="margin-top: var(--space-sm); padding: var(--space-sm); background: var(--bg-alt); border-radius: var(--radius);">
        <div v-for="(step, idx) in lastQueryPlan.steps || []" :key="idx" style="margin-bottom: var(--space-xs)">
          <strong>{{ step.intent }}:</strong> {{ step.description }}
        </div>
      </div>
    </details>

    <!-- Retrievals -->
    <details v-if="retrievals.length > 0" style="margin-top: var(--space-md)">
      <summary style="cursor:pointer; color: var(--primary)">📚 Retrieval Inspector ({{ retrievals.length }} sources)</summary>
      <div class="data-table-wrapper" style="margin-top: var(--space-md)">
        <table class="data-table">
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
              <td>{{ r.doc }}</td>
              <td>
                <span :class="getScoreClass(r.score)">{{ r.score?.toFixed(3) || 'N/A' }}</span>
              </td>
              <td>{{ r.method || 'hybrid' }}</td>
              <td style="max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                {{ r.snippet }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </details>
  </div>
</template>

<script setup>
import { ref, watch, computed } from 'vue'
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

const messages = ref([
  { role: 'assistant', content: 'Hello — ask me about your indexed data, conversions, or analysis. I use hybrid RAG retrieval with citation enforcement.' }
])
const input = ref('')
const sending = ref(false)
const retrievals = ref([])
const lastQueryPlan = ref(null)

// Reset messages when session changes
watch(() => props.sessionId, () => {
  messages.value = [
    { role: 'assistant', content: 'Hello — ask me about your indexed data, conversions, or analysis. I use hybrid RAG retrieval with citation enforcement.' }
  ]
  retrievals.value = []
  lastQueryPlan.value = null
})

function getScoreClass(score) {
  if (!score) return ''
  if (score >= 0.8) return 'score-high'
  if (score >= 0.5) return 'score-medium'
  return 'score-low'
}

function formatMessage(content) {
  // Simple markdown-like formatting
  if (!content) return ''
  return escapeHtml(content)
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\n/g, '<br>')
}

async function send() {
  if (!input.value.trim() || !props.sessionId) return
  
  const userMessage = input.value.trim()
  messages.value.push({ role: 'user', content: userMessage })
  input.value = ''
  sending.value = true
  
  try {
    // Use advanced chat endpoint
    const resp = await api.post('/ai/chat/advanced', {
      session_id: props.sessionId,
      question: userMessage,
      use_rag: true,
      top_k: 8
    })
    
    const answer = resp.data.answer || resp.data.response || 'No response'
    messages.value.push({ role: 'assistant', content: answer })
    
    // Store retrievals
    const rawRetrievals = resp.data.retrievals || []
    retrievals.value = rawRetrievals.map((src) => ({
      doc: src.doc || src.file || src.source || 'unknown',
      score: typeof src.score === 'number' ? src.score : null,
      snippet: src.snippet || '',
      method: src.method || 'hybrid'
    }))
    
    // Store query plan if available
    lastQueryPlan.value = resp.data.query_plan || null
    
  } catch (e) {
    const errorMsg = e.response?.data?.detail || e.response?.data?.message || e.message
    messages.value.push({ role: 'assistant', content: '❌ Error: ' + errorMsg })
  } finally {
    sending.value = false
  }
}

function escapeHtml(unsafe) {
  return unsafe
    .replaceAll('&','&amp;')
    .replaceAll('<','&lt;')
    .replaceAll('>','&gt;')
}
</script>

<style scoped>
.score-high {
  color: var(--success, #10b981);
  font-weight: 600;
}
.score-medium {
  color: var(--warning, #f59e0b);
}
.score-low {
  color: var(--text-muted, #6b7280);
}
</style>

