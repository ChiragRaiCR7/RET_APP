<template>
  <form @submit.prevent="submit" class="animate-in" aria-labelledby="login-form">
    <div class="form-group">
      <label class="form-label" for="username">Username</label>
      <input id="username" v-model="form.username" class="form-input" required aria-required="true" />
    </div>

    <div class="form-group">
      <label class="form-label" for="password">Password</label>
      <input id="password" v-model="form.password" type="password" class="form-input" required aria-required="true" />
    </div>

    <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom: var(--space-md)">
      <label style="display:flex; align-items:center; gap:8px;">
        <input type="checkbox" v-model="form.remember" />
        <span style="font-weight:700">Remember me</span>
      </label>
      <a class="form-label" @click="$emit('reset')">Forgot?</a>
    </div>

    <div style="display:flex; gap:12px">
      <button class="btn btn-primary" :disabled="loading" type="submit">
        <span v-if="loading" class="spinner spinner-lg" aria-hidden="true"></span>
        <span v-else>Login</span>
      </button>
      <button class="btn btn-secondary" type="button" @click="demoLogin">Demo</button>
    </div>

    <p v-if="error" class="form-error" role="alert">{{ error }}</p>
  </form>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useAuthStore } from '@/stores/authStore'

const auth = useAuthStore()
const loading = ref(false)
const error = ref(null)
const form = reactive({ username: '', password: '', remember: true })
const emit = defineEmits(['success', 'reset'])

async function submit() {
  loading.value = true
  error.value = null
  try {
    await auth.login(form.username, form.password, form.remember)
    // Emit success to parent
    emit('success')
  } catch (e) {
    error.value = e.response?.data?.message || 'Login failed'
  } finally {
    loading.value = false
  }
}
function demoLogin() {
  form.username = 'demo'
  form.password = 'password'
  submit()
}
</script>
