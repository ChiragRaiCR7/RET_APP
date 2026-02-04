<template>
  <div class="controls-section">
    <h4 class="section-title">⚙️ Controls</h4>
    <div class="controls-grid">
      <div class="control-group">
        <label class="form-label">Output format (downloads)</label>
        <div class="radio-group">
          <label class="radio-label">
            <input 
              type="radio" 
              :value="'csv'" 
              :checked="outputFormat === 'csv'"
              @change="$emit('update:outputFormat', 'csv')" 
            />
            <span>CSV</span>
          </label>
          <label class="radio-label">
            <input 
              type="radio" 
              :value="'xlsx'" 
              :checked="outputFormat === 'xlsx'"
              @change="$emit('update:outputFormat', 'xlsx')" 
            />
            <span>Excel (.xlsx)</span>
          </label>
        </div>
      </div>
      
      <div class="control-group">
        <label class="toggle-control">
          <input 
            type="checkbox" 
            :checked="editMode"
            @change="$emit('update:editMode', $event.target.checked)"
            class="toggle-input" 
          />
          <span class="toggle-text">✏️ Enable Edit Mode (session-only)</span>
        </label>
      </div>

      <div class="control-group full-width">
        <label class="form-label">Custom group prefixes (comma-separated, e.g. ABC,XYZ,PQR). Leave blank for auto.</label>
        <input 
          :value="customPrefixes"
          @input="$emit('update:customPrefixes', $event.target.value)"
          type="text" 
          class="form-input"
          placeholder="ABC,XYZ,PQR"
        />
      </div>
    </div>

    <div class="controls-actions">
      <button class="btn btn-secondary" @click="$emit('cleanup')">
        🧹 Cleanup Session Data
      </button>
      <button class="btn btn-secondary" @click="$emit('clear-edits')">
        Clear ALL Edits
      </button>
      <span class="idle-info">Idle cleanup timeout: 60 minutes</span>
    </div>

    <div class="parser-option">
      <label class="checkbox-label">
        <input 
          type="checkbox" 
          :checked="fastParser"
          @change="$emit('update:fastParser', $event.target.checked)"
        />
        <span>Fast XML parser (lxml)</span>
      </label>
    </div>
  </div>
</template>

<script setup>
defineProps({
  outputFormat: {
    type: String,
    default: 'csv'
  },
  editMode: {
    type: Boolean,
    default: false
  },
  customPrefixes: {
    type: String,
    default: ''
  },
  fastParser: {
    type: Boolean,
    default: true
  }
})

defineEmits([
  'update:outputFormat',
  'update:editMode', 
  'update:customPrefixes',
  'update:fastParser',
  'cleanup',
  'clear-edits'
])
</script>

<style scoped>
.controls-section {
  background: var(--surface-base);
  border-radius: var(--radius-md);
  padding: var(--space-lg);
  margin-bottom: var(--space-lg);
}

.section-title {
  font-size: 1rem;
  font-weight: 700;
  margin-bottom: var(--space-md);
  color: var(--text-heading);
}

.controls-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: var(--space-lg);
  margin-bottom: var(--space-md);
}

.control-group {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}

.control-group.full-width {
  grid-column: 1 / -1;
}

.radio-group {
  display: flex;
  gap: var(--space-lg);
}

.radio-label {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
  cursor: pointer;
}

.toggle-control {
  display: flex;
  align-items: center;
  gap: var(--space-md);
  cursor: pointer;
  padding: var(--space-md);
  border-radius: 8px;
  background: var(--surface-secondary);
  border: 1px solid var(--border-light);
  transition: all 0.2s ease;
}

.toggle-control:hover {
  background: var(--surface-hover);
  border-color: var(--brand-primary);
}

.toggle-input {
  width: 56px;
  height: 28px;
  appearance: none;
  background: linear-gradient(135deg, #e0e0e0 0%, #f0f0f0 100%);
  border-radius: 14px;
  position: relative;
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  border: 2px solid #d0d0d0;
}

.toggle-input:checked {
  background: linear-gradient(135deg, var(--brand-primary) 0%, #2563eb 100%);
  border-color: var(--brand-primary);
}

.toggle-input::before {
  content: '';
  position: absolute;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: white;
  top: 2px;
  left: 2px;
  transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
}

.toggle-input:checked::before {
  transform: translateX(28px);
}

.toggle-text {
  font-weight: 500;
  font-size: 0.95rem;
  color: var(--text-primary);
  user-select: none;
}

.controls-actions {
  display: flex;
  gap: var(--space-md);
  align-items: center;
  flex-wrap: wrap;
}

.idle-info {
  color: var(--text-tertiary);
  font-size: 0.85rem;
}

.parser-option {
  margin-top: var(--space-md);
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  cursor: pointer;
}
</style>
