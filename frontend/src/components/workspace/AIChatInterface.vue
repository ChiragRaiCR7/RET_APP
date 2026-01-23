<template>
  <div>
    <div class="chat-container" role="log" aria-live="polite">
      <div v-for="(m, i) in messages" :key="i" :class="['chat-message', m.role === 'user' ? 'user' : 'assistant']">
        <div class="chat-message-header">{{ m.role }}</div>
        <div class="chat-message-content" v-html="m.content"></div>
      </div>
    </div>

    <form @submit.prevent="send" style="display:flex; gap:8px; margin-top: var(--space-md);">
      <input v-model="input" class="form-input" placeholder="Ask RET about your dataset or conversion steps..." aria-label="Chat input" />
      <button class="btn btn-primary" :disabled="sending">Send</button>
    </form>

    <details style="margin-top: var(--space-md)">
      <summary>Retrieval Inspector</summary>
      <div class="data-table-wrapper" style="margin-top: var(--space-md)">
        <table class="data-table">
          <thead><tr><th>Doc</th><th>Score</th><th>Snippet</th></tr></thead>
          <tbody>
            <tr v-for="(r, idx) in retrievals" :key="idx">
              <td>{{ r.doc }}</td>
              <td>{{ r.score }}</td>
              <td>{{ r.snippet }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </details>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import api from '@/utils/api'

const messages = ref([
  { role: 'assistant', content: 'Hello — ask me about XML conversions, compare runs, or audit logs.' }
])
const input = ref('')
const sending = ref(false)
const retrievals = ref([])

async function send() {
  if (!input.value.trim()) return
  messages.value.push({ role: 'user', content: escapeHtml(input.value) })
  sending.value = true
  try {
    const resp = await api.post('/ai/chat', { prompt: input.value })
    messages.value.push({ role: 'assistant', content: resp.data.answer })
    retrievals.value = resp.data.retrievals || []
    input.value = ''
  } catch (e) {
    messages.value.push({ role: 'assistant', content: 'Error: ' + (e.response?.data?.message || e.message) })
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
