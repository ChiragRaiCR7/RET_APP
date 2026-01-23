<template>
  <form @submit.prevent="requestReset" aria-label="Request password reset">
    <div class="form-group">
      <label class="form-label">Username or Email</label>
      <input class="form-input" v-model="username" placeholder="user@example.com" />
    </div>
    <div style="display:flex; gap:12px">
      <button class="btn btn-primary" :disabled="loading" type="submit">Request Reset</button>
      <button class="btn btn-secondary" @click="$emit('done')" type="button">Back</button>
    </div>

    <div v-if="message" class="alert alert-info" role="status">
      <div class="alert-content">{{ message }}</div>
    </div>
    <div v-if="error" class="form-error" role="alert">{{ error }}</div>
  </form>
</template>

<script setup>
import { ref } from 'vue'
import api from '@/utils/api'

const username = ref('')
const loading = ref(false)
const message = ref(null)
const error = ref(null)

async function requestReset() {
  loading.value = true
  error.value = null
  message.value = null
  try {
    await api.post('/auth/request-reset', { username: username.value })
    message.value = 'If that account exists we sent instructions (check audit logs if you are admin).'
  } catch (e) {
    error.value = e.response?.data?.message || 'Failed to request reset'
  } finally {
    loading.value = false
  }
}
</script>
