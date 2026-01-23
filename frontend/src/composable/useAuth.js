import { useAuthStore } from '@/stores/authStore'
import { onMounted } from 'vue'

export function useAuth() {
  const auth = useAuthStore()
  onMounted(() => {
    if (auth.token && !auth.user) auth.fetchMe()
  })
  return { auth }
}
