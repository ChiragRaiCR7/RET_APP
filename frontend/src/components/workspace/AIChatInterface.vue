<template>
  <div>
    <div class="chat-container" role="log" aria-live="polite">
      <div v-for="(m, i) in messages" :key="i" :class="['chat-message', m.role === 'user' ? 'user' : 'assistant']">
        <div class="chat-message-header">{{ m.role }}</div>
        <div class="chat-message-content" v-html="m.content"></div>
      </div>
    </div>

    <form @submit.prevent="send" style="display:flex; gap:8px; margin-top: var(--space-md);">
      <input v-model="input" class="form-input" placeholder="Ask RET about your dataset or conversion steps..." aria-label="Chat input" :disabled="!sessionId" />
      <button class="btn btn-primary" :disabled="sending || !sessionId">Send</button>
    </form>

    <p v-if="!sessionId" class="text-muted" style="margin-top: var(--space-sm); font-size: 0.875rem;">
      ⚠️ No session active. Please scan a ZIP file first.
    </p>

    <details v-if="retrievals.length > 0" style="margin-top: var(--space-md)">
      <summary>Retrieval Inspector</summary>
      <div class="data-table-wrapper" style="margin-top: var(--space-md)">
        <table class="data-table">
          <thead><tr><th>Doc</th><th>Score</th><th>Snippet</th></tr></thead>
          <tbody>
            <tr v-for="(r, idx) in retrievals" :key="idx">
              <td>{{ r.doc }}</td>
              <td>{{ r.score?.toFixed(3) || 'N/A' }}</td>
              <td>{{ r.snippet }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </details>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
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
  { role: 'assistant', content: 'Hello — ask me about your indexed data, conversions, or analysis.' }
])
const input = ref('')
const sending = ref(false)
const retrievals = ref([])

// Reset messages when session changes
watch(() => props.sessionId, () => {
  messages.value = [
    { role: 'assistant', content: 'Hello — ask me about your indexed data, conversions, or analysis.' }
  ]
  retrievals.value = []
})

async function send() {
  if (!input.value.trim() || !props.sessionId) return
  
  const userMessage = input.value.trim()
  messages.value.push({ role: 'user', content: escapeHtml(userMessage) })
  input.value = ''
  sending.value = true
  
  try {
    const resp = await api.post('/ai/chat', {
      session_id: props.sessionId,
      question: userMessage
    })
    
    messages.value.push({ role: 'assistant', content: resp.data.answer || resp.data.response || 'No response' })
    const rawSources = resp.data.retrievals || resp.data.sources || []
    retrievals.value = rawSources.map((src) => ({
      doc: src.doc || src.file || src.source || 'unknown',
      score: typeof src.score === 'number' ? src.score : null,
      snippet: src.snippet || ''
    }))
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
