import { createRouter, createWebHistory } from 'vue-router'
import LoginView from '@/views/LoginView.vue'
import MainView from '@/views/MainView.vue'
import AdminView from '@/views/AdminView.vue'
import { useAuthStore } from '@/stores/authStore'

const routes = [
  { path: '/', name: 'login', component: LoginView, meta: { requiresGuest: true } },
  { path: '/app', name: 'main', component: MainView, meta: { requiresAuth: true } },
  { path: '/admin', name: 'admin', component: AdminView, meta: { requiresAuth: true, requiresAdmin: true } },
  { path: '/:pathMatch(.*)*', redirect: '/' }, // Catch-all redirect to login
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

// Track if we've attempted a refresh in this session to avoid loops
let hasAttemptedRefresh = false

router.beforeEach(async (to) => {
  const auth = useAuthStore()

  // One-time attempt to restore session when app first loads
  if (!hasAttemptedRefresh && !auth.isAuthenticated) {
    hasAttemptedRefresh = true
    try {
      const refreshed = await auth.refreshToken()
      if (refreshed) {
        await auth.fetchMe()
      }
    } catch (e) {
      // Silent fail - no valid refresh cookie is normal for new sessions
    }
  }

  // Now apply standard guards
  if (to.meta.requiresAuth && !auth.isAuthenticated) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }

  if (to.meta.requiresGuest && auth.isAuthenticated) {
    return { name: auth.user?.role === 'admin' ? 'admin' : 'main' }
  }

  if (to.meta.requiresAdmin && !auth.isAdmin) {
    return { name: 'main' }
  }

  return true
})

export default router
