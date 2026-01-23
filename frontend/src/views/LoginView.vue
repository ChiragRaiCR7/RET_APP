<template>
  <div class="auth-shell" role="main" aria-labelledby="login-title">
    <div style="display:grid; grid-template-columns: 1fr 420px; gap: var(--space-lg);">
      <div class="auth-hero">
        <h2 id="login-title">ZIP → XML conversion made simple</h2>
        <p>Fast conversions • Audit logs • Bulk ZIP support</p>
        <img alt="hero" src="@/assets/Light_mode.png" style="max-width:420px; margin-top: var(--space-lg)" />
      </div>

      <div class="auth-card" aria-live="polite">
        <div class="tab-list" role="tablist">
          <button class="tab-button active" role="tab" aria-selected="true">Login</button>
          <button class="tab-button" @click="showReset = true" role="tab">Reset</button>
        </div>

        <LoginForm v-if="!showReset" @success="onSuccess" />
        <ResetPasswordForm v-else @done="showReset = false" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import LoginForm from '@/components/auth/LoginForm.vue'
import ResetPasswordForm from '@/components/auth/ResetPasswordForm.vue'
import { useAuthStore } from '@/stores/authStore'
import { useRouter } from 'vue-router'


const showReset = ref(false)
const auth = useAuthStore()
const router = useRouter()

async function onSuccess() {
  await auth.fetchMe()
  router.push({ name: 'main' })
}
</script>
