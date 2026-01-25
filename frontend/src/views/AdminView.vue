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

    <!-- TAB 1: Add User -->
    <div v-show="activeTab === 1" class="enterprise-card">
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

    <!-- TAB 2: Manage User -->
    <div v-show="activeTab === 2" class="enterprise-card">
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
            <div class="info-label">Last Login</div>
            <div class="info-value">{{ formatDate(selectedUser.last_login_at) }}</div>
          </div>
          <div class="info-item">
            <div class="info-label">Failed Login Attempts</div>
            <div class="info-value">{{ selectedUser.failed_login_attempts || 0 }}</div>
          </div>
          <div class="info-item">
            <div class="info-label">Account Status</div>
            <div class="info-value">
              <span class="status-badge" :class="selectedUser.locked_until ? 'badge-error' : 'badge-success'">
                {{ selectedUser.locked_until ? 'Locked' : 'Active' }}
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
        <div v-if="selectedUser.locked_until" class="enterprise-card" style="margin-top:var(--space-lg)">
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

    <!-- TAB 3: All Users -->
    <div v-show="activeTab === 3" class="enterprise-card">
      <div class="card-header">
        <div style="display:flex; justify-content:space-between; align-items:center">
          <div>
            <h3 class="card-title">👥 All Users</h3>
            <p class="card-description">Complete user directory</p>
          </div>
          <button class="btn btn-primary" @click="activeTab = 1">
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
              <th>Last Login</th>
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
              <td>{{ formatDate(u.last_login_at) }}</td>
              <td>
                <span class="status-badge" :class="u.locked_until ? 'badge-error' : 'badge-success'">
                  {{ u.locked_until ? 'Locked' : 'Active' }}
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

    <!-- TAB 4: Reset Requests -->
    <div v-show="activeTab === 4" class="enterprise-card">
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
              <th>Token</th>
              <th>Requested At</th>
              <th>Used At</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in resetRequests" :key="r.id">
              <td>{{ r.username }}</td>
              <td><code>{{ r.token.substring(0, 16) }}...</code></td>
              <td>{{ formatDate(r.requested_at) }}</td>
              <td>{{ formatDate(r.used_at) }}</td>
              <td>
                <span class="status-badge" :class="r.used_at ? 'badge-success' : 'badge-warning'">
                  {{ r.used_at ? 'Used' : 'Pending' }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- TAB 5: Audit Logs -->
    <div v-show="activeTab === 5" class="enterprise-card">
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
              <th>Event</th>
              <th>Details</th>
              <th>IP Address</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="log in auditLogs" :key="log.id">
              <td>{{ formatDate(log.timestamp) }}</td>
              <td>{{ log.username }}</td>
              <td>
                <span class="status-badge" :class="getEventBadgeClass(log.event)">
                  {{ log.event }}
                </span>
              </td>
              <td>{{ log.details || '—' }}</td>
              <td><code>{{ log.ip_address || '—' }}</code></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- TAB 6: Ops Logs -->
    <div v-show="activeTab === 6" class="enterprise-card">
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
              <th>Operation</th>
              <th>Status</th>
              <th>Duration (ms)</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="log in opsLogs" :key="log.id">
              <td>{{ formatDate(log.timestamp) }}</td>
              <td>{{ log.username }}</td>
              <td>{{ log.operation }}</td>
              <td>
                <span class="status-badge" :class="log.status === 'success' ? 'badge-success' : 'badge-error'">
                  {{ log.status }}
                </span>
              </td>
              <td>{{ log.duration_ms || '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- TAB 7: Sessions -->
    <div v-show="activeTab === 7" class="enterprise-card">
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
import { useRouter } from 'vue-router'
import AIAgentChat from '@/components/admin/AIAgentChat.vue'
import api from '@/utils/api'
import { format } from 'date-fns'

const auth = useAuthStore()
const router = useRouter()
const activeTab = ref(0)

const tabs = [
  'AI Agent',
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

function formatDate(d) {
  if (!d) return '—'
  try {
    return format(new Date(d), 'MMM dd, yyyy HH:mm')
  } catch {
    return d
  }
}

function getEventBadgeClass(event) {
  const lower = event.toLowerCase()
  if (lower.includes('login_success')) return 'badge-success'
  if (lower.includes('login_failed') || lower.includes('error')) return 'badge-error'
  if (lower.includes('logout')) return 'badge-info'
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
    alert('Failed to load user details')
  }
}

async function createUser() {
  creating.value = true
  createdToken.value = null
  try {
    const res = await api.post('/admin/users', newUser)
    createdToken.value = res.data.token
    Object.assign(newUser, { username: '', role: 'user', tokenTTL: 60, note: '' })
    await refresh()
  } catch (e) {
    alert('Failed to create user: ' + (e.response?.data?.message || e.message))
  } finally {
    creating.value = false
  }
}

async function updateUserRole() {
  try {
    await api.put(`/admin/users/${selectedUserId.value}/role`, { role: updateRole.newRole })
    alert('✅ Role updated successfully')
    await loadUserDetails()
    await refresh()
  } catch (e) {
    alert('❌ Failed to update role')
  }
}

async function generateResetToken() {
  try {
    const res = await api.post(`/admin/users/${selectedUserId.value}/reset-token`)
    resetToken.value = res.data.token
  } catch (e) {
    alert('Failed to generate token')
  }
}

async function unlockAccount() {
  try {
    await api.post(`/admin/users/${selectedUserId.value}/unlock`)
    alert('✅ Account unlocked')
    await loadUserDetails()
  } catch (e) {
    alert('❌ Failed to unlock account')
  }
}

async function confirmDelete() {
  if (!confirm(`⚠️ Delete user "${selectedUser.value?.username}"? This action cannot be undone.`)) return
  try {
    await api.delete(`/admin/users/${selectedUserId.value}`)
    alert('✅ User deleted')
    selectedUserId.value = ''
    selectedUser.value = null
    await refresh()
  } catch (e) {
    alert('❌ Failed to delete user')
  }
}

function editUser(u) {
  selectedUserId.value = u.id
  activeTab.value = 2
  loadUserDetails()
}

async function deleteUser(u) {
  if (!confirm(`⚠️ Delete user "${u.username}"?`)) return
  try {
    await api.delete(`/admin/users/${u.id}`)
    await refresh()
  } catch (e) {
    alert('Failed to delete user')
  }
}

async function cleanupSessions() {
  if (!confirm('Clean up sessions older than 24 hours?')) return
  try {
    await api.post('/admin/sessions/cleanup')
    alert('✅ Cleanup complete')
    await refresh()
  } catch (e) {
    alert('❌ Cleanup failed')
  }
}

onMounted(() => {
  refresh()
})
</script>