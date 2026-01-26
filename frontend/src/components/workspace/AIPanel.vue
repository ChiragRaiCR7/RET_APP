<template>
  <div class="ai-panel">
    <!-- AI Memory Management Section -->
    <details class="memory-section" open>
      <summary class="memory-title">
        <span>💾 Session Memory Management</span>
        <span class="toggle-icon">▶</span>
      </summary>
      
      <div class="memory-content">
        <!-- Group Selection for Indexing -->
        <div class="form-group">
          <label class="form-label">📂 Select Groups to Index</label>
          <p class="form-hint">Choose which groups should be indexed for AI context</p>
          
          <div v-if="availableGroups.length === 0" class="alert alert-info">
            No groups available. Scan a ZIP file in the Utility tab first.
          </div>
          
          <div v-else class="group-selector">
            <div class="group-list">
              <label v-for="group in availableGroups" :key="group" class="group-checkbox">
                <input 
                  type="checkbox" 
                  :value="group" 
                  v-model="ai.selectedGroups"
                />
                <span>{{ group }}</span>
              </label>
            </div>
          </div>
        </div>

        <!-- Indexed Groups Info -->
        <div v-if="ai.indexedGroups.length > 0" class="info-box" style="margin-top:var(--space-md)">
          <div class="info-label">✅ Indexed Groups</div>
          <div class="group-tags">
            <span v-for="group in ai.indexedGroups" :key="group" class="tag">
              {{ group }}
            </span>
          </div>
        </div>

        <!-- Action Buttons -->
        <div style="display:flex; gap:8px; margin-top:var(--space-lg); flex-wrap:wrap">
          <button 
            class="btn btn-primary" 
            @click="indexGroups" 
            :disabled="!ai.selectedGroups.length || indexing"
          >
            <span v-if="indexing" class="spinner" style="margin-right:8px"></span>
            {{ indexing ? 'Indexing...' : 'Index Selected Groups' }}
          </button>
          
          <button 
            class="btn btn-danger" 
            @click="clearMemory"
            :disabled="ai.indexedGroups.length === 0"
          >
            Clear All Memory
          </button>
        </div>

        <!-- Status Messages -->
        <div v-if="ai.indexStatus" class="alert" :class="getStatusClass()">
          <div class="alert-content">{{ ai.indexStatus }}</div>
        </div>
      </div>
    </details>

    <!-- AI Chat Interface -->
    <div style="margin-top:var(--space-lg)">
      <h4 class="card-title">🤖 Ask RET AI</h4>
      <p class="card-description">Query your indexed data using natural language</p>
      
      <AIChatInterface 
        :indexed-groups="ai.indexedGroups"
        :session-id="sessionId"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import AIChatInterface from './AIChatInterface.vue'
import api from '@/utils/api'

defineProps({
  scannedGroups: {
    type: Array,
    default: () => []
  },
  sessionId: {
    type: String,
    default: null
  }
})

const ai = reactive({
  selectedGroups: [],
  indexedGroups: [],
  indexStatus: null
})

const indexing = ref(false)

const availableGroups = computed(() => {
  // Extract unique group names from scanned groups
  return [...new Set((props.scannedGroups || []).map(g => g.name || g))]
})

// Watch for props changes
const props = defineProps(['scannedGroups', 'sessionId'])

onMounted(async () => {
  if (props.sessionId) {
    await loadIndexedGroups()
  }
})

async function loadIndexedGroups() {
  try {
    const res = await api.get(`/api/ai/indexed-groups/${props.sessionId}`)
    ai.indexedGroups = res.data.indexed_groups || []
  } catch (e) {
    console.error('Failed to load indexed groups:', e)
  }
}

async function indexGroups() {
  if (!props.sessionId) {
    alert('Session ID not available. Scan a file first.')
    return
  }

  indexing.value = true
  ai.indexStatus = null

  try {
    const res = await api.post(`/api/ai/index`, {
      session_id: props.sessionId,
      groups: ai.selectedGroups
    })

    ai.indexStatus = res.data.message || 'Groups indexed successfully! ✅'
    ai.indexedGroups = res.data.indexed_groups || []
    
    // Clear selection after successful indexing
    ai.selectedGroups = []
    
    setTimeout(() => {
      ai.indexStatus = null
    }, 5000)
  } catch (e) {
    ai.indexStatus = '❌ Indexing failed: ' + (e.response?.data?.detail || e.message)
  } finally {
    indexing.value = false
  }
}

async function clearMemory() {
  if (!props.sessionId) {
    alert('Session ID not available.')
    return
  }

  if (!confirm('Clear all AI memory? This cannot be undone.')) {
    return
  }

  try {
    const res = await api.post(`/api/ai/clear-memory/${props.sessionId}`)
    
    ai.indexStatus = 'AI memory cleared successfully! 🗑️'
    ai.indexedGroups = []
    ai.selectedGroups = []
    
    setTimeout(() => {
      ai.indexStatus = null
    }, 3000)
  } catch (e) {
    ai.indexStatus = '❌ Failed to clear memory: ' + (e.response?.data?.detail || e.message)
  }
}

function getStatusClass() {
  if (!ai.indexStatus) return ''
  if (ai.indexStatus.includes('✅')) return 'alert-success'
  if (ai.indexStatus.includes('❌')) return 'alert-error'
  return 'alert-info'
}
</script>

<style scoped>
.ai-panel {
  padding: var(--space-lg);
}

.memory-section {
  background: var(--surface-base);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  padding: var(--space-lg);
  margin-bottom: var(--space-lg);
}

.memory-title {
  cursor: pointer;
  font-weight: 600;
  display: flex;
  justify-content: space-between;
  align-items: center;
  user-select: none;
}

.toggle-icon {
  display: inline-block;
  transition: transform 0.2s;
}

details[open] .toggle-icon {
  transform: rotate(90deg);
}

.memory-content {
  margin-top: var(--space-md);
  padding-top: var(--space-md);
  border-top: 1px solid var(--border-color);
}

.group-selector {
  background: var(--surface-alt);
  padding: var(--space-md);
  border-radius: var(--radius-sm);
  max-height: 300px;
  overflow-y: auto;
}

.group-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.group-checkbox {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  cursor: pointer;
  padding: var(--space-xs);
  border-radius: var(--radius-sm);
  transition: background-color 0.2s;
}

.group-checkbox:hover {
  background-color: var(--surface-base);
}

.group-checkbox input[type="checkbox"] {
  cursor: pointer;
}

.info-box {
  background: var(--surface-alt);
  padding: var(--space-md);
  border-radius: var(--radius-sm);
  border-left: 4px solid var(--success);
}

.info-label {
  font-weight: 600;
  margin-bottom: var(--space-sm);
  color: var(--text-primary);
}

.group-tags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-sm);
}

.tag {
  display: inline-block;
  background-color: var(--primary);
  color: white;
  padding: 4px 12px;
  border-radius: 12px;
  font-size: 0.9rem;
}

.alert-success {
  background-color: var(--success-light, #dcfce7);
  border-left-color: var(--success);
  color: var(--success);
}

.alert-error {
  background-color: var(--error-light, #fee2e2);
  border-left-color: var(--error);
  color: var(--error);
}

.alert-info {
  background-color: var(--info-light, #cffafe);
  border-left-color: var(--info);
  color: var(--info);
}
</style>
