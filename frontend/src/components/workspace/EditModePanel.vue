<template>
  <div class="edit-mode-panel">
    <div class="panel-header">
      <h4 class="panel-title">✏️ Edit Mode Active</h4>
      <p class="panel-description">Make changes to your CSV files. Changes are session-only until downloaded.</p>
    </div>

    <!-- Pending Changes Summary -->
    <div v-if="hasChanges" class="changes-summary">
      <div class="summary-header">
        <span class="summary-icon">📝</span>
        <span class="summary-text">{{ totalChanges }} unsaved change(s)</span>
        <button class="btn btn-primary btn-sm" @click="saveAllChanges" :disabled="saving">
          <span v-if="saving" class="spinner-sm"></span>
          {{ saving ? 'Saving...' : 'Save All Changes' }}
        </button>
        <button class="btn btn-secondary btn-sm" @click="discardChanges">
          Discard All
        </button>
      </div>
      
      <div class="changes-list">
        <div v-for="(change, idx) in pendingChangesList" :key="idx" class="change-item">
          <span class="change-type" :class="change.type">{{ change.type }}</span>
          <span class="change-file">{{ change.filename }}</span>
          <span class="change-detail">{{ change.detail }}</span>
        </div>
      </div>
    </div>

    <!-- Quick Actions -->
    <div class="quick-actions">
      <button class="btn btn-secondary" @click="showAddRowModal = true">
        ➕ Add Row
      </button>
      <button class="btn btn-secondary" @click="showAddFileModal = true">
        📄 Add New File
      </button>
      <button class="btn btn-warning" @click="showDeleteFileModal = true">
        🗑️ Delete File
      </button>
    </div>

    <!-- Add Row Modal -->
    <div v-if="showAddRowModal" class="modal-overlay" @click.self="showAddRowModal = false">
      <div class="modal-content">
        <div class="modal-header">
          <h4>Add New Row</h4>
          <button class="modal-close" @click="showAddRowModal = false">×</button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label class="form-label">Select File</label>
            <select v-model="addRowForm.filename" class="form-select">
              <option value="">Choose file...</option>
              <option v-for="f in files" :key="f.filename" :value="f.filename">
                {{ f.filename }}
              </option>
            </select>
          </div>
          <div v-if="addRowForm.filename" class="form-group">
            <label class="form-label">Row Data (JSON format)</label>
            <textarea 
              v-model="addRowForm.rowData" 
              class="form-textarea"
              rows="4"
              placeholder='{"column1": "value1", "column2": "value2"}'
            ></textarea>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="showAddRowModal = false">Cancel</button>
          <button class="btn btn-primary" @click="addRow" :disabled="!addRowForm.filename">Add Row</button>
        </div>
      </div>
    </div>

    <!-- Add File Modal -->
    <div v-if="showAddFileModal" class="modal-overlay" @click.self="showAddFileModal = false">
      <div class="modal-content">
        <div class="modal-header">
          <h4>Add New File</h4>
          <button class="modal-close" @click="showAddFileModal = false">×</button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label class="form-label">File Name</label>
            <input v-model="addFileForm.filename" class="form-input" placeholder="newfile.csv" />
          </div>
          <div class="form-group">
            <label class="form-label">Group</label>
            <input v-model="addFileForm.group" class="form-input" placeholder="GROUP_NAME" />
          </div>
          <div class="form-group">
            <label class="form-label">Headers (comma-separated)</label>
            <input v-model="addFileForm.headers" class="form-input" placeholder="Col1,Col2,Col3" />
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="showAddFileModal = false">Cancel</button>
          <button class="btn btn-primary" @click="addFile" :disabled="!addFileForm.filename || !addFileForm.headers">Create File</button>
        </div>
      </div>
    </div>

    <!-- Delete File Modal -->
    <div v-if="showDeleteFileModal" class="modal-overlay" @click.self="showDeleteFileModal = false">
      <div class="modal-content">
        <div class="modal-header">
          <h4>Delete File</h4>
          <button class="modal-close" @click="showDeleteFileModal = false">×</button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label class="form-label">Select File to Delete</label>
            <select v-model="deleteFileForm.filename" class="form-select">
              <option value="">Choose file...</option>
              <option v-for="f in files" :key="f.filename" :value="f.filename">
                {{ f.filename }}
              </option>
            </select>
          </div>
          <div v-if="deleteFileForm.filename" class="warning-box">
            <span class="warning-icon">⚠️</span>
            <span>This action cannot be undone within this session.</span>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="showDeleteFileModal = false">Cancel</button>
          <button class="btn btn-danger" @click="deleteFile" :disabled="!deleteFileForm.filename">Delete File</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import api from '@/utils/api'
import { useToastStore } from '@/stores/toastStore'

const props = defineProps({
  sessionId: { type: String, required: true },
  files: { type: Array, default: () => [] }
})

const emit = defineEmits(['file-updated', 'file-added', 'file-removed'])
const toast = useToastStore()

const saving = ref(false)
const pendingChanges = ref([])
const showAddRowModal = ref(false)
const showAddFileModal = ref(false)
const showDeleteFileModal = ref(false)

const addRowForm = reactive({ filename: '', rowData: '' })
const addFileForm = reactive({ filename: '', group: '', headers: '' })
const deleteFileForm = reactive({ filename: '' })

const hasChanges = computed(() => pendingChanges.value.length > 0)
const totalChanges = computed(() => pendingChanges.value.length)
const pendingChangesList = computed(() => pendingChanges.value)

function recordChange(type, filename, detail) {
  pendingChanges.value.push({ type, filename, detail, timestamp: new Date() })
}

async function saveAllChanges() {
  if (!hasChanges.value) return
  saving.value = true
  try {
    await api.post(`/conversion/save-edits/${props.sessionId}`, { changes: pendingChanges.value })
    toast.success('All changes saved successfully')
    pendingChanges.value = []
  } catch (e) {
    toast.error('Failed to save changes: ' + (e.response?.data?.detail || e.message))
  } finally {
    saving.value = false
  }
}

function discardChanges() {
  if (!confirm('Discard all pending changes?')) return
  pendingChanges.value = []
  toast.info('Changes discarded')
}

async function addRow() {
  if (!addRowForm.filename || !addRowForm.rowData) return
  try {
    const rowData = JSON.parse(addRowForm.rowData)
    await api.post(`/conversion/add-row/${props.sessionId}`, { filename: addRowForm.filename, row: rowData })
    recordChange('ADD_ROW', addRowForm.filename, 'New row added')
    toast.success('Row added successfully')
    emit('file-updated', addRowForm.filename)
    showAddRowModal.value = false
    addRowForm.filename = ''
    addRowForm.rowData = ''
  } catch (e) {
    toast.error('Failed to add row: ' + (e.response?.data?.detail || e.message))
  }
}

async function addFile() {
  if (!addFileForm.filename || !addFileForm.headers) return
  try {
    const headers = addFileForm.headers.split(',').map(h => h.trim())
    await api.post(`/conversion/add-file/${props.sessionId}`, {
      filename: addFileForm.filename,
      group: addFileForm.group || 'DEFAULT',
      headers
    })
    recordChange('ADD_FILE', addFileForm.filename, `New file with ${headers.length} columns`)
    toast.success('File created successfully')
    emit('file-added', addFileForm.filename)
    showAddFileModal.value = false
    addFileForm.filename = ''
    addFileForm.group = ''
    addFileForm.headers = ''
  } catch (e) {
    toast.error('Failed to create file: ' + (e.response?.data?.detail || e.message))
  }
}

async function deleteFile() {
  if (!deleteFileForm.filename) return
  try {
    await api.delete(`/conversion/delete-file/${props.sessionId}/${deleteFileForm.filename}`)
    recordChange('DELETE', deleteFileForm.filename, 'File removed')
    toast.success('File deleted')
    emit('file-removed', deleteFileForm.filename)
    showDeleteFileModal.value = false
    deleteFileForm.filename = ''
  } catch (e) {
    toast.error('Failed to delete file: ' + (e.response?.data?.detail || e.message))
  }
}
</script>

<style scoped>
.edit-mode-panel { background: var(--brand-subtle); border: 2px solid var(--brand-primary); border-radius: var(--radius-md); padding: var(--space-lg); margin-top: var(--space-lg); }
.panel-header { margin-bottom: var(--space-md); }
.panel-title { margin: 0 0 var(--space-xs); font-size: 1.1rem; font-weight: 700; }
.panel-description { margin: 0; font-size: 0.85rem; color: var(--text-tertiary); }

.changes-summary { background: var(--surface-elevated); border-radius: var(--radius-md); padding: var(--space-md); margin-bottom: var(--space-md); }
.summary-header { display: flex; align-items: center; gap: var(--space-sm); margin-bottom: var(--space-sm); }
.summary-icon { font-size: 1.25rem; }
.summary-text { font-weight: 600; flex: 1; }
.changes-list { display: flex; flex-direction: column; gap: var(--space-xs); }
.change-item { display: flex; align-items: center; gap: var(--space-sm); padding: var(--space-xs) var(--space-sm); background: var(--surface-base); border-radius: var(--radius-sm); font-size: 0.85rem; }
.change-type { padding: 2px 8px; border-radius: var(--radius-sm); font-weight: 600; font-size: 0.75rem; }
.change-type.EDIT { background: var(--warning-bg); color: var(--warning); }
.change-type.ADD_ROW { background: var(--success-bg); color: var(--success); }
.change-type.ADD_FILE { background: var(--info-bg); color: var(--info); }
.change-type.DELETE { background: var(--error-bg); color: var(--error); }
.change-file { font-weight: 500; }
.change-detail { color: var(--text-tertiary); }

.quick-actions { display: flex; gap: var(--space-sm); flex-wrap: wrap; }

.modal-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.modal-content { background: var(--surface-elevated); border-radius: var(--radius-lg); width: 90%; max-width: 500px; overflow: hidden; box-shadow: var(--shadow-xl); }
.modal-header { display: flex; justify-content: space-between; align-items: center; padding: var(--space-md) var(--space-lg); border-bottom: 1px solid var(--border-light); }
.modal-header h4 { margin: 0; }
.modal-close { background: transparent; border: none; font-size: 1.5rem; cursor: pointer; color: var(--text-secondary); }
.modal-body { padding: var(--space-lg); }
.modal-footer { display: flex; justify-content: flex-end; gap: var(--space-sm); padding: var(--space-md) var(--space-lg); border-top: 1px solid var(--border-light); }

.warning-box { display: flex; align-items: center; gap: var(--space-sm); padding: var(--space-md); background: var(--error-bg); border-radius: var(--radius-md); color: var(--error); font-size: 0.9rem; }
.warning-icon { font-size: 1.25rem; }

.spinner-sm { display: inline-block; width: 14px; height: 14px; border: 2px solid transparent; border-top-color: currentColor; border-radius: 50%; animation: spin 0.8s linear infinite; margin-right: 6px; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
