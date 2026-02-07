<template>
  <div>
    <!-- Admin Header -->
    <div class="admin-header">
      <div class="header-grid">
        <div>
          <h2 class="card-title">Admin Console</h2>
          <p class="card-description">User management • AI agent • Sessions • Audit</p>
        </div>
        <div class="user-info">
          <div class="user-avatar">{{ userInitials }}</div>
          <div>{{ auth.user?.username }}</div>
        </div>
        <div style="display:flex; gap:8px">
          <button class="btn btn-secondary btn-sm" @click="$router.push({ name: 'main' })">
            Back to Workspace
          </button>
          <button class="btn btn-primary btn-sm" @click="refresh">Refresh</button>
        </div>
      </div>
    </div>

    <!-- Quick Stats -->
    <div class="metric-container">
      <div class="metric-card">
        <div class="metric-value">{{ stats.totalUsers }}</div>
        <div class="metric-label">Total Users</div>
      </div>
      <div class="metric-card">
        <div class="metric-value">{{ stats.admins }}</div>
        <div class="metric-label">Admins</div>
      </div>
      <div class="metric-card">
        <div class="metric-value">{{ stats.regular }}</div>
        <div class="metric-label">Regular Users</div>
      </div>
    </div>

    <!-- Admin Tabs -->
    <div class="tab-list" role="tablist">
      <button 
        v-for="(tab, idx) in tabs" 
        :key="idx"
        class="tab-button"
        :class="{ active: activeTab === idx }"
        @click="activeTab = idx"
      >
        {{ tab }}
      </button>
    </div>

    <!-- TAB 0: AI Agent -->
    <div v-show="activeTab === 0" class="enterprise-card">
      <div class="card-header">
        <h3 class="card-title">🤖 Admin AI Agent</h3>
        <p class="card-description">Execute admin commands via natural language</p>
      </div>
      <AIAgentChat />
    </div>

    <!-- TAB 1: AI Indexing Config -->
    <div v-show="activeTab === 1" class="enterprise-card">
      <div class="card-header">
        <h3 class="card-title">🗂️ AI Indexing Configuration</h3>
        <p class="card-description">Configure which groups are automatically embedded for AI</p>
      </div>

      <div class="form-group">
        <label class="form-label">Auto-Embedded Groups</label>
        <p class="form-hint">These groups will be automatically embedded when detected during ZIP scanning</p>
      </div>

      <!-- Two-sided selector -->
      <div style="display:grid; grid-template-columns:1fr 100px 1fr; gap:var(--space-lg); margin-top:var(--space-lg); align-items:start">
        <!-- Available Groups (Left) -->
        <div class="group-selector-box">
          <h4 class="box-title">Available Groups</h4>
          <div style="display:flex; gap:8px; margin-bottom:8px">
            <input v-model="newGroup" placeholder="New Group" class="form-input" style="padding:4px 8px; font-size:0.85rem" @keyup.enter="addGroup" />
            <button class="btn btn-sm btn-secondary" @click="addGroup" :disabled="!newGroup">+</button>
          </div>
          <div class="group-list">
            <label v-for="group in availableGroupsList" :key="group" class="group-item">
              <input 
                type="checkbox" 
                :value="group" 
                v-model="selectedLeftGroups"
              />
              <span>{{ group }}</span>
            </label>
          </div>
        </div>

        <!-- Control Buttons (Center) -->
        <div class="button-column">
          <button 
            class="btn btn-primary btn-sm" 
            @click="moveToRight" 
            :disabled="!selectedLeftGroups.length"
            title="Add selected groups"
          >
            >>
          </button>
          <button 
            class="btn btn-secondary btn-sm" 
            @click="moveToLeft" 
            :disabled="!selectedRightGroups.length"
            title="Remove selected groups"
          >
            <<
          </button>
        </div>

        <!-- Auto-Embedded Groups (Right) -->
        <div class="group-selector-box">
          <h4 class="box-title">Auto-Embedded</h4>
          <div class="group-list">
            <label v-for="group in autoEmbeddedGroups" :key="group" class="group-item">
              <input 
                type="checkbox" 
                :value="group" 
                v-model="selectedRightGroups"
              />
              <span>{{ group }}</span>
            </label>
          </div>
        </div>
      </div>

      <!-- Save Button -->
      <div style="margin-top:var(--space-lg); display:flex; gap:8px">
        <button class="btn btn-primary" @click="saveEmbeddingConfig" :disabled="saving">
          <span v-if="saving" class="spinner" style="margin-right:8px"></span>
          {{ saving ? 'Saving...' : 'Save Configuration' }}
        </button>
      </div>

      <!-- Status Messages -->
      <div v-if="configStatus" class="alert" :class="configStatus.type === 'success' ? 'alert-success' : 'alert-error'" style="margin-top:var(--space-lg)">
        <div class="alert-content">{{ configStatus.message }}</div>
      </div>
    </div>

    <!-- TAB 2: Add User -->
    <div v-show="activeTab === 2" class="enterprise-card">
      <div class="card-header">
        <h3 class="card-title">➕ Add User</h3>
        <p class="card-description">Create new user and generate auth token</p>
      </div>

      <form @submit.prevent="createUser">
        <div class="form-group">
          <label class="form-label">Username</label>
          <input v-model="newUser.username" class="form-input" required placeholder="john.doe" />
        </div>
        <div class="form-group">
          <label class="form-label">Role</label>
          <select v-model="newUser.role" class="form-select">
            <option value="user">Regular User</option>
            <option value="admin">Admin</option>
          </select>
        </div>
        <div class="form-group">
          <label class="form-label">Token TTL (minutes)</label>
          <input v-model.number="newUser.tokenTTL" type="number" class="form-input" placeholder="60" />
          <div class="form-hint">How long the auth token will remain valid</div>
        </div>
        <div class="form-group">
          <label class="form-label">Note (Optional)</label>
          <textarea v-model="newUser.note" class="form-textarea" rows="3" placeholder="Admin notes..."></textarea>
        </div>
        <button class="btn btn-primary" :disabled="creating" type="submit">
          <span v-if="creating" class="spinner" style="margin-right:8px"></span>
          {{ creating ? 'Creating...' : 'Create User + Generate Token' }}
        </button>
      </form>

      <div v-if="createdToken" class="alert alert-success" style="margin-top:var(--space-lg)">
        <div class="alert-content">
          <div class="alert-title">✅ User Created Successfully!</div>
          <div style="margin-top:var(--space-sm)">
            <strong>Auth Token (save this, won't be shown again):</strong>
            <pre style="margin-top:var(--space-xs); background:var(--surface-base); padding:var(--space-sm); border-radius:var(--radius-sm); overflow-x:auto">{{ createdToken }}</pre>
          </div>
        </div>
      </div>
    </div>

    <!-- TAB 3: Manage User -->
    <div v-show="activeTab === 3" class="enterprise-card">
      <div class="card-header">
        <h3 class="card-title">⚙️ Manage User</h3>
        <p class="card-description">Update roles, unlock accounts, generate reset tokens</p>
      </div>

      <div class="form-group">
        <label class="form-label">Select User</label>
        <select v-model="selectedUserId" @change="loadUserDetails" class="form-select">
          <option value="">-- Choose User --</option>
          <option v-for="u in users" :key="u.id" :value="u.id">
            {{ u.username }} ({{ u.role }})
          </option>
        </select>
      </div>

      <div v-if="selectedUser" style="margin-top:var(--space-lg)">
        <!-- User Info Grid -->
        <div class="info-grid">
          <div class="info-item">
            <div class="info-label">Username</div>
            <div class="info-value">{{ selectedUser.username }}</div>
          </div>
          <div class="info-item">
            <div class="info-label">Role</div>
            <div class="info-value">
              <span class="status-badge" :class="selectedUser.role === 'admin' ? 'badge-warning' : 'badge-info'">
                {{ selectedUser.role }}
              </span>
            </div>
          </div>
          <div class="info-item">
            <div class="info-label">Created At</div>
            <div class="info-value">{{ formatDate(selectedUser.created_at) }}</div>
          </div>
          <div class="info-item">
            <div class="info-label">Updated At</div>
            <div class="info-value">{{ formatDate(selectedUser.updated_at) }}</div>
          </div>
          <div class="info-item">
            <div class="info-label">Account Status</div>
            <div class="info-value">
              <span
                class="status-badge"
                :class="selectedUser.is_locked ? 'badge-error' : (selectedUser.is_active ? 'badge-success' : 'badge-warning')"
              >
                {{ selectedUser.is_locked ? 'Locked' : (selectedUser.is_active ? 'Active' : 'Disabled') }}
              </span>
            </div>
          </div>
        </div>

        <hr class="divider" />

        <!-- Update Role Section -->
        <div class="enterprise-card">
          <h4 class="card-title">Update Role</h4>
          <div style="display:flex; gap:12px; align-items:end; margin-top:var(--space-md)">
            <div class="form-group" style="flex:1; margin-bottom:0">
              <label class="form-label">New Role</label>
              <select v-model="updateRole.newRole" class="form-select">
                <option value="user">Regular User</option>
                <option value="admin">Admin</option>
              </select>
            </div>
            <button class="btn btn-primary" @click="updateUserRole">Update Role</button>
          </div>
        </div>

        <!-- Generate Reset Token Section -->
        <div class="enterprise-card" style="margin-top:var(--space-lg)">
          <h4 class="card-title">Generate Password Reset Token</h4>
          <p class="card-description">Create a one-time token for user to reset password</p>
          <button class="btn btn-warning" @click="generateResetToken" style="margin-top:var(--space-md)">
            Generate Reset Token
          </button>
          <div v-if="resetToken" class="alert alert-info" style="margin-top:var(--space-md)">
            <div class="alert-content">
              <strong>Reset Token:</strong>
              <pre style="margin-top:var(--space-xs); background:var(--surface-base); padding:var(--space-sm); border-radius:var(--radius-sm)">{{ resetToken }}</pre>
            </div>
          </div>
        </div>

        <!-- Unlock Account Section -->
        <div v-if="selectedUser.is_locked" class="enterprise-card" style="margin-top:var(--space-lg)">
          <h4 class="card-title">Unlock Account</h4>
          <p class="card-description">This account is currently locked due to failed login attempts</p>
          <button class="btn btn-success" @click="unlockAccount" style="margin-top:var(--space-md)">
            Unlock Now
          </button>
        </div>

        <!-- Danger Zone -->
        <div class="enterprise-card" style="margin-top:var(--space-lg); border:2px solid var(--error)">
          <h4 class="card-title" style="color:var(--error)">⚠️ Danger Zone</h4>
          <p class="card-description">Permanently delete this user and all associated data. This cannot be undone.</p>
          <button class="btn btn-danger" @click="confirmDelete" style="margin-top:var(--space-md)">
            Delete User Permanently
          </button>
        </div>
      </div>
    </div>

    <!-- TAB 4: All Users -->
    <div v-show="activeTab === 4" class="enterprise-card">
      <div class="card-header">
        <div style="display:flex; justify-content:space-between; align-items:center">
          <div>
            <h3 class="card-title">👥 All Users</h3>
            <p class="card-description">Complete user directory</p>
          </div>
          <button class="btn btn-primary" @click="activeTab = 2">
            Add New User
          </button>
        </div>
      </div>
      
      <div class="data-table-wrapper">
        <table class="data-table">
          <thead>
            <tr>
              <th>Username</th>
              <th>Role</th>
              <th>Created</th>
              <th>Updated</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="u in users" :key="u.id">
              <td><strong>{{ u.username }}</strong></td>
              <td>
                <span class="status-badge" :class="u.role === 'admin' ? 'badge-warning' : 'badge-info'">
                  {{ u.role }}
                </span>
              </td>
              <td>{{ formatDate(u.created_at) }}</td>
              <td>{{ formatDate(u.updated_at) }}</td>
              <td>
                <span
                  class="status-badge"
                  :class="u.is_locked ? 'badge-error' : (u.is_active ? 'badge-success' : 'badge-warning')"
                >
                  {{ u.is_locked ? 'Locked' : (u.is_active ? 'Active' : 'Disabled') }}
                </span>
              </td>
              <td>
                <button class="btn btn-sm btn-secondary" @click="editUser(u)">Edit</button>
                <button class="btn btn-sm btn-danger" @click="deleteUser(u)">Delete</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- TAB 5: Reset Requests -->
    <div v-show="activeTab === 5" class="enterprise-card">
      <div class="card-header">
        <h3 class="card-title">🔑 Password Reset Requests</h3>
        <p class="card-description">Pending and completed reset token requests</p>
      </div>

      <div v-if="resetRequests.length === 0" class="alert alert-info">
        <div class="alert-content">No pending reset requests</div>
      </div>

      <div v-else class="data-table-wrapper">
        <table class="data-table">
          <thead>
            <tr>
              <th>Username</th>
              <th>Reason</th>
              <th>Requested At</th>
              <th>Decided At</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in resetRequests" :key="r.id">
              <td>{{ r.username }}</td>
              <td>{{ r.reason || '—' }}</td>
              <td>{{ formatDate(r.created_at) }}</td>
              <td>{{ formatDate(r.decided_at) }}</td>
              <td>
                <span class="status-badge" :class="r.status === 'approved' ? 'badge-success' : (r.status === 'rejected' ? 'badge-error' : 'badge-warning')">
                  {{ r.status || 'pending' }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- TAB 6: Audit Logs -->
    <div v-show="activeTab === 6" class="enterprise-card">
      <div class="card-header">
        <h3 class="card-title">📋 Audit Logs</h3>
        <p class="card-description">Security and authentication events</p>
      </div>

      <div class="data-table-wrapper">
        <table class="data-table">
          <thead>
            <tr>
              <th>Timestamp</th>
              <th>Username</th>
              <th>Action</th>
              <th>Area</th>
              <th>Message</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="log in auditLogs" :key="log.id">
              <td>{{ formatDate(log.created_at) }}</td>
              <td>{{ log.username }}</td>
              <td>
                <span class="status-badge" :class="getEventBadgeClass(log.action)">
                  {{ log.action || '—' }}
                </span>
              </td>
              <td>{{ log.area || '—' }}</td>
              <td>{{ log.message || '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- TAB 7: Ops Logs -->
    <div v-show="activeTab === 7" class="enterprise-card">
      <div class="card-header">
        <h3 class="card-title">⚙️ Operations Logs</h3>
        <p class="card-description">System operations and conversions</p>
      </div>

      <div class="data-table-wrapper">
        <table class="data-table">
          <thead>
            <tr>
              <th>Timestamp</th>
              <th>User</th>
              <th>Area</th>
              <th>Action</th>
              <th>Message</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="log in opsLogs" :key="log.id">
              <td>{{ formatDate(log.created_at) }}</td>
              <td>{{ log.username || '—' }}</td>
              <td>
                <span class="status-badge badge-info">{{ log.area }}</span>
              </td>
              <td><strong>{{ log.action }}</strong></td>
              <td>{{ log.message }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- TAB 8: Sessions -->
    <div v-show="activeTab === 8" class="enterprise-card">
      <div class="card-header">
        <div style="display:flex; justify-content:space-between; align-items:center">
          <div>
            <h3 class="card-title">💾 Active Sessions</h3>
            <p class="card-description">User session management</p>
          </div>
          <button class="btn btn-danger btn-sm" @click="cleanupSessions">
            Cleanup Old Sessions
          </button>
        </div>
      </div>

      <div class="data-table-wrapper">
        <table class="data-table">
          <thead>
            <tr>
              <th>Session ID</th>
              <th>Username</th>
              <th>Created</th>
              <th>Last Activity</th>
              <th>Size</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="session in sessions" :key="session.session_id">
              <td><code>{{ session.session_id.substring(0, 12) }}...</code></td>
              <td>{{ session.username }}</td>
              <td>{{ formatDate(session.created_at) }}</td>
              <td>{{ formatDate(session.last_activity) }}</td>
              <td>{{ session.size || '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useAuthStore } from '@/stores/authStore'
import { useToastStore } from '@/stores/toastStore'
import { useRouter } from 'vue-router'
import AIAgentChat from '@/components/admin/AIAgentChat.vue'
import api from '@/utils/api'
import { format } from 'date-fns'

const auth = useAuthStore()
const toast = useToastStore()
const router = useRouter()
const activeTab = ref(0)

const tabs = [
  'AI Agent',
  'AI Indexing Config',
  'Add User',
  'Manage User',
  'All Users',
  'Reset Requests',
  'Audit Logs',
  'Ops Logs',
  'Sessions'
]

const stats = reactive({ totalUsers: 0, admins: 0, regular: 0 })
const users = ref([])
const selectedUserId = ref('')
const selectedUser = ref(null)
const newUser = reactive({ username: '', role: 'user', tokenTTL: 60, note: '' })
const creating = ref(false)
const createdToken = ref(null)
const updateRole = reactive({ newRole: 'user' })
const resetToken = ref(null)
const resetRequests = ref([])
const auditLogs = ref([])
const opsLogs = ref([])
const sessions = ref([])

const userInitials = computed(() => {
  if (!auth.user?.username) return 'A'
  return auth.user.username.split(' ').map(s => s[0]).slice(0, 2).join('').toUpperCase()
})

// AI Embedding Configuration
const availableGroupsList = ref([])
const autoEmbeddedGroups = ref([])
const selectedLeftGroups = ref([])
const selectedRightGroups = ref([])
const newGroup = ref('')
const saving = ref(false)
const configStatus = ref(null)

function addGroup() {
  if (!newGroup.value) return
  const val = newGroup.value.toUpperCase().trim()
  if (!availableGroupsList.value.includes(val) && !autoEmbeddedGroups.value.includes(val)) {
    availableGroupsList.value.push(val)
  }
  newGroup.value = ''
}

function formatDate(d) {
  if (!d) return '—'
  try {
    return format(new Date(d), 'MMM dd, yyyy HH:mm')
  } catch {
    return d
  }
}

function getEventBadgeClass(action) {
  const lower = (action || '').toLowerCase()
  if (lower.includes('login') && lower.includes('success')) return 'badge-success'
  if (lower.includes('login') && lower.includes('fail')) return 'badge-error'
  if (lower.includes('logout')) return 'badge-info'
  if (lower.includes('delete') || lower.includes('lock') || lower.includes('error')) return 'badge-error'
  return 'badge-warning'
}

async function refresh() {
  try {
    const [statsRes, usersRes, resetRes, auditRes, opsRes, sessionsRes] = await Promise.all([
      api.get('/admin/stats'),
      api.get('/admin/users'),
      api.get('/admin/reset-requests'),
      api.get('/admin/audit-logs'),
      api.get('/admin/ops-logs'),
      api.get('/admin/sessions')
    ])
    
    Object.assign(stats, statsRes.data)
    users.value = usersRes.data || []
    resetRequests.value = resetRes.data || []
    auditLogs.value = auditRes.data || []
    opsLogs.value = opsRes.data || []
    sessions.value = sessionsRes.data || []
  } catch (e) {
    console.error('Failed to refresh admin data:', e)
  }
}

async function loadUserDetails() {
  if (!selectedUserId.value) return
  try {
    const res = await api.get(`/admin/users/${selectedUserId.value}`)
    selectedUser.value = res.data
    updateRole.newRole = res.data.role
    resetToken.value = null
  } catch (e) {
    toast.error('Failed to load user details')
  }
}

async function createUser() {
  creating.value = true
  createdToken.value = null
  try {
    const res = await api.post('/admin/users', newUser)
    createdToken.value = res.data.token
    Object.assign(newUser, { username: '', role: 'user', tokenTTL: 60, note: '' })
    toast.success('User created successfully')
    await refresh()
  } catch (e) {
    toast.error('Failed to create user: ' + (e.response?.data?.message || e.message))
  } finally {
    creating.value = false
  }
}

async function updateUserRole() {
  try {
    await api.put(`/admin/users/${selectedUserId.value}/role`, { role: updateRole.newRole })
    toast.success('Role updated successfully')
    await loadUserDetails()
    await refresh()
  } catch (e) {
    toast.error('Failed to update role')
  }
}

async function generateResetToken() {
  try {
    const res = await api.post(`/admin/users/${selectedUserId.value}/reset-token`)
    resetToken.value = res.data.token
    toast.success('Reset token generated')
  } catch (e) {
    toast.error('Failed to generate token')
  }
}

async function unlockAccount() {
  try {
    await api.post(`/admin/users/${selectedUserId.value}/unlock`)
    toast.success('Account unlocked')
    await loadUserDetails()
  } catch (e) {
    toast.error('Failed to unlock account')
  }
}

async function confirmDelete() {
  if (!confirm(`⚠️ Delete user "${selectedUser.value?.username}"? This action cannot be undone.`)) return
  try {
    await api.delete(`/admin/users/${selectedUserId.value}`)
    toast.success('User deleted')
    selectedUserId.value = ''
    selectedUser.value = null
    await refresh()
  } catch (e) {
    toast.error('Failed to delete user')
  }
}

function editUser(u) {
  selectedUserId.value = u.id
  activeTab.value = 3
  loadUserDetails()
}

async function deleteUser(u) {
  if (!confirm(`⚠️ Delete user "${u.username}"?`)) return
  try {
    await api.delete(`/admin/users/${u.id}`)
    toast.success(`User ${u.username} deleted`)
    await refresh()
  } catch (e) {
    toast.error('Failed to delete user')
  }
}

async function cleanupSessions() {
  if (!confirm('Clean up sessions older than 24 hours?')) return
  try {
    await api.post('/admin/sessions/cleanup')
    toast.success('Cleanup complete')
    await refresh()
  } catch (e) {
    toast.error('Cleanup failed')
  }
}

// AI Embedding Configuration Functions
function moveToRight() {
  autoEmbeddedGroups.value.push(...selectedLeftGroups.value)
  autoEmbeddedGroups.value = [...new Set(autoEmbeddedGroups.value)]
  availableGroupsList.value = availableGroupsList.value.filter(g => !selectedLeftGroups.value.includes(g))
  selectedLeftGroups.value = []
}

function moveToLeft() {
  availableGroupsList.value.push(...selectedRightGroups.value)
  availableGroupsList.value = [...new Set(availableGroupsList.value)]
  autoEmbeddedGroups.value = autoEmbeddedGroups.value.filter(g => !selectedRightGroups.value.includes(g))
  selectedRightGroups.value = []
}

async function saveEmbeddingConfig() {
  saving.value = true
  configStatus.value = null
  try {
    await api.post('/admin/ai-indexing-config', {
      auto_embedded_groups: autoEmbeddedGroups.value
    })
    configStatus.value = {
      type: 'success',
      message: '✅ Configuration saved successfully'
    }
    setTimeout(() => {
      configStatus.value = null
    }, 3000)
  } catch (e) {
    configStatus.value = {
      type: 'error',
      message: '❌ Failed to save configuration: ' + (e.response?.data?.detail || e.message)
    }
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  await refresh()
  
  // Load AI Config
  try {
    const res = await api.get('/admin/ai-indexing-config')
    if (res.data.auto_embedded_groups) {
      autoEmbeddedGroups.value = res.data.auto_embedded_groups
      // Remove auto-embedded from available to avoid duplicates
      availableGroupsList.value = ['BOOK', 'JOURNAL', 'CONFERENCE', 'DISSERTATION', 'COMPONENT', 'OTHER']
        .filter(g => !autoEmbeddedGroups.value.includes(g))
    }
  } catch (e) {
    console.error("Failed to load AI config", e)
    availableGroupsList.value = ['BOOK', 'JOURNAL', 'CONFERENCE', 'DISSERTATION', 'COMPONENT']
  }
})
</script>

<style scoped>
.group-selector-box {
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  padding: var(--space-md);
  background: var(--surface-alt);
  min-height: 200px;
}

.box-title {
  margin: 0 0 var(--space-md) 0;
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary);
}

.group-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
  max-height: 300px;
  overflow-y: auto;
}

.group-item {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  padding: 6px 8px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: background-color 0.2s;
  font-size: 0.9rem;
}

.group-item:hover {
  background-color: var(--surface-base);
}

.group-item input[type="checkbox"] {
  cursor: pointer;
  width: 18px;
  height: 18px;
}

.button-column {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
  justify-content: center;
}

.button-column .btn {
  width: 100%;
  padding: 8px;
  font-weight: 600;
  font-size: 1.1rem;
}

.alert-success {
  background-color: #dcfce7;
  border-left: 4px solid var(--success);
  color: var(--success);
}

.alert-error {
  background-color: #fee2e2;
  border-left: 4px solid var(--error);
  color: var(--error);
}
</style>
