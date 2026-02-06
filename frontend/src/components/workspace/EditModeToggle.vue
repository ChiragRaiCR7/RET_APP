<template>
  <div class="edit-mode-toggle-container">
    <!-- Main Toggle Button -->
    <button
      class="edit-mode-toggle-btn"
      :class="{ 'toggle-active': modelValue, 'toggle-inactive': !modelValue }"
      @click="toggleEditMode"
      :aria-pressed="modelValue"
      aria-label="Toggle Edit Mode"
    >
      <!-- Toggle Switch Visual -->
      <div class="toggle-switch-visual">
        <div class="toggle-track"></div>
        <div class="toggle-thumb"></div>
      </div>

      <!-- Labels -->
      <div class="toggle-content">
        <div class="toggle-main-label">
          <span class="toggle-icon">✏️</span>
          <span class="toggle-text">Edit Mode</span>
          <span v-if="modelValue" class="toggle-badge active-badge">ACTIVE</span>
        </div>
        <div class="toggle-sublabel">Session-only edits, modify CSVs in-memory</div>
      </div>
    </button>

    <!-- Status Indicator -->
    <transition name="fade-slide">
      <div v-if="modelValue" class="edit-mode-status">
        <span class="status-icon">✓</span>
        <span class="status-text">Edit Mode enabled</span>
      </div>
    </transition>
  </div>
</template>

<script setup>
const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['update:modelValue'])

const toggleEditMode = () => {
  emit('update:modelValue', !props.modelValue)
}
</script>

<style scoped>
.edit-mode-toggle-container {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

/* Main Toggle Button */
.edit-mode-toggle-btn {
  display: flex;
  align-items: center;
  gap: var(--space-lg);
  width: 100%;
  padding: var(--space-md) var(--space-lg);
  background: var(--surface-elevated);
  border: 2px solid var(--border-light);
  border-radius: var(--radius-lg);
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  font-family: inherit;
  font-size: 1rem;
  color: var(--text-body);
  text-align: left;
}

.edit-mode-toggle-btn:hover {
  border-color: var(--border-medium);
  background: var(--surface-hover);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
}

.edit-mode-toggle-btn:focus-visible {
  outline: 3px solid var(--brand-primary);
  outline-offset: 2px;
  box-shadow: 0 0 0 6px rgba(255, 192, 0, 0.1);
}

.edit-mode-toggle-btn:active {
  transform: scale(0.98);
}

/* Toggle Switch Visual */
.toggle-switch-visual {
  position: relative;
  width: 60px;
  height: 36px;
  flex-shrink: 0;
}

.toggle-track {
  position: absolute;
  top: 50%;
  left: 0;
  width: 100%;
  height: 20px;
  border-radius: 999px;
  transform: translateY(-50%);
  transition: background 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  background: #E5E7EB;
}

.toggle-thumb {
  position: absolute;
  top: 50%;
  left: 2px;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: white;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15), inset 0 -1px 3px rgba(0, 0, 0, 0.1);
  transform: translateY(-50%);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

/* States */
.toggle-inactive .toggle-track {
  background: #D1D5DB;
}

.toggle-active .toggle-track {
  background: var(--brand-primary);
  box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.1);
}

.toggle-active .toggle-thumb {
  left: calc(100% - 34px);
  background: white;
  box-shadow: 0 3px 10px rgba(255, 192, 0, 0.4), inset 0 1px 2px rgba(255, 255, 255, 0.5);
}

/* Content Area */
.toggle-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.toggle-main-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 700;
  font-size: 1rem;
  color: var(--text-body);
  letter-spacing: -0.01em;
}

.toggle-icon {
  font-size: 1.25rem;
  line-height: 1;
}

.toggle-text {
  flex: 1;
}

.toggle-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px;
  border-radius: var(--radius-full);
  font-size: 0.75rem;
  font-weight: 800;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  white-space: nowrap;
}

.toggle-badge.active-badge {
  background: linear-gradient(135deg, var(--brand-primary), #FFD700);
  color: #000000;
  box-shadow: 0 2px 8px rgba(255, 192, 0, 0.3);
}

.toggle-sublabel {
  font-size: 0.85rem;
  color: var(--text-secondary);
  font-weight: 500;
}

/* Status Indicator */
.edit-mode-status {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  padding: var(--space-sm) var(--space-md);
  background: rgba(34, 197, 94, 0.08);
  border: 1px solid rgba(34, 197, 94, 0.3);
  border-radius: var(--radius-md);
  font-size: 0.875rem;
  color: #16a34a;
  font-weight: 600;
  animation: slideInFromTop 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.status-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #22c55e;
  color: white;
  font-size: 0.75rem;
  font-weight: bold;
}

.status-text {
  flex: 1;
}

/* Animations */
@keyframes slideInFromTop {
  from {
    opacity: 0;
    transform: translateY(-8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.fade-slide-enter-active,
.fade-slide-leave-active {
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.fade-slide-enter-from,
.fade-slide-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}

/* Responsive */
@media (max-width: 640px) {
  .edit-mode-toggle-btn {
    gap: var(--space-md);
    padding: var(--space-md);
  }

  .toggle-switch-visual {
    width: 52px;
    height: 32px;
  }

  .toggle-thumb {
    width: 28px;
    height: 28px;
  }

  .toggle-active .toggle-thumb {
    left: calc(100% - 30px);
  }

  .toggle-main-label {
    font-size: 0.95rem;
  }

  .toggle-sublabel {
    font-size: 0.8rem;
  }
}

/* Accessibility */
@media (prefers-reduced-motion: reduce) {
  .toggle-track,
  .toggle-thumb,
  .edit-mode-toggle-btn,
  .edit-mode-status {
    transition: none;
  }
}

/* Dark mode support */
@media (prefers-color-scheme: dark) {
  .toggle-track {
    background: #4B5563;
  }

  .toggle-inactive .toggle-track {
    background: #374151;
  }

  .toggle-thumb {
    background: #F9FAFB;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.5), inset 0 -1px 3px rgba(0, 0, 0, 0.3);
  }

  .edit-mode-status {
    background: rgba(34, 197, 94, 0.12);
  }
}
</style>
