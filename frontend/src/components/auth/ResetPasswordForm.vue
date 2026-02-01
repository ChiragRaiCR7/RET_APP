<template>
  <div>
    <div class="tab-list" role="tablist" style="margin-bottom:var(--space-lg)">
      <button
        class="tab-button"
        :class="{ active: mode === 'request' }"
        @click="mode = 'request'"
        role="tab"
        :aria-selected="mode === 'request'"
      >
        Request Reset
      </button>
      <button
        class="tab-button"
        :class="{ active: mode === 'confirm' }"
        @click="mode = 'confirm'"
        role="tab"
        :aria-selected="mode === 'confirm'"
      >
        Use Reset Token
      </button>
    </div>

    <form v-if="mode === 'request'" @submit.prevent="requestReset" aria-label="Request password reset">
      <div class="form-group">
        <label class="form-label">Username</label>
        <input class="form-input" v-model="username" placeholder="john.doe" />
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

    <form v-else @submit.prevent="confirmReset" aria-label="Confirm password reset">
      <div class="form-group">
        <label class="form-label">Reset Token</label>
        <input class="form-input" v-model="token" placeholder="Paste reset token" />
      </div>

      <div class="form-group">
        <label class="form-label">New Password</label>
        <div style="position: relative; display: flex; align-items: center;">
          <input
            class="form-input"
            :type="showPassword ? 'text' : 'password'"
            v-model="newPassword"
            autocomplete="new-password"
            style="flex:1; padding-right:40px"
          />
          <button
            type="button"
            @click.prevent="showPassword = !showPassword"
            class="pwd-toggle"
            :title="showPassword ? 'Hide password' : 'Show password'"
            style="position:absolute; right:12px; background:none; border:none; cursor:pointer; font-size:18px; color:var(--color-text-muted);"
          >
            {{ showPassword ? '👁️' : '👁️‍🗨️' }}
          </button>
        </div>
        <div style="margin-top:var(--space-xs)">
          <PasswordStrengthMeter :value="newPassword" />
        </div>
      </div>

      <div class="form-group">
        <label class="form-label">Confirm New Password</label>
        <input class="form-input" type="password" v-model="confirmPassword" autocomplete="new-password" />
      </div>

      <div style="display:flex; gap:12px">
        <button class="btn btn-primary" :disabled="loading" type="submit">Update Password</button>
        <button class="btn btn-secondary" @click="$emit('done')" type="button">Back</button>
      </div>

      <div v-if="message" class="alert alert-info" role="status">
        <div class="alert-content">{{ message }}</div>
      </div>
      <div v-if="error" class="form-error" role="alert">{{ error }}</div>
    </form>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import api from '@/utils/api'
import PasswordStrengthMeter from '@/components/auth/PasswordStrengthMeter.vue'
import { isStrongPassword } from '@/utils/validators'

const mode = ref('request')
const username = ref('')
const token = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const showPassword = ref(false)
const loading = ref(false)
const message = ref(null)
const error = ref(null)
const emit = defineEmits(['done'])

async function requestReset() {
  loading.value = true
  error.value = null
  message.value = null
  try {
    await api.post('/auth/password-reset/request', { username: username.value })
    message.value = 'Request submitted. Contact an admin for your reset token.'
  } catch (e) {
    error.value = e.response?.data?.message || 'Failed to request reset'
  } finally {
    loading.value = false
  }
}

async function confirmReset() {
  loading.value = true
  error.value = null
  message.value = null
  try {
    if (!token.value.trim()) {
      error.value = 'Reset token is required.'
      return
    }
    if (newPassword.value !== confirmPassword.value) {
      error.value = 'Passwords do not match.'
      return
    }
    if (!isStrongPassword(newPassword.value)) {
      error.value = 'Password must be at least 8 characters with uppercase and number.'
      return
    }

    await api.post('/auth/password-reset/confirm', {
      token: token.value,
      new_password: newPassword.value
    })

    message.value = 'Password updated successfully. You can now login.'
    token.value = ''
    newPassword.value = ''
    confirmPassword.value = ''
  } catch (e) {
    error.value = e.response?.data?.detail || e.response?.data?.message || 'Failed to reset password'
  } finally {
    loading.value = false
  }
}
</script>
