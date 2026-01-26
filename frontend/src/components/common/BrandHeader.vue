<template>
  <header class="brand-header" role="banner" aria-label="RETv4 header">
    <div>
      <h1 class="brand-title"><span class="brand-accent">RET</span>v4 <small class="brand-subtitle">ZIP → XML</small></h1>
      <div class="brand-badge" aria-hidden="true">Secured</div>
    </div>

    <div style="display:flex; gap: 12px; align-items:center;">
      <button class="btn btn-secondary btn-sm" @click="$router.push({ name: 'main' })" aria-label="Go to Workspace">Workspace</button>
      <button v-if="auth.isAdmin" class="btn btn-secondary btn-sm" @click="$router.push({ name: 'admin' })" aria-label="Go to Admin">Admin</button>
      <button class="btn btn-sm btn-primary" @click="$emit('toggle-theme')" aria-label="Toggle theme">
        🌓
      </button>
      <div v-if="auth.isAuthenticated" class="user-info" role="status" :title="auth.user?.username">
        <div class="user-avatar">{{ initials }}</div>
        <div>{{ auth.user?.username }}</div>
        <button class="btn btn-sm" @click="logout" aria-label="Logout">Logout</button>
      </div>
    </div>
  </header>
</template>

<script setup>
import { computed } from 'vue'
import { useAuthStore } from '@/stores/authStore'

const auth = useAuthStore()
function logout() {
  auth.logout()
  // redirect
  window.location.href = '/'
}

const initials = computed(() => {
  if (!auth.user?.username) return 'U'
  return auth.user.username.split(' ').map(s=>s[0]).slice(0,2).join('').toUpperCase()
})
</script>
