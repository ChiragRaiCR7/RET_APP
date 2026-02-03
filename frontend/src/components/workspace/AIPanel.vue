<template>
  <div class="ai-panel">
    <div class="card-header">
      <div class="card-title-group">
        <h3 class="card-title">🤖 Ask RET AI — RAG-Powered Answers</h3>
        <p class="card-description">Uses hybrid search (vector + keyword) over indexed documents for retrieval-augmented generation.</p>
      </div>
    </div>

    <!-- Tools Bar -->
    <div class="tools-bar">
      <div class="tool-group">
        <span class="tool-label">Session Memory Tools</span>
        <button class="tool-btn" @click="clearSessionMemory" title="Clear Session Memory">
          <span class="tool-icon">🗑️</span>
          <span>Clear Memory</span>
        </button>
        <button class="tool-btn" @click="showInstructions" title="Session Instructions">
          <span class="tool-icon">📋</span>
          <span>Instructions</span>
        </button>
        <button class="tool-btn" @click="downloadTranscript" title="Download Transcript">
          <span class="tool-icon">⬇️</span>
          <span>Download</span>
        </button>
      </div>
    </div>

    <!-- Chat Area -->
    <div class="chat-container" ref="chatContainer">
      <div class="chat-messages" ref="messagesContainer">
        <!-- Welcome Message -->
        <div v-if="messages.length === 0" class="welcome-message">
          <div class="welcome-icon">🤖</div>
          <h4>Welcome to RET AI Assistant</h4>
          <p>Ask me anything about your indexed documents. I use RAG (Retrieval Augmented Generation) to provide accurate answers based on your data.</p>
          <div class="quick-prompts">
            <span class="prompt-label">Try asking:</span>
            <button class="quick-prompt" @click="sendQuickPrompt('Summarize the key findings in my documents')">Summarize key findings</button>
            <button class="quick-prompt" @click="sendQuickPrompt('What are the main topics covered?')">Main topics</button>
            <button class="quick-prompt" @click="sendQuickPrompt('Show me data patterns')">Data patterns</button>
          </div>
        </div>

        <!-- Messages -->
        <div v-for="(msg, idx) in messages" :key="idx" class="message" :class="msg.role">
          <div class="message-avatar">
            {{ msg.role === 'user' ? '👤' : '🤖' }}
          </div>
          <div class="message-content">
            <div class="message-header">
              <span class="message-role">{{ msg.role === 'user' ? 'You' : 'RET AI' }}</span>
              <span class="message-time">{{ formatTime(msg.timestamp) }}</span>
            </div>
            <div class="message-text" v-html="formatMessage(msg.content)"></div>
            
            <!-- Sources (for AI responses) -->
            <div v-if="msg.role === 'assistant' && msg.sources?.length" class="message-sources">
              <details class="sources-details">
                <summary>📚 Sources ({{ msg.sources.length }} documents)</summary>
                <div class="sources-list">
                  <div v-for="(src, sidx) in msg.sources" :key="sidx" class="source-item">
                    <span class="source-icon">📄</span>
                    <span class="source-name">{{ src.filename }}</span>
                    <span class="source-score">{{ (src.score * 100).toFixed(1) }}%</span>
                  </div>
                </div>
              </details>
            </div>

            <!-- Copy Button -->
            <button class="copy-btn" @click="copyMessage(msg.content)" title="Copy message">
              📋
            </button>
          </div>
        </div>

        <!-- Typing Indicator -->
        <div v-if="isTyping" class="message assistant typing">
          <div class="message-avatar">🤖</div>
          <div class="message-content">
            <div class="typing-indicator">
              <span></span><span></span><span></span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Input Area -->
    <div class="chat-input-area">
      <div class="input-wrapper">
        <textarea
          v-model="inputText"
          ref="inputField"
          class="chat-input"
          placeholder="Ask about your indexed documents..."
          rows="1"
          @keydown.enter.exact.prevent="sendMessage"
          @input="autoResize"
        ></textarea>
        <button 
          class="send-btn" 
          @click="sendMessage"
          :disabled="!inputText.trim() || isTyping"
        >
          <span v-if="isTyping" class="spinner-sm"></span>
          <span v-else>➤</span>
        </button>
      </div>
      <div class="input-hints">
        <span>Press Enter to send, Shift+Enter for new line</span>
        <span class="char-count">{{ inputText.length }}/4000</span>
      </div>
    </div>

    <!-- RAG Retrieval Inspector (collapsible) -->
    <details class="rag-inspector" v-if="lastRetrievalInfo">
      <summary class="inspector-header">
        <span class="inspector-icon">🔍</span>
        <span>RAG Retrieval Inspector</span>
        <span class="chunk-count">{{ lastRetrievalInfo.chunks?.length || 0 }} chunks retrieved</span>
      </summary>
      <div class="inspector-content">
        <div class="inspector-metrics">
          <div class="metric">
            <span class="metric-label">Query Time</span>
            <span class="metric-value">{{ lastRetrievalInfo.queryTime }}ms</span>
          </div>
          <div class="metric">
            <span class="metric-label">Embedding Model</span>
            <span class="metric-value">{{ lastRetrievalInfo.embeddingModel || 'default' }}</span>
          </div>
          <div class="metric">
            <span class="metric-label">Top K</span>
            <span class="metric-value">{{ lastRetrievalInfo.topK || 5 }}</span>
          </div>
        </div>
        <div class="retrieved-chunks">
          <h5>Retrieved Chunks</h5>
          <div v-for="(chunk, idx) in lastRetrievalInfo.chunks" :key="idx" class="chunk-item">
            <div class="chunk-header">
              <span class="chunk-index">#{{ idx + 1 }}</span>
              <span class="chunk-file">{{ chunk.filename }}</span>
              <span class="chunk-score">{{ (chunk.score * 100).toFixed(1) }}%</span>
            </div>
            <div class="chunk-text">{{ truncateText(chunk.content, 200) }}</div>
          </div>
        </div>
      </div>
    </details>

    <!-- Auto-Index Section -->
    <div class="auto-index-section">
      <h4 class="section-header">📂 Auto-Index Documents</h4>
      <p class="section-desc">Index files for AI-powered search and chat.</p>
      
      <!-- Quick Index Converted Files -->
      <div v-if="conversionSessionId" class="quick-index-bar">
        <span class="quick-index-label">📦 Converted files available in session</span>
        
        <!-- Group Selection for Indexing -->
        <div v-if="availableGroups.length > 0" class="group-selection">
          <label class="form-label">Select groups to index:</label>
          <div class="group-checkboxes">
            <label v-for="group in availableGroups" :key="group" class="checkbox-label">
              <input 
                type="checkbox" 
                :value="group"
                v-model="selectedGroupsForIndex"
              />
              <span>{{ group }}</span>
            </label>
          </div>
        </div>
        
        <div v-else class="group-selection" style="color: var(--text-tertiary); font-size: 0.9rem;">
          <p>📁 No groups detected. Please convert files first.</p>
        </div>
        
        <button 
          class="btn btn-primary" 
          @click="indexConvertedFiles" 
          :disabled="indexing || selectedGroupsForIndex.length === 0"
          :title="selectedGroupsForIndex.length === 0 ? 'Select at least one group to index' : 'Index selected converted files for AI search'"
        >
        >
          {{ indexing ? 'Indexing...' : '⚡ Index Converted Files' }}
        </button>
      </div>
      
      <div class="drop-divider" v-if="conversionSessionId">
        <span>or upload additional files</span>
      </div>
      
      <div 
        class="index-drop-zone"
        :class="{ dragging: isDragging }"
        @dragover.prevent="isDragging = true"
        @dragleave.prevent="isDragging = false"
        @drop.prevent="onDropFiles"
      >
        <div class="drop-content">
          <span class="drop-icon">📁</span>
          <p>Drag & drop files to index</p>
          <p class="drop-hint">Supports PDF, TXT, CSV, XML, DOCX</p>
        </div>
        <button class="btn btn-secondary" @click="$refs.fileInput.click()">Browse Files</button>
      </div>
      <input 
        ref="fileInput" 
        type="file" 
        multiple 
        @change="onSelectFiles"
        accept=".pdf,.txt,.csv,.xml,.docx"
        style="display: none"
      />
      
      <!-- Pending Files -->
      <div v-if="pendingFiles.length" class="pending-files">
        <div class="pending-header">
          <span>{{ pendingFiles.length }} file(s) pending</span>
          <button class="btn btn-primary btn-sm" @click="indexFiles" :disabled="indexing">
            {{ indexing ? 'Indexing...' : 'Index Now' }}
          </button>
        </div>
        <div class="files-list">
          <div v-for="(file, idx) in pendingFiles" :key="idx" class="file-item">
            <span class="file-icon">📄</span>
            <span class="file-name">{{ file.name }}</span>
            <span class="file-size">{{ formatSize(file.size) }}</span>
            <button class="btn-remove" @click="removePendingFile(idx)">×</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Session Instructions Modal -->
    <div v-if="showInstructionsModal" class="modal-overlay" @click.self="showInstructionsModal = false">
      <div class="modal-content">
        <div class="modal-header">
          <h4>Session Instructions</h4>
          <button class="modal-close" @click="showInstructionsModal = false">×</button>
        </div>
        <div class="modal-body">
          <p>These instructions guide the AI's responses for this session.</p>
          <textarea 
            v-model="sessionInstructions" 
            class="instructions-input"
            placeholder="Enter custom instructions for the AI..."
            rows="6"
          ></textarea>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="showInstructionsModal = false">Cancel</button>
          <button class="btn btn-primary" @click="saveInstructions">Save</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick, onMounted, onUnmounted, watch } from 'vue'
import api from '@/utils/api'
import { useToastStore } from '@/stores/toastStore'

const props = defineProps({
  sessionId: {
    type: String,
    default: null
  },
  scannedGroups: {
    type: Array,
    default: () => []
  }
})

const toast = useToastStore()
const emit = defineEmits(['message-sent', 'files-indexed', 'groups-indexed'])

const messages = ref([])
const inputText = ref('')
const isTyping = ref(false)
const chatContainer = ref(null)
const messagesContainer = ref(null)
const inputField = ref(null)
const lastRetrievalInfo = ref(null)
const isDragging = ref(false)
const pendingFiles = ref([])
const indexing = ref(false)
const showInstructionsModal = ref(false)
const sessionInstructions = ref('')
const aiSessionId = ref(null)  // AI chat session ID
const conversionSessionId = ref(null)  // Conversion session ID for indexing
const availableGroups = ref([])  // Groups available in the conversion session
const selectedGroupsForIndex = ref([])  // Groups selected for indexing
const loadingGroups = ref(false)  // Loading state for group fetching

// Use conversion session from props
watch(() => props.sessionId, (newVal) => {
  conversionSessionId.value = newVal
  if (newVal) {
    loadSessionGroups()
  }
}, { immediate: true })

onMounted(async () => {
  // Update conversion session from props
  conversionSessionId.value = props.sessionId
  
  // Load or create AI chat session
  try {
    const res = await api.get('/ai/session')
    aiSessionId.value = res.data.session_id
    messages.value = res.data.messages || []
    sessionInstructions.value = res.data.instructions || ''
  } catch {
    // Create new session
    const res = await api.post('/ai/session')
    aiSessionId.value = res.data.session_id
  }
})

function formatTime(ts) {
  if (!ts) return ''
  const date = new Date(ts)
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function formatMessage(text) {
  if (!text) return ''
  // Simple markdown-like formatting
  return text
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    .replace(/`(.*?)`/g, '<code>$1</code>')
    .replace(/\n/g, '<br>')
}

function truncateText(text, maxLen) {
  if (!text) return ''
  return text.length > maxLen ? text.substring(0, maxLen) + '...' : text
}

function formatSize(bytes) {
  if (!bytes) return '0 KB'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

function autoResize() {
  const el = inputField.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 150) + 'px'
}

async function scrollToBottom() {
  await nextTick()
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
}

function sendQuickPrompt(prompt) {
  inputText.value = prompt
  sendMessage()
}

async function sendMessage() {
  const text = inputText.value.trim()
  if (!text || isTyping.value) return
  
  // Add user message
  messages.value.push({
    role: 'user',
    content: text,
    timestamp: new Date().toISOString()
  })
  inputText.value = ''
  autoResize()
  await scrollToBottom()
  
  isTyping.value = true
  
  try {
    // Use conversion session for RAG queries (where indexed data is)
    const useSessionId = conversionSessionId.value || aiSessionId.value
    
    const res = await api.post('/ai/chat', {
      message: text,
      session_id: useSessionId,
      instructions: sessionInstructions.value
    })
    
    messages.value.push({
      role: 'assistant',
      content: res.data.response,
      timestamp: new Date().toISOString(),
      sources: res.data.sources || []
    })
    
    lastRetrievalInfo.value = res.data.retrieval_info || null
    emit('message-sent', { text, response: res.data })
  } catch (e) {
    toast.error('Failed to get response: ' + (e.response?.data?.detail || e.message))
    messages.value.push({
      role: 'assistant',
      content: 'Sorry, I encountered an error processing your request. Please try again.',
      timestamp: new Date().toISOString()
    })
  } finally {
    isTyping.value = false
    await scrollToBottom()
  }
}

async function clearSessionMemory() {
  if (!confirm('Clear all chat history for this session?')) return
  try {
    await api.delete(`/ai/session/${aiSessionId.value}`)
    messages.value = []
    lastRetrievalInfo.value = null
    toast.success('Session memory cleared')
  } catch (e) {
    toast.error('Failed to clear memory: ' + (e.response?.data?.detail || e.message))
  }
}

function showInstructions() {
  showInstructionsModal.value = true
}

async function saveInstructions() {
  try {
    await api.put(`/ai/session/${aiSessionId.value}`, { instructions: sessionInstructions.value })
    showInstructionsModal.value = false
    toast.success('Instructions saved')
  } catch (e) {
    toast.error('Failed to save instructions')
  }
}

function downloadTranscript() {
  const transcript = messages.value.map(m => `[${m.role.toUpperCase()}] ${m.content}`).join('\n\n')
  const blob = new Blob([transcript], { type: 'text/plain' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `chat-transcript-${new Date().toISOString().split('T')[0]}.txt`
  a.click()
  URL.revokeObjectURL(url)
}

function copyMessage(content) {
  navigator.clipboard.writeText(content)
  toast.success('Copied to clipboard')
}

function onDropFiles(e) {
  isDragging.value = false
  const files = Array.from(e.dataTransfer.files)
  files.forEach(f => pendingFiles.value.push(f))
}

function onSelectFiles(e) {
  const files = Array.from(e.target.files)
  files.forEach(f => pendingFiles.value.push(f))
  e.target.value = ''
}

function removePendingFile(idx) {
  pendingFiles.value.splice(idx, 1)
}

async function indexFiles() {
  // If no files uploaded, try to index from converted session files
  if (!pendingFiles.value.length && !conversionSessionId.value) {
    toast.error('No files to index. Please convert files first or upload CSV files.')
    return
  }
  
  indexing.value = true
  
  try {
    const formData = new FormData()
    
    // Use conversion session ID for indexing
    const useSessionId = conversionSessionId.value || aiSessionId.value
    formData.append('session_id', useSessionId)
    
    // Append files if provided
    if (pendingFiles.value.length) {
      pendingFiles.value.forEach(f => formData.append('files', f))
    }
    
    const res = await api.post('/ai/index-session', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
    
    const filesIndexed = res.data.files_indexed || pendingFiles.value.length
    toast.success(`${filesIndexed} file(s) indexed successfully`)
    emit('files-indexed', filesIndexed)
    emit('groups-indexed', res.data.indexed_groups || [])
    pendingFiles.value = []
  } catch (e) {
    toast.error('Indexing failed: ' + (e.response?.data?.detail || e.message))
  } finally {
    indexing.value = false
  }
}

async function loadSessionGroups() {
  if (!conversionSessionId.value) {
    availableGroups.value = []
    selectedGroupsForIndex.value = []
    return
  }
  
  loadingGroups.value = true
  try {
    const res = await api.get(`/ai/session-groups/${conversionSessionId.value}`)
    availableGroups.value = res.data.groups || []
    // Pre-select all groups by default
    selectedGroupsForIndex.value = [...availableGroups.value]
  } catch (e) {
    console.error('Failed to load session groups:', e)
    availableGroups.value = []
    selectedGroupsForIndex.value = []
  } finally {
    loadingGroups.value = false
  }
}

async function indexConvertedFiles() {
  if (!conversionSessionId.value) {
    toast.error('No conversion session available. Please convert files first.')
    return
  }
  
  indexing.value = true
  
  try {
    const formData = new FormData()
    formData.append('session_id', conversionSessionId.value)
    
    // Add selected groups
    if (selectedGroupsForIndex.value.length > 0) {
      formData.append('groups', selectedGroupsForIndex.value.join(','))
    }
    
    const res = await api.post('/ai/index-session', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
    
    const filesIndexed = res.data.files_indexed || 0
    if (filesIndexed > 0) {
      toast.success(`${filesIndexed} converted file(s) indexed successfully!`)
      emit('files-indexed', filesIndexed)
      emit('groups-indexed', res.data.indexed_groups || [])
    } else {
      toast.warning('No files found to index. Have you converted files yet?')
    }
  } catch (e) {
    toast.error('Indexing failed: ' + (e.response?.data?.detail || e.message))
  } finally {
    indexing.value = false
  }
}
</script>

<style scoped>
.ai-panel { display: flex; flex-direction: column; height: 100%; }
.tools-bar { display: flex; justify-content: space-between; align-items: center; padding: var(--space-md); background: var(--surface-base); border-bottom: 1px solid var(--border-light); }
.tool-group { display: flex; align-items: center; gap: var(--space-sm); }
.tool-label { font-weight: 600; color: var(--text-tertiary); font-size: 0.85rem; margin-right: var(--space-sm); }
.tool-btn { display: flex; align-items: center; gap: var(--space-xs); padding: var(--space-xs) var(--space-sm); background: var(--surface-elevated); border: 1px solid var(--border-light); border-radius: var(--radius-sm); cursor: pointer; font-size: 0.85rem; transition: all 0.2s; }
.tool-btn:hover { background: var(--surface-active); border-color: var(--brand-primary); }
.tool-icon { font-size: 1rem; }

.chat-container { flex: 1; overflow: hidden; display: flex; flex-direction: column; min-height: 400px; }
.chat-messages { flex: 1; overflow-y: auto; padding: var(--space-lg); display: flex; flex-direction: column; gap: var(--space-md); }

.welcome-message { text-align: center; padding: var(--space-xl); color: var(--text-secondary); }
.welcome-icon { font-size: 3rem; margin-bottom: var(--space-md); }
.welcome-message h4 { margin-bottom: var(--space-sm); color: var(--text-heading); }
.quick-prompts { margin-top: var(--space-lg); display: flex; flex-wrap: wrap; gap: var(--space-sm); justify-content: center; }
.prompt-label { font-size: 0.85rem; color: var(--text-tertiary); width: 100%; }
.quick-prompt { background: var(--surface-elevated); border: 1px solid var(--border-medium); border-radius: var(--radius-full); padding: var(--space-xs) var(--space-md); cursor: pointer; font-size: 0.85rem; transition: all 0.2s; }
.quick-prompt:hover { background: var(--brand-subtle); border-color: var(--brand-primary); }

.message { display: flex; gap: var(--space-md); max-width: 85%; }
.message.user { align-self: flex-end; flex-direction: row-reverse; }
.message.assistant { align-self: flex-start; }
.message-avatar { width: 40px; height: 40px; border-radius: 50%; background: var(--surface-elevated); display: flex; align-items: center; justify-content: center; font-size: 1.25rem; flex-shrink: 0; }
.message.user .message-avatar { background: var(--brand-primary); }
.message-content { background: var(--surface-base); border-radius: var(--radius-md); padding: var(--space-md); position: relative; border: 1px solid var(--border-light); }
.message.user .message-content { background: var(--brand-subtle); border-color: var(--brand-primary); }
.message-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--space-xs); }
.message-role { font-weight: 600; font-size: 0.85rem; }
.message-time { font-size: 0.75rem; color: var(--text-tertiary); }
.message-text { line-height: 1.6; word-break: break-word; }
.message-text code { background: var(--surface-active); padding: 2px 6px; border-radius: var(--radius-sm); font-family: monospace; font-size: 0.9em; }

.message-sources { margin-top: var(--space-md); }
.sources-details { background: var(--surface-elevated); border-radius: var(--radius-sm); }
.sources-details summary { padding: var(--space-sm); cursor: pointer; font-size: 0.85rem; font-weight: 600; }
.sources-list { padding: var(--space-sm); display: flex; flex-direction: column; gap: var(--space-xs); }
.source-item { display: flex; align-items: center; gap: var(--space-sm); font-size: 0.8rem; padding: var(--space-xs); border-radius: var(--radius-sm); background: var(--surface-base); }
.source-score { color: var(--brand-primary); font-weight: 600; margin-left: auto; }

.copy-btn { position: absolute; top: var(--space-xs); right: var(--space-xs); background: transparent; border: none; cursor: pointer; opacity: 0; transition: opacity 0.2s; font-size: 0.85rem; }
.message-content:hover .copy-btn { opacity: 1; }

.typing-indicator { display: flex; gap: 4px; padding: var(--space-sm); }
.typing-indicator span { width: 8px; height: 8px; background: var(--text-tertiary); border-radius: 50%; animation: bounce 1.4s infinite ease-in-out both; }
.typing-indicator span:nth-child(1) { animation-delay: -0.32s; }
.typing-indicator span:nth-child(2) { animation-delay: -0.16s; }
@keyframes bounce { 0%, 80%, 100% { transform: scale(0); } 40% { transform: scale(1); } }

.chat-input-area { padding: var(--space-md); background: var(--surface-base); border-top: 1px solid var(--border-light); }
.input-wrapper { display: flex; gap: var(--space-sm); align-items: flex-end; }
.chat-input { flex: 1; padding: var(--space-md); border: 1px solid var(--border-medium); border-radius: var(--radius-md); resize: none; font-family: inherit; font-size: 1rem; background: var(--surface-elevated); color: var(--text-body); min-height: 44px; max-height: 150px; }
.chat-input:focus { outline: none; border-color: var(--brand-primary); }
.send-btn { width: 50px; height: 44px; border-radius: var(--radius-md); background: var(--brand-primary); color: #000; border: none; cursor: pointer; font-size: 1.25rem; display: flex; align-items: center; justify-content: center; transition: all 0.2s; }
.send-btn:hover:not(:disabled) { background: var(--brand-light); }
.send-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.spinner-sm { width: 16px; height: 16px; border: 2px solid transparent; border-top-color: #000; border-radius: 50%; animation: spin 0.8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.input-hints { display: flex; justify-content: space-between; margin-top: var(--space-xs); font-size: 0.75rem; color: var(--text-tertiary); }

.rag-inspector { margin: var(--space-lg); background: var(--surface-base); border-radius: var(--radius-md); border: 1px solid var(--border-light); }
.inspector-header { padding: var(--space-md); display: flex; align-items: center; gap: var(--space-sm); cursor: pointer; font-weight: 600; }
.inspector-icon { font-size: 1.25rem; }
.chunk-count { margin-left: auto; font-size: 0.85rem; color: var(--text-tertiary); }
.inspector-content { padding: 0 var(--space-md) var(--space-md); }
.inspector-metrics { display: flex; gap: var(--space-lg); margin-bottom: var(--space-md); }
.inspector-metrics .metric { display: flex; flex-direction: column; }
.inspector-metrics .metric-label { font-size: 0.75rem; color: var(--text-tertiary); }
.inspector-metrics .metric-value { font-weight: 600; }
.retrieved-chunks h5 { margin-bottom: var(--space-sm); }
.chunk-item { background: var(--surface-elevated); border-radius: var(--radius-sm); padding: var(--space-sm); margin-bottom: var(--space-sm); }
.chunk-header { display: flex; align-items: center; gap: var(--space-sm); margin-bottom: var(--space-xs); }
.chunk-index { font-weight: 700; color: var(--brand-primary); }
.chunk-file { font-size: 0.85rem; }
.chunk-score { margin-left: auto; font-weight: 600; color: var(--brand-primary); }
.chunk-text { font-size: 0.85rem; color: var(--text-secondary); line-height: 1.5; }

.auto-index-section { margin: var(--space-lg); padding: var(--space-lg); background: var(--surface-base); border-radius: var(--radius-md); border: 1px solid var(--border-light); }
.section-header { margin-bottom: var(--space-xs); }
.section-desc { font-size: 0.85rem; color: var(--text-tertiary); margin-bottom: var(--space-md); }

.quick-index-bar { display: flex; align-items: center; justify-content: space-between; padding: var(--space-md); background: var(--brand-subtle); border-radius: var(--radius-md); margin-bottom: var(--space-md); border: 1px solid var(--brand-primary); }
.quick-index-label { font-size: 0.9rem; font-weight: 500; color: var(--text-body); }
.drop-divider { display: flex; align-items: center; gap: var(--space-md); margin: var(--space-md) 0; }
.drop-divider::before, .drop-divider::after { content: ''; flex: 1; height: 1px; background: var(--border-medium); }
.drop-divider span { font-size: 0.85rem; color: var(--text-tertiary); }

.index-drop-zone { border: 2px dashed var(--border-medium); border-radius: var(--radius-md); padding: var(--space-xl); text-align: center; transition: all 0.2s; }
.index-drop-zone:hover, .index-drop-zone.dragging { border-color: var(--brand-primary); background: var(--brand-subtle); }
.drop-content { margin-bottom: var(--space-md); }
.drop-icon { font-size: 2rem; margin-bottom: var(--space-sm); }
.drop-hint { font-size: 0.85rem; color: var(--text-tertiary); }

.pending-files { margin-top: var(--space-md); }
.pending-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--space-sm); }
.files-list { display: flex; flex-direction: column; gap: var(--space-xs); }
.file-item { display: flex; align-items: center; gap: var(--space-sm); padding: var(--space-sm); background: var(--surface-elevated); border-radius: var(--radius-sm); }
.file-icon { font-size: 1.25rem; }
.file-name { flex: 1; font-weight: 500; }
.file-size { font-size: 0.85rem; color: var(--text-tertiary); }
.btn-remove { background: var(--error); color: white; border: none; border-radius: 50%; width: 24px; height: 24px; cursor: pointer; font-size: 1rem; line-height: 1; }

/* Modal */
.modal-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.modal-content { background: var(--surface-elevated); border-radius: var(--radius-lg); width: 90%; max-width: 500px; overflow: hidden; box-shadow: var(--shadow-heavy); }
.modal-header { display: flex; justify-content: space-between; align-items: center; padding: var(--space-md) var(--space-lg); border-bottom: 1px solid var(--border-light); }
.modal-header h4 { margin: 0; }
.modal-close { background: transparent; border: none; font-size: 1.5rem; cursor: pointer; color: var(--text-secondary); }
.modal-body { padding: var(--space-lg); }
.instructions-input { width: 100%; padding: var(--space-md); border: 1px solid var(--border-medium); border-radius: var(--radius-md); resize: vertical; font-family: inherit; background: var(--surface-base); color: var(--text-body); }
.modal-footer { display: flex; justify-content: flex-end; gap: var(--space-sm); padding: var(--space-md) var(--space-lg); border-top: 1px solid var(--border-light); }
</style>
