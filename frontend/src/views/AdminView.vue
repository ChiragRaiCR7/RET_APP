<template>
  <div>
    <div class="admin-header">
      <div class="header-grid">
        <div>
          <h2 class="card-title">Admin Console</h2>
          <p class="card-description">User management • AI agent • Sessions • Audit</p>
        </div>
        <div style="display:flex; gap:12px; align-items:center;">
          <div class="user-info">
            <div class="user-avatar">AD</div>
            <div>Admin</div>
          </div>
          <button class="btn btn-primary" @click="refresh">Refresh</button>
        </div>
      </div>
    </div>

    <div style="display:grid; grid-template-columns: 1fr 420px; gap:var(--space-lg)">
      <div>
        <div class="enterprise-card">
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <h3 class="card-title">All Users</h3>
            <button class="btn btn-primary" @click="openAdd">Add User</button>
          </div>
          <div class="data-table-wrapper" style="margin-top: var(--space-md)">
            <table class="data-table">
              <thead><tr><th>Username</th><th>Role</th><th>Last Login</th><th>Actions</th></tr></thead>
              <tbody>
                <tr v-for="u in users" :key="u.id">
                  <td>{{ u.username }}</td>
                  <td>{{ u.role }}</td>
                  <td>{{ u.last_login || '-' }}</td>
                  <td>
                    <button class="btn btn-sm" @click="edit(u)">Edit</button>
                    <button class="btn btn-sm btn-danger" @click="del(u)">Delete</button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <div class="enterprise-card" style="margin-top: var(--space-lg)">
          <h3 class="card-title">AI Agent</h3>
          <AIAgentChat />
        </div>
      </div>

      <div>
        <div class="enterprise-card">
          <h4 class="card-title">Reset Requests</h4>
          <div v-if="resetRequests.length === 0" class="form-hint">No pending resets</div>
          <div v-for="r in resetRequests" :key="r.id" style="margin-bottom:var(--space-sm)">
            <div style="display:flex; justify-content:space-between; gap:12px;">
              <div>{{ r.username }} • {{ r.requested_at }}</div>
              <div style="display:flex; gap:8px">
                <button class="btn btn-sm btn-primary">Approve</button>
                <button class="btn btn-sm">Deny</button>
              </div>
            </div>
          </div>
        </div>

        <div class="enterprise-card" style="margin-top:var(--space-lg)">
          <h4 class="card-title">Operations Logs</h4>
          <div style="max-height:320px; overflow:auto">
            <pre style="white-space:pre-wrap">{{ opsLogs.join('\n') }}</pre>
          </div>
        </div>
      </div>
    </div>

    <!-- Add/Edit modal could be placed here -->
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import AIAgentChat from '@/components/admin/AIAgentChat.vue'
import api from '@/utils/api'

const users = ref([])
const resetRequests = ref([])
const opsLogs = ref([])

async function refresh() {
  try {
    const [u, r, o] = await Promise.all([
      api.get('/admin/users'),
      api.get('/admin/reset-requests'),
      api.get('/admin/ops-logs')
    ])
    users.value = u.data || []
    resetRequests.value = r.data || []
    opsLogs.value = o.data?.logs || []
  } catch (e) {
    console.warn('failed to refresh', e)
  }
}

onMounted(refresh)

function openAdd() {
  alert('Open add user modal (not yet implemented)')
}
function edit(u) {
  alert('Edit user ' + u.username)
}
function del(u) {
  if (!confirm('Delete user ' + u.username + '?')) return
  // call backend
  api.delete('/admin/users/' + u.id).then(refresh)
}
</script>
