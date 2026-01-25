<template>
  <div class="auth-shell" role="main" aria-labelledby="login-title">
    <div style="display:grid; grid-template-columns: 1fr 420px; gap: var(--space-2xl); align-items:center">
      <!-- Hero Panel -->
      <div class="auth-hero">
        <h2 id="login-title" style="font-size:2rem; margin-bottom:var(--space-md)">
          ZIP → XML Conversion Engine
        </h2>
        <p style="color:var(--text-secondary); margin-bottom:var(--space-lg)">
          Fast conversions • Audit logs • Bulk ZIP support • Enterprise grade
        </p>
        
        <!-- Dynamic Hero Image -->
        <img 
          v-if="heroImage"
          :src="heroImage" 
          alt="RET v4 Hero Illustration"
          style="max-width:100%; border-radius:var(--radius-lg); margin-bottom:var(--space-lg); box-shadow:var(--shadow-lg)"
        />
        
        <!-- Feature Badges -->
        <div style="display:flex; flex-wrap:wrap; gap:var(--space-sm)">
          <span class="brand-badge">⚡ Fast Conversions</span>
          <span class="brand-badge">📋 Audit Logs</span>
          <span class="brand-badge">📦 Bulk ZIP</span>
          <span class="brand-badge">🔒 Secure</span>
        </div>
      </div>

      <!-- Auth Card -->
      <div class="auth-card" aria-live="polite">
        <div class="tab-list" role="tablist" style="margin-bottom:var(--space-lg)">
          <button 
            class="tab-button" 
            :class="{ active: !showReset }"
            @click="showReset = false"
            role="tab" 
            :aria-selected="!showReset"
          >
            Login
          </button>
          <button 
            class="tab-button"
            :class="{ active: showReset }"
            @click="showReset = true" 
            role="tab"
            :aria-selected="showReset"
          >
            Reset Password
          </button>
        </div>

        <!-- Login Form -->
        <div v-if="!showReset">
          <LoginForm @success="onSuccess" @reset="showReset = true" />
        </div>

        <!-- Reset Password Form -->
        <div v-else>
          <ResetPasswordForm @done="showReset = false" />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import LoginForm from '@/components/auth/LoginForm.vue'
import ResetPasswordForm from '@/components/auth/ResetPasswordForm.vue'
import { useAuthStore } from '@/stores/authStore'
import { useRouter } from 'vue-router'
import { useTheme } from '@/composable/useTheme'

// Import images (adjust paths based on your actual structure)
import LightModeImage from '@/assets/Light_mode.png'
import DarkModeImage from '@/assets/Dark_mode.png'

const showReset = ref(false)
const auth = useAuthStore()
const router = useRouter()
const { theme } = useTheme()

// Dynamically select hero image based on theme
const heroImage = computed(() => {
  return theme.value === 'dark' ? DarkModeImage : LightModeImage
})

async function onSuccess() {
  // Fetch user details after successful login
  await auth.fetchMe()
  // Redirect based on role
  if (auth.user?.role === 'admin') {
    router.push({ name: 'admin' })
  } else {
    router.push({ name: 'main' })
  }
}
</script>