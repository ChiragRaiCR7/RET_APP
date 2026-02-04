<template>
  <div class="auto-index-container">
    <!-- Progress Card -->
    <div 
      class="progress-card"
      :class="{ 
        'is-active': isIndexing,
        'is-complete': progress.status === 'completed',
        'has-error': progress.status === 'failed'
      }"
    >
      <!-- Header -->
      <div class="card-header">
        <div class="header-icon">
          <span v-if="isIndexing" class="icon-spinning">⚙️</span>
          <span v-else-if="progress.status === 'completed'">✅</span>
          <span v-else-if="progress.status === 'failed'">❌</span>
          <span v-else>📑</span>
        </div>
        <div class="header-info">
          <h3 class="card-title">Auto-Index Progress</h3>
          <span class="status-badge" :class="progress.status">
            {{ statusLabel }}
          </span>
        </div>
        <button 
          v-if="isIndexing" 
          class="cancel-btn"
          @click="cancelIndexing"
          title="Cancel Indexing"
        >
          ✕
        </button>
      </div>

      <!-- Progress Bar -->
      <div class="progress-section" v-if="isIndexing || progress.processed > 0">
        <div class="progress-bar-container">
          <div 
            class="progress-bar-fill"
            :style="{ width: progressPercent + '%' }"
            :class="{ 'animated': isIndexing }"
          ></div>
        </div>
        <div class="progress-stats">
          <span class="stat">
            <span class="stat-value">{{ progress.processed }}</span>
            <span class="stat-label">/ {{ progress.total }}</span>
          </span>
          <span class="stat-percent">{{ progressPercent }}%</span>
        </div>
      </div>

      <!-- Current File -->
      <div class="current-file" v-if="progress.currentFile && isIndexing">
        <span class="file-label">Processing:</span>
        <span class="file-name">{{ truncateFile(progress.currentFile, 40) }}</span>
      </div>

      <!-- Groups Being Indexed -->
      <div class="groups-section" v-if="progress.groups?.length">
        <span class="groups-label">Groups:</span>
        <div class="groups-list">
          <span 
            v-for="(group, idx) in progress.groups" 
            :key="group"
            class="group-chip"
            :class="{ 'processed': idx < progress.currentGroupIndex }"
          >
            {{ group }}
            <span v-if="idx === progress.currentGroupIndex && isIndexing" class="chip-indicator"></span>
          </span>
        </div>
      </div>

      <!-- Stats Summary -->
      <div class="stats-summary" v-if="progress.status === 'completed' || progress.stats">
        <div class="stat-box">
          <span class="stat-box-value">{{ progress.stats?.totalDocuments || progress.processed }}</span>
          <span class="stat-box-label">Documents</span>
        </div>
        <div class="stat-box">
          <span class="stat-box-value">{{ progress.stats?.totalChunks || 0 }}</span>
          <span class="stat-box-label">Chunks</span>
        </div>
        <div class="stat-box" v-if="progress.stats?.totalTokens">
          <span class="stat-box-value">{{ formatNumber(progress.stats.totalTokens) }}</span>
          <span class="stat-box-label">Tokens</span>
        </div>
        <div class="stat-box" v-if="progress.duration">
          <span class="stat-box-value">{{ formatDuration(progress.duration) }}</span>
          <span class="stat-box-label">Duration</span>
        </div>
      </div>

      <!-- Error Message -->
      <div class="error-message" v-if="progress.error">
        <span class="error-icon">⚠️</span>
        {{ progress.error }}
      </div>

      <!-- Actions -->
      <div class="card-actions" v-if="!isIndexing && progress.status === 'completed'">
        <button class="action-btn success" @click="$emit('open-chat')">
          💬 Open Chat
        </button>
        <button class="action-btn secondary" @click="$emit('re-index')">
          🔄 Re-Index
        </button>
      </div>
    </div>

    <!-- Eligible Groups Preview (before indexing) -->
    <div class="eligible-groups" v-if="!isIndexing && eligibleGroups.length && progress.status !== 'completed'">
      <h4>Eligible Groups for Auto-Index</h4>
      <p class="eligible-hint">
        These groups match your admin configuration and will be indexed automatically.
      </p>
      <div class="eligible-list">
        <div 
          v-for="group in eligibleGroups" 
          :key="group.name"
          class="eligible-item"
        >
          <span class="eligible-name">{{ group.name }}</span>
          <span class="eligible-count">{{ group.fileCount }} files</span>
        </div>
      </div>
      <button class="start-btn" @click="startAutoIndex">
        🚀 Start Auto-Index
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import api from '@/utils/api'

const props = defineProps({
  sessionId: {
    type: String,
    required: true
  },
  autoStart: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['progress-update', 'complete', 'error', 'open-chat', 're-index'])

// State
const progress = ref({
  status: 'idle', // idle, indexing, completed, failed
  processed: 0,
  total: 0,
  currentFile: null,
  currentGroupIndex: 0,
  groups: [],
  stats: null,
  error: null,
  duration: null
})
const eligibleGroups = ref([])
const pollInterval = ref(null)

const isIndexing = computed(() => progress.value.status === 'indexing')

const progressPercent = computed(() => {
  if (!progress.value.total) return 0
  return Math.round((progress.value.processed / progress.value.total) * 100)
})

const statusLabel = computed(() => {
  switch (progress.value.status) {
    case 'idle': return 'Ready'
    case 'indexing': return 'Indexing...'
    case 'completed': return 'Complete'
    case 'failed': return 'Failed'
    default: return 'Unknown'
  }
})

// Load eligible groups
async function loadEligibleGroups() {
  try {
    const resp = await api.get(`/v2/ai/index/groups`, {
      params: { session_id: props.sessionId, eligible_only: true }
    })
    eligibleGroups.value = resp.data.groups || []
  } catch (e) {
    console.error('Failed to load eligible groups:', e)
  }
}

// Start auto-indexing
async function startAutoIndex() {
  try {
    progress.value = {
      status: 'indexing',
      processed: 0,
      total: 0,
      currentFile: null,
      currentGroupIndex: 0,
      groups: eligibleGroups.value.map(g => g.name),
      stats: null,
      error: null,
      duration: null
    }
    
    const resp = await api.post('/v2/ai/auto-index/start', {
      session_id: props.sessionId
    })
    
    if (resp.data.started) {
      // Start polling for progress
      startPolling()
    }
  } catch (e) {
    progress.value.status = 'failed'
    progress.value.error = e.response?.data?.detail || e.message
    emit('error', progress.value.error)
  }
}

// Poll for progress updates
function startPolling() {
  if (pollInterval.value) return
  
  pollInterval.value = setInterval(async () => {
    try {
      const resp = await api.get(`/v2/ai/auto-index/progress/${props.sessionId}`)
      const data = resp.data
      
      progress.value = {
        status: data.status || 'indexing',
        processed: data.processed || 0,
        total: data.total || 0,
        currentFile: data.current_file,
        currentGroupIndex: data.current_group_index || 0,
        groups: data.groups || progress.value.groups,
        stats: data.stats,
        error: data.error,
        duration: data.duration
      }
      
      emit('progress-update', progress.value)
      
      if (data.status === 'completed' || data.status === 'failed') {
        stopPolling()
        if (data.status === 'completed') {
          emit('complete', progress.value.stats)
        }
      }
    } catch (e) {
      // Continue polling; might just be a network hiccup
      console.warn('Progress poll failed:', e)
    }
  }, 1500)
}

function stopPolling() {
  if (pollInterval.value) {
    clearInterval(pollInterval.value)
    pollInterval.value = null
  }
}

async function cancelIndexing() {
  try {
    await api.post(`/v2/ai/auto-index/cancel/${props.sessionId}`)
    stopPolling()
    progress.value.status = 'idle'
  } catch (e) {
    console.error('Failed to cancel:', e)
  }
}

function truncateFile(path, maxLen) {
  if (!path) return ''
  const name = path.split(/[/\\]/).pop()
  return name.length > maxLen ? '...' + name.slice(-maxLen) : name
}

function formatNumber(num) {
  if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M'
  if (num >= 1000) return (num / 1000).toFixed(1) + 'K'
  return num.toString()
}

function formatDuration(ms) {
  if (!ms) return '0s'
  if (ms < 1000) return ms + 'ms'
  const seconds = Math.floor(ms / 1000)
  if (seconds < 60) return seconds + 's'
  const minutes = Math.floor(seconds / 60)
  const secs = seconds % 60
  return `${minutes}m ${secs}s`
}

// Check for existing indexing progress on mount
async function checkExistingProgress() {
  try {
    const resp = await api.get(`/v2/ai/auto-index/progress/${props.sessionId}`)
    if (resp.data?.status === 'indexing') {
      progress.value = {
        status: 'indexing',
        processed: resp.data.processed || 0,
        total: resp.data.total || 0,
        currentFile: resp.data.current_file,
        groups: resp.data.groups || [],
        stats: null,
        error: null
      }
      startPolling()
    } else if (resp.data?.status === 'completed') {
      progress.value = {
        status: 'completed',
        processed: resp.data.processed || 0,
        total: resp.data.total || 0,
        groups: resp.data.groups || [],
        stats: resp.data.stats,
        error: null
      }
    }
  } catch (e) {
    // No existing progress
  }
}

watch(() => props.sessionId, async (newId) => {
  if (newId) {
    stopPolling()
    progress.value = { status: 'idle', processed: 0, total: 0, groups: [], stats: null, error: null }
    await loadEligibleGroups()
    await checkExistingProgress()
    
    if (props.autoStart && eligibleGroups.value.length && progress.value.status === 'idle') {
      await startAutoIndex()
    }
  }
}, { immediate: true })

onUnmounted(() => {
  stopPolling()
})
</script>

<style scoped>
.auto-index-container {
  display: flex;
  flex-direction: column;
  gap: var(--space-md, 16px);
}

/* Progress Card */
.progress-card {
  background: var(--bg-panel, #1a1a2e);
  border-radius: var(--radius-lg, 12px);
  padding: var(--space-lg, 24px);
  border: 1px solid var(--border-color, #2a2a4a);
  transition: all 0.3s ease;
}

.progress-card.is-active {
  border-color: var(--primary, #4f46e5);
  box-shadow: 0 0 20px rgba(79, 70, 229, 0.2);
}

.progress-card.is-complete {
  border-color: var(--success, #10b981);
}

.progress-card.has-error {
  border-color: var(--error, #ef4444);
}

/* Header */
.card-header {
  display: flex;
  align-items: center;
  gap: var(--space-md, 16px);
  margin-bottom: var(--space-lg, 24px);
}

.header-icon {
  font-size: 1.8rem;
}

.icon-spinning {
  display: inline-block;
  animation: spin 2s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.header-info {
  flex: 1;
}

.card-title {
  margin: 0 0 var(--space-xs, 4px);
  font-size: 1.1rem;
  font-weight: 600;
}

.status-badge {
  font-size: 0.75rem;
  padding: 2px 10px;
  border-radius: var(--radius-full, 9999px);
  text-transform: uppercase;
  font-weight: 600;
}

.status-badge.idle {
  background: var(--bg-alt, #16213e);
  color: var(--text-muted, #6b7280);
}

.status-badge.indexing {
  background: var(--primary-subtle, #4f46e520);
  color: var(--primary, #4f46e5);
}

.status-badge.completed {
  background: var(--success-subtle, #10b98120);
  color: var(--success, #10b981);
}

.status-badge.failed {
  background: var(--error-subtle, #ef444420);
  color: var(--error, #ef4444);
}

.cancel-btn {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--error-subtle, #ef444420);
  border: none;
  color: var(--error, #ef4444);
  cursor: pointer;
  font-size: 1rem;
  transition: all 0.2s;
}

.cancel-btn:hover {
  background: var(--error, #ef4444);
  color: white;
}

/* Progress Bar */
.progress-section {
  margin-bottom: var(--space-md, 16px);
}

.progress-bar-container {
  height: 8px;
  background: var(--bg-alt, #16213e);
  border-radius: var(--radius-full, 9999px);
  overflow: hidden;
  margin-bottom: var(--space-sm, 8px);
}

.progress-bar-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--primary, #4f46e5), var(--primary-light, #818cf8));
  border-radius: var(--radius-full, 9999px);
  transition: width 0.3s ease;
}

.progress-bar-fill.animated {
  background: linear-gradient(90deg, 
    var(--primary, #4f46e5), 
    var(--primary-light, #818cf8),
    var(--primary, #4f46e5)
  );
  background-size: 200% 100%;
  animation: shimmer 2s linear infinite;
}

@keyframes shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

.progress-stats {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.stat {
  font-size: 0.9rem;
}

.stat-value {
  font-weight: 700;
  color: var(--primary, #4f46e5);
}

.stat-label {
  color: var(--text-muted, #6b7280);
}

.stat-percent {
  font-weight: 600;
  color: var(--text-primary, #e0e0f0);
}

/* Current File */
.current-file {
  padding: var(--space-sm, 8px);
  background: var(--bg-alt, #16213e);
  border-radius: var(--radius, 8px);
  margin-bottom: var(--space-md, 16px);
  font-size: 0.85rem;
  display: flex;
  gap: var(--space-sm, 8px);
  overflow: hidden;
}

.file-label {
  color: var(--text-muted, #6b7280);
  flex-shrink: 0;
}

.file-name {
  color: var(--text-secondary, #a0a0c0);
  font-family: 'JetBrains Mono', monospace;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Groups Section */
.groups-section {
  margin-bottom: var(--space-md, 16px);
}

.groups-label {
  font-size: 0.8rem;
  color: var(--text-muted, #6b7280);
  display: block;
  margin-bottom: var(--space-xs, 4px);
}

.groups-list {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-xs, 4px);
}

.group-chip {
  padding: 4px 12px;
  background: var(--bg-alt, #16213e);
  border-radius: var(--radius-full, 9999px);
  font-size: 0.8rem;
  color: var(--text-secondary, #a0a0c0);
  position: relative;
}

.group-chip.processed {
  background: var(--success-subtle, #10b98120);
  color: var(--success, #10b981);
}

.chip-indicator {
  position: absolute;
  top: -2px;
  right: -2px;
  width: 8px;
  height: 8px;
  background: var(--primary, #4f46e5);
  border-radius: 50%;
  animation: pulse 1s ease infinite;
}

@keyframes pulse {
  0%, 100% { transform: scale(1); opacity: 1; }
  50% { transform: scale(1.5); opacity: 0.5; }
}

/* Stats Summary */
.stats-summary {
  display: flex;
  gap: var(--space-md, 16px);
  padding: var(--space-md, 16px) 0;
  border-top: 1px solid var(--border-color, #2a2a4a);
}

.stat-box {
  flex: 1;
  text-align: center;
}

.stat-box-value {
  display: block;
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--primary, #4f46e5);
}

.stat-box-label {
  font-size: 0.75rem;
  color: var(--text-muted, #6b7280);
  text-transform: uppercase;
}

/* Error Message */
.error-message {
  padding: var(--space-md, 16px);
  background: var(--error-subtle, #ef444420);
  border-radius: var(--radius, 8px);
  color: var(--error, #ef4444);
  font-size: 0.9rem;
  display: flex;
  align-items: center;
  gap: var(--space-sm, 8px);
}

/* Card Actions */
.card-actions {
  display: flex;
  gap: var(--space-sm, 8px);
  margin-top: var(--space-md, 16px);
  padding-top: var(--space-md, 16px);
  border-top: 1px solid var(--border-color, #2a2a4a);
}

.action-btn {
  flex: 1;
  padding: var(--space-sm, 8px) var(--space-md, 16px);
  border-radius: var(--radius, 8px);
  border: none;
  cursor: pointer;
  font-weight: 600;
  transition: all 0.2s;
}

.action-btn.success {
  background: var(--success, #10b981);
  color: white;
}

.action-btn.success:hover {
  background: var(--success-dark, #059669);
}

.action-btn.secondary {
  background: var(--bg-alt, #16213e);
  color: var(--text-secondary, #a0a0c0);
  border: 1px solid var(--border-color, #2a2a4a);
}

.action-btn.secondary:hover {
  background: var(--primary-subtle, #4f46e520);
  border-color: var(--primary, #4f46e5);
}

/* Eligible Groups */
.eligible-groups {
  background: var(--bg-panel, #1a1a2e);
  border-radius: var(--radius-lg, 12px);
  padding: var(--space-lg, 24px);
  border: 1px solid var(--border-color, #2a2a4a);
}

.eligible-groups h4 {
  margin: 0 0 var(--space-xs, 4px);
}

.eligible-hint {
  font-size: 0.85rem;
  color: var(--text-muted, #6b7280);
  margin-bottom: var(--space-md, 16px);
}

.eligible-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm, 8px);
  margin-bottom: var(--space-md, 16px);
}

.eligible-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-sm, 8px) var(--space-md, 16px);
  background: var(--bg-alt, #16213e);
  border-radius: var(--radius, 8px);
}

.eligible-name {
  font-weight: 600;
}

.eligible-count {
  font-size: 0.85rem;
  color: var(--text-muted, #6b7280);
}

.start-btn {
  width: 100%;
  padding: var(--space-md, 16px);
  background: linear-gradient(135deg, var(--primary, #4f46e5), var(--primary-light, #818cf8));
  border: none;
  border-radius: var(--radius, 8px);
  color: white;
  font-weight: 600;
  font-size: 1rem;
  cursor: pointer;
  transition: all 0.2s;
}

.start-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(79, 70, 229, 0.4);
}
</style>
