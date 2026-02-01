/**
 * Toast Notification Store
 * Provides centralized toast notifications across the application
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useToastStore = defineStore('toast', () => {
  const toasts = ref([])
  let nextId = 0

  // Add a toast notification
  function add(message, type = 'info', duration = 5000) {
    const id = nextId++
    const toast = {
      id,
      message,
      type, // 'success', 'error', 'warning', 'info'
      duration,
      createdAt: Date.now()
    }
    toasts.value.push(toast)

    // Auto-remove after duration
    if (duration > 0) {
      setTimeout(() => {
        remove(id)
      }, duration)
    }

    return id
  }

  // Remove a toast by ID
  function remove(id) {
    const index = toasts.value.findIndex(t => t.id === id)
    if (index !== -1) {
      toasts.value.splice(index, 1)
    }
  }

  // Clear all toasts
  function clear() {
    toasts.value = []
  }

  // Convenience methods
  function success(message, duration = 4000) {
    return add(message, 'success', duration)
  }

  function error(message, duration = 6000) {
    return add(message, 'error', duration)
  }

  function warning(message, duration = 5000) {
    return add(message, 'warning', duration)
  }

  function info(message, duration = 4000) {
    return add(message, 'info', duration)
  }

  return {
    toasts: computed(() => toasts.value),
    add,
    remove,
    clear,
    success,
    error,
    warning,
    info
  }
})
