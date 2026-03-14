/**
 * Toast Notification Store
 * Provides centralized toast notifications across the application
 *
 * Non-breaking improvements:
 * - Prevent unbounded toast growth with a max cap
 * - Optional dedupe behavior (same message+type refreshes existing toast)
 * - Track and clear timers to avoid orphaned timeouts
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useToastStore = defineStore('toast', () => {
  const toasts = ref([])
  let nextId = 0

  // ✅ Safety defaults (non-breaking)
  const MAX_TOASTS_DEFAULT = 6
  const DEDUPE_DEFAULT = true

  // Runtime-configurable options
  const maxToasts = ref(MAX_TOASTS_DEFAULT)
  const dedupe = ref(DEDUPE_DEFAULT)

  // Track timers to avoid dangling setTimeout handlers
  const timers = new Map()

  /**
   * Internal: clear and forget a toast timer
   */
  function _clearTimer(id) {
    const t = timers.get(id)
    if (t) {
      clearTimeout(t)
      timers.delete(id)
    }
  }

  /**
   * Internal: enforce max toast count (drop oldest)
   */
  function _enforceMax() {
    while (toasts.value.length > maxToasts.value) {
      const oldest = toasts.value.shift()
      if (oldest) _clearTimer(oldest.id)
    }
  }

  /**
   * Add a toast notification
   * @param {string} message
   * @param {'success'|'error'|'warning'|'info'} type
   * @param {number} duration - ms; 0 or negative disables auto-dismiss
   * @returns {number} toast id
   */
  function add(message, type = 'info', duration = 5000) {
    const msg = String(message ?? '').trim()
    if (!msg) return -1

    // ✅ Optional dedupe: refresh an existing toast instead of creating duplicates
    if (dedupe.value) {
      const existing = toasts.value.find((t) => t.message === msg && t.type === type)
      if (existing) {
        // refresh metadata + timer
        existing.duration = duration
        existing.createdAt = Date.now()
        _clearTimer(existing.id)

        if (duration > 0) {
          timers.set(
            existing.id,
            setTimeout(() => remove(existing.id), duration)
          )
        }
        return existing.id
      }
    }

    const id = nextId++
    const toast = {
      id,
      message: msg,
      type, // 'success', 'error', 'warning', 'info'
      duration,
      createdAt: Date.now()
    }

    toasts.value.push(toast)
    _enforceMax()

    // Auto-remove after duration
    if (duration > 0) {
      timers.set(
        id,
        setTimeout(() => remove(id), duration)
      )
    }

    return id
  }

  /**
   * Remove a toast by ID
   */
  function remove(id) {
    _clearTimer(id)
    const index = toasts.value.findIndex((t) => t.id === id)
    if (index !== -1) {
      toasts.value.splice(index, 1)
    }
  }

  /**
   * Clear all toasts
   */
  function clear() {
    // clear timers
    for (const id of timers.keys()) {
      _clearTimer(id)
    }
    toasts.value = []
  }

  /**
   * Optional: update a toast in-place (non-breaking extra helper)
   */
  function update(id, patch = {}) {
    const t = toasts.value.find((x) => x.id === id)
    if (!t) return false

    Object.assign(t, patch)
    // If duration changed, refresh timer
    if (Object.prototype.hasOwnProperty.call(patch, 'duration')) {
      _clearTimer(id)
      if (t.duration > 0) {
        timers.set(id, setTimeout(() => remove(id), t.duration))
      }
    }
    return true
  }

  /**
   * Optional: configure maximum number of toasts kept in memory
   */
  function setMax(n) {
    const v = Number(n)
    if (!Number.isFinite(v) || v <= 0) return
    maxToasts.value = Math.floor(v)
    _enforceMax()
  }

  /**
   * Optional: enable/disable dedupe behavior
   */
  function setDedupe(flag) {
    dedupe.value = !!flag
  }

  // Convenience methods (same as your original)
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
    // original API
    toasts: computed(() => toasts.value),
    add,
    remove,
    clear,
    success,
    error,
    warning,
    info,

    // optional helpers (non-breaking)
    update,
    setMax,
    setDedupe
  }
})