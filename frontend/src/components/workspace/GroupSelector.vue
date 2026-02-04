<template>
  <div class="group-selector">
    <!-- Header -->
    <div class="selector-header">
      <div class="header-title">
        <span class="header-icon">🗂️</span>
        <h4>Select Groups for AI Indexing</h4>
      </div>
      <div class="selection-count" v-if="selectedGroups.length">
        {{ selectedGroups.length }} selected
      </div>
    </div>

    <!-- Search & Filter -->
    <div class="search-bar">
      <span class="search-icon">🔍</span>
      <input 
        v-model="searchQuery"
        type="text"
        class="search-input"
        placeholder="Search groups..."
      />
      <button 
        v-if="searchQuery" 
        class="clear-btn"
        @click="searchQuery = ''"
      >
        ✕
      </button>
    </div>

    <!-- Quick Actions -->
    <div class="quick-actions">
      <button class="quick-btn" @click="selectAll">Select All</button>
      <button class="quick-btn" @click="selectNone">Clear All</button>
      <button class="quick-btn" @click="selectEligible" v-if="eligibleGroupNames.length">
        Select Eligible ({{ eligibleGroupNames.length }})
      </button>
    </div>

    <!-- Groups List -->
    <div class="groups-list" v-if="filteredGroups.length">
      <div 
        v-for="group in filteredGroups" 
        :key="group.name"
        class="group-item"
        :class="{ 
          selected: selectedGroups.includes(group.name),
          eligible: eligibleGroupNames.includes(group.name)
        }"
        @click="toggleGroup(group.name)"
      >
        <div class="group-checkbox">
          <div class="checkbox-inner" v-if="selectedGroups.includes(group.name)">✓</div>
        </div>
        
        <div class="group-info">
          <div class="group-name">
            {{ group.name }}
            <span class="eligible-badge" v-if="eligibleGroupNames.includes(group.name)">
              AI Eligible
            </span>
          </div>
          <div class="group-meta">
            <span class="meta-item">
              📄 {{ group.fileCount || 0 }} file{{ group.fileCount !== 1 ? 's' : '' }}
            </span>
            <span class="meta-item" v-if="group.recordCount">
              📊 {{ formatNumber(group.recordCount) }} records
            </span>
            <span class="meta-item" v-if="group.size">
              💾 {{ formatSize(group.size) }}
            </span>
          </div>
        </div>
        
        <div class="group-status" v-if="indexedGroups.includes(group.name)">
          <span class="indexed-badge">✅ Indexed</span>
        </div>
      </div>
    </div>

    <!-- Empty State -->
    <div class="empty-state" v-else-if="!loading">
      <span class="empty-icon">📭</span>
      <p v-if="searchQuery">No groups match "{{ searchQuery }}"</p>
      <p v-else>No groups available. Scan a ZIP file first.</p>
    </div>

    <!-- Loading State -->
    <div class="loading-state" v-if="loading">
      <span class="spinner"></span>
      <p>Loading groups...</p>
    </div>

    <!-- Action Footer -->
    <div class="selector-footer" v-if="selectedGroups.length">
      <div class="selection-summary">
        <strong>{{ selectedGroups.length }}</strong> group{{ selectedGroups.length !== 1 ? 's' : '' }} selected
        <span v-if="estimatedRecords" class="estimate">
          (~{{ formatNumber(estimatedRecords) }} records)
        </span>
      </div>
      <button 
        class="index-btn"
        :disabled="indexing"
        @click="startIndexing"
      >
        <span v-if="indexing" class="btn-spinner"></span>
        <span v-else>🚀</span>
        {{ indexing ? 'Indexing...' : 'Index Selected' }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import api from '@/utils/api'

const props = defineProps({
  sessionId: {
    type: String,
    default: null
  },
  availableGroups: {
    type: Array,
    default: () => []
  },
  indexedGroups: {
    type: Array,
    default: () => []
  },
  eligibleGroupNames: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['selection-change', 'index-start', 'index-complete', 'index-error'])

// State
const selectedGroups = ref([])
const searchQuery = ref('')
const loading = ref(false)
const indexing = ref(false)

// Filtered groups based on search
const filteredGroups = computed(() => {
  if (!searchQuery.value) return props.availableGroups
  const q = searchQuery.value.toLowerCase()
  return props.availableGroups.filter(g => 
    g.name.toLowerCase().includes(q)
  )
})

// Estimated records
const estimatedRecords = computed(() => {
  return props.availableGroups
    .filter(g => selectedGroups.value.includes(g.name))
    .reduce((sum, g) => sum + (g.recordCount || 0), 0)
})

// Selection handlers
function toggleGroup(name) {
  const idx = selectedGroups.value.indexOf(name)
  if (idx >= 0) {
    selectedGroups.value.splice(idx, 1)
  } else {
    selectedGroups.value.push(name)
  }
  emit('selection-change', selectedGroups.value)
}

function selectAll() {
  selectedGroups.value = props.availableGroups.map(g => g.name)
  emit('selection-change', selectedGroups.value)
}

function selectNone() {
  selectedGroups.value = []
  emit('selection-change', selectedGroups.value)
}

function selectEligible() {
  selectedGroups.value = [...props.eligibleGroupNames]
  emit('selection-change', selectedGroups.value)
}

// Start indexing
async function startIndexing() {
  if (!props.sessionId || selectedGroups.value.length === 0) return
  
  indexing.value = true
  emit('index-start', selectedGroups.value)
  
  try {
    const resp = await api.post('/v2/ai/index/groups', {
      session_id: props.sessionId,
      groups: selectedGroups.value
    })
    
    emit('index-complete', {
      groups: selectedGroups.value,
      stats: resp.data.stats
    })
    
  } catch (e) {
    const errorMsg = e.response?.data?.detail || e.message
    emit('index-error', errorMsg)
  } finally {
    indexing.value = false
  }
}

// Helper functions
function formatNumber(num) {
  if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M'
  if (num >= 1000) return (num / 1000).toFixed(1) + 'K'
  return num.toString()
}

function formatSize(bytes) {
  if (bytes >= 1073741824) return (bytes / 1073741824).toFixed(1) + ' GB'
  if (bytes >= 1048576) return (bytes / 1048576).toFixed(1) + ' MB'
  if (bytes >= 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return bytes + ' B'
}

// Watch for external changes
watch(() => props.availableGroups, (newGroups) => {
  // Remove selections for groups that no longer exist
  selectedGroups.value = selectedGroups.value.filter(name => 
    newGroups.some(g => g.name === name)
  )
}, { deep: true })
</script>

<style scoped>
.group-selector {
  background: var(--bg-panel, #1a1a2e);
  border-radius: var(--radius-lg, 12px);
  overflow: hidden;
  border: 1px solid var(--border-color, #2a2a4a);
}

/* Header */
.selector-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-md, 16px);
  background: var(--bg-alt, #16213e);
  border-bottom: 1px solid var(--border-color, #2a2a4a);
}

.header-title {
  display: flex;
  align-items: center;
  gap: var(--space-sm, 8px);
}

.header-icon {
  font-size: 1.3rem;
}

.header-title h4 {
  margin: 0;
  font-size: 1rem;
  font-weight: 600;
}

.selection-count {
  background: var(--primary-subtle, #4f46e520);
  color: var(--primary, #4f46e5);
  padding: 4px 12px;
  border-radius: var(--radius-full, 9999px);
  font-size: 0.8rem;
  font-weight: 600;
}

/* Search Bar */
.search-bar {
  display: flex;
  align-items: center;
  gap: var(--space-sm, 8px);
  padding: var(--space-sm, 8px) var(--space-md, 16px);
  background: var(--bg-alt, #16213e);
}

.search-icon {
  font-size: 1rem;
  color: var(--text-muted, #6b7280);
}

.search-input {
  flex: 1;
  background: transparent;
  border: none;
  color: var(--text-primary, #e0e0f0);
  font-size: 0.9rem;
  outline: none;
}

.search-input::placeholder {
  color: var(--text-muted, #6b7280);
}

.clear-btn {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--bg-panel, #1a1a2e);
  border: none;
  color: var(--text-muted, #6b7280);
  cursor: pointer;
  font-size: 0.8rem;
  transition: all 0.2s;
}

.clear-btn:hover {
  background: var(--error-subtle, #ef444420);
  color: var(--error, #ef4444);
}

/* Quick Actions */
.quick-actions {
  display: flex;
  gap: var(--space-xs, 4px);
  padding: var(--space-sm, 8px) var(--space-md, 16px);
  border-bottom: 1px solid var(--border-color, #2a2a4a);
}

.quick-btn {
  padding: 4px 12px;
  background: var(--bg-panel, #1a1a2e);
  border: 1px solid var(--border-color, #2a2a4a);
  border-radius: var(--radius-full, 9999px);
  color: var(--text-secondary, #a0a0c0);
  font-size: 0.75rem;
  cursor: pointer;
  transition: all 0.2s;
}

.quick-btn:hover {
  background: var(--primary-subtle, #4f46e520);
  border-color: var(--primary, #4f46e5);
  color: var(--primary, #4f46e5);
}

/* Groups List */
.groups-list {
  max-height: 300px;
  overflow-y: auto;
}

.group-item {
  display: flex;
  align-items: center;
  gap: var(--space-md, 16px);
  padding: var(--space-md, 16px);
  border-bottom: 1px solid var(--border-color, #2a2a4a);
  cursor: pointer;
  transition: all 0.2s;
}

.group-item:hover {
  background: var(--bg-alt, #16213e);
}

.group-item.selected {
  background: var(--primary-subtle, #4f46e520);
}

.group-item.eligible {
  border-left: 3px solid var(--success, #10b981);
}

/* Checkbox */
.group-checkbox {
  width: 22px;
  height: 22px;
  border-radius: var(--radius, 8px);
  border: 2px solid var(--border-color, #2a2a4a);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: all 0.2s;
}

.group-item.selected .group-checkbox {
  background: var(--primary, #4f46e5);
  border-color: var(--primary, #4f46e5);
}

.checkbox-inner {
  color: white;
  font-size: 0.8rem;
  font-weight: 700;
}

/* Group Info */
.group-info {
  flex: 1;
  min-width: 0;
}

.group-name {
  font-weight: 600;
  font-size: 0.95rem;
  display: flex;
  align-items: center;
  gap: var(--space-sm, 8px);
  margin-bottom: var(--space-xs, 4px);
}

.eligible-badge {
  background: var(--success-subtle, #10b98120);
  color: var(--success, #10b981);
  padding: 2px 8px;
  border-radius: var(--radius-full, 9999px);
  font-size: 0.65rem;
  font-weight: 600;
  text-transform: uppercase;
}

.group-meta {
  display: flex;
  gap: var(--space-md, 16px);
  flex-wrap: wrap;
}

.meta-item {
  font-size: 0.8rem;
  color: var(--text-muted, #6b7280);
}

/* Group Status */
.indexed-badge {
  background: var(--success-subtle, #10b98120);
  color: var(--success, #10b981);
  padding: 4px 10px;
  border-radius: var(--radius, 8px);
  font-size: 0.75rem;
  font-weight: 600;
}

/* Empty & Loading States */
.empty-state,
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--space-2xl, 48px);
  text-align: center;
  color: var(--text-muted, #6b7280);
}

.empty-icon {
  font-size: 2.5rem;
  margin-bottom: var(--space-md, 16px);
}

.spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--border-color, #2a2a4a);
  border-top-color: var(--primary, #4f46e5);
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin-bottom: var(--space-md, 16px);
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* Footer */
.selector-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-md, 16px);
  background: var(--bg-alt, #16213e);
  border-top: 1px solid var(--border-color, #2a2a4a);
}

.selection-summary {
  font-size: 0.9rem;
}

.estimate {
  color: var(--text-muted, #6b7280);
  margin-left: var(--space-sm, 8px);
}

.index-btn {
  display: flex;
  align-items: center;
  gap: var(--space-sm, 8px);
  padding: var(--space-sm, 8px) var(--space-lg, 24px);
  background: linear-gradient(135deg, var(--primary, #4f46e5), var(--primary-light, #818cf8));
  border: none;
  border-radius: var(--radius, 8px);
  color: white;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.index-btn:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(79, 70, 229, 0.4);
}

.index-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-spinner {
  width: 16px;
  height: 16px;
  border: 2px solid transparent;
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
</style>
