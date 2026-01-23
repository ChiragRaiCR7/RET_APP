<template>
  <div>
    <div class="chat-container" style="max-height:300px">
      <div v-for="(m, i) in messages" :key="i" class="chat-message assistant">
        <div class="chat-message-content" v-html="m.content"></div>
      </div>
    </div>

    <form @submit.prevent="send" style="display:flex; gap:8px; margin-top:var(--space-md)">
      <input v-model="input" class="form-input" placeholder="Admin command or question..." />
      <button class="btn btn-primary" :disabled="sending">Execute</button>
    </form>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import api from '@/utils/api'

const messages = ref([])
const input = ref('')
const sending = ref(false)

async function send() {
  if (!input.value.trim()) return
  sending.value = true
  try {
    const res = await api.post('/admin/agent', { command: input.value })
    messages.value.push({ content: res.data.result || 'OK' })
    input.value = ''
  } catch (e) {
    messages.value.push({ content: 'Error: ' + (e.response?.data?.message || e.message) })
  } finally {
    sending.value = false
  }
}
</script>
