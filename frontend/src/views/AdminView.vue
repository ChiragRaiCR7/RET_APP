<template>
  <div class="admin-shell">
    <!-- Header -->
    <header class="admin-header" role="banner">
      <div class="header-left">
        <h2 class="page-title">Admin Console</h2>
        <p class="page-subtitle">
          Manage users, AI configuration, sessions, and security logs in one place.
        </p>
      </div>

      <div class="header-right">
        <div class="user-pill" aria-label="Signed in user">
          <div class="avatar" aria-hidden="true">{{ userInitials }}</div>
          <div class="user-meta">
            <div class="user-name">{{ auth.user?.username || 'Admin' }}</div>
            <div class="user-role">Administrator</div>
          </div>
        </div>

        <div class="header-actions">
          <button class="btn btn-secondary" @click="router.push({ name: 'main' })">
            Back to workspace
          </button>
          <button class="btn btn-primary" @click="refresh" :disabled="refreshing">
            <span v-if="refreshing" class="spinner" aria-hidden="true"></span>
            {{ refreshing ? 'Refreshing…' : 'Refresh' }}
          </button>
        </div>
      </div>
    </header>

    <!-- Metrics -->
    <section class="metrics" aria-label="Quick metrics">
      <div class="metric-card">
        <div class="metric-value">{{ stats.totalUsers }}</div>
        <div class="metric-label">Total users</div>
      </div>
      <div class="metric-card">
        <div class="metric-value">{{ stats.admins }}</div>
        <div class="metric-label">Admins</div>
      </div>
      <div class="metric-card">
        <div class="metric-value">{{ stats.regular }}</div>
        <div class="metric-label">Regular users</div>
      </div>
      <div class="metric-card metric-soft">
        <div class="metric-value">{{ sessions?.length || 0 }}</div>
        <div class="metric-label">Active sessions</div>
      </div>
    </section>

    <!-- Tabs -->
    <nav class="tabs" role="tablist" aria-label="Admin sections">
      <button
        v-for="(t, idx) in tabs"
        :key="t.key"
        class="tab"
        role="tab"
        :id="`admin-tab-${t.key}`"
        :aria-controls="`admin-panel-${t.key}`"
        :aria-selected="activeTab === idx"
        :tabindex="activeTab === idx ? 0 : -1"
        :class="{ active: activeTab === idx }"
        @click="setTab(idx)"
        @keydown="onTabKeydown($event, idx)"
        type="button"
      >
        <span class="tab-icon" aria-hidden="true">{{ t.icon }}</span>
        <span class="tab-label">{{ t.label }}</span>
      </button>
    </nav>

    <!-- Panels -->
    <section class="panel-stack">
      <!-- 0: AI Agent -->
      <section
        v-show="activeTab === 0"
        class="card"
        role="tabpanel"
        :id="'admin-panel-ai-agent'"
        :aria-labelledby="'admin-tab-ai-agent'"
      >
        <div class="card-header">
          <div>
            <h3 class="card-title">Admin Assistant</h3>
            <p class="card-subtitle">
              Run administrative actions using natural language. Review responses before applying changes.
            </p>
          </div>
        </div>

        <div class="card-body">
          <AIAgentChat />
        </div>
      </section>

      <!-- 1: AI Indexing Config -->
      <section
        v-show="activeTab === 1"
        class="card"
        role="tabpanel"
        :id="'admin-panel-ai-indexing'"
        :aria-labelledby="'admin-tab-ai-indexing'"
      >
        <div class="card-header">
          <div>
            <h3 class="card-title">AI Indexing Configuration</h3>
            <p class="card-subtitle">
              Choose which groups should be automatically prepared for AI search and chat.
            </p>
          </div>
          <div class="card-actions">
            <button class="btn btn-secondary" @click="reloadAIConfig" :disabled="aiConfigLoading">
              <span v-if="aiConfigLoading" class="spinner" aria-hidden="true"></span>
              {{ aiConfigLoading ? 'Loading…' : 'Reload' }}
            </button>
          </div>
        </div>

        <div class="card-body">
          <div class="summary-strip" role="status" aria-live="polite">
            <div class="summary-pill" :class="autoEmbedEnabled ? 'summary-on' : 'summary-off'">
              Auto-embed: <strong>{{ autoEmbedEnabled ? 'Enabled' : 'Disabled' }}</strong>
            </div>
            <div class="summary-pill">
              Enabled groups: <strong>{{ autoEmbeddedGroups.length }}</strong>
            </div>
          </div>

          <div class="info-banner" role="note">
            <div class="info-title">How it works</div>
            <div class="info-text">
              Enable auto-embed to prepare selected groups during scan. Use the dual list to control which groups are included.
            </div>
          </div>

          <div class="config-top-row">
            <label class="toggle-inline" aria-label="Enable auto-embedding">
              <input type="checkbox" v-model="autoEmbedEnabled" />
              <span>Enable automatic embedding for selected groups</span>
            </label>
            <p class="help">When disabled, selected groups remain configured but no auto-embed job is started after scan.</p>
          </div>

          <div class="dual-selector">
            <!-- Available -->
            <div class="selector">
              <div class="selector-head">
                <h4 class="selector-title">Available</h4>
                <p class="selector-subtitle">Select groups to enable.</p>
              </div>

              <div class="selector-tools">
                <input
                  v-model="availableSearch"
                  class="input"
                  type="text"
                  placeholder="Search available…"
                  aria-label="Search available groups"
                />
              </div>

              <div class="selector-add">
                <input
                  v-model="newGroup"
                  class="input"
                  type="text"
                  placeholder="Add new group (e.g., REPORT)"
                  @keyup.enter="addGroup"
                  aria-label="Add new group"
                />
                <button class="btn btn-secondary btn-sm" @click="addGroup" :disabled="!newGroup">
                  Add
                </button>
              </div>

              <div class="selector-list" role="group" aria-label="Available groups">
                <label v-for="g in filteredAvailableGroups" :key="g" class="check-row">
                  <input type="checkbox" :value="g" v-model="selectedLeftGroups" />
                  <span class="check-label">{{ formatOracleGroupLabel(g) }}</span>
                </label>

                <div v-if="filteredAvailableGroups.length === 0" class="empty-small">
                  No groups found.
                </div>
              </div>
            </div>

            <!-- Middle controls -->
            <div class="selector-controls" aria-label="Move controls">
              <button
                class="btn btn-primary btn-sm"
                @click="moveToRight"
                :disabled="!selectedLeftGroups.length"
                title="Enable selected"
              >
                Enable →
              </button>
              <button
                class="btn btn-secondary btn-sm"
                @click="moveToLeft"
                :disabled="!selectedRightGroups.length"
                title="Disable selected"
              >
                ← Disable
              </button>
              <p class="muted selector-hint">
                Select items in either list, then move.
              </p>
            </div>

            <!-- Enabled -->
            <div class="selector">
              <div class="selector-head">
                <h4 class="selector-title">Auto-enabled</h4>
                <p class="selector-subtitle">Prepared automatically during scanning.</p>
              </div>

              <div class="selector-tools">
                <input
                  v-model="enabledSearch"
                  class="input"
                  type="text"
                  placeholder="Search enabled…"
                  aria-label="Search enabled groups"
                />
              </div>

              <div class="selector-list" role="group" aria-label="Auto-enabled groups">
                <label v-for="g in filteredEnabledGroups" :key="g" class="check-row">
                  <input type="checkbox" :value="g" v-model="selectedRightGroups" />
                  <span class="check-label">{{ formatOracleGroupLabel(g) }}</span>
                </label>

                <div v-if="filteredEnabledGroups.length === 0" class="empty-small">
                  No groups enabled.
                </div>
              </div>
            </div>
          </div>

          <div class="action-row">
            <button class="btn btn-primary" @click="saveEmbeddingConfig" :disabled="saving">
              <span v-if="saving" class="spinner" aria-hidden="true"></span>
              {{ saving ? 'Saving…' : 'Save configuration' }}
            </button>

            <span class="muted">
              Changes apply to new sessions after saving.
            </span>
          </div>

          <div
            v-if="configStatus"
            class="alert"
            :class="configStatus.type === 'success' ? 'alert-success' : 'alert-error'"
            role="status"
            aria-live="polite"
          >
            {{ configStatus.message }}
          </div>
        </div>
      </section>

      <!-- 2: Add User -->
      <section
        v-show="activeTab === 2"
        class="card"
        role="tabpanel"
        :id="'admin-panel-add-user'"
        :aria-labelledby="'admin-tab-add-user'"
      >
        <div class="card-header">
          <div>
            <h3 class="card-title">Create user</h3>
            <p class="card-subtitle">
              Create a user and generate a token. Tokens are shown once—copy and store securely.
            </p>
          </div>
        </div>

        <div class="card-body">
          <form class="form" @submit.prevent="createUser">
            <div class="form-grid">
              <div class="field">
                <label class="label">Username</label>
                <input v-model="newUser.username" class="input" required placeholder="john.doe" />
                <p class="help">Use a unique username. Avoid spaces where possible.</p>
              </div>

              <div class="field">
                <label class="label">Role</label>
                <select v-model="newUser.role" class="select">
                  <option value="user">Regular user</option>
                  <option value="admin">Admin</option>
                </select>
                <p class="help">Admins can manage users, sessions, and logs.</p>
              </div>

              <div class="field">
                <label class="label">Token TTL (minutes)</label>
                <input v-model.number="newUser.tokenTTL" type="number" class="input" placeholder="60" min="1" />
                <p class="help">How long the token remains valid after creation.</p>
              </div>

              <div class="field field-full">
                <label class="label">Note (optional)</label>
                <textarea v-model="newUser.note" class="textarea" rows="3" placeholder="Internal notes…"></textarea>
              </div>
            </div>

            <div class="action-row">
              <button class="btn btn-primary" :disabled="creating" type="submit">
                <span v-if="creating" class="spinner" aria-hidden="true"></span>
                {{ creating ? 'Creating…' : 'Create user & generate token' }}
              </button>
              <span class="muted">You can manage the user after creation in “Manage user”.</span>
            </div>
          </form>

          <div v-if="createdToken" class="token-card" role="status" aria-live="polite">
            <div class="token-header">
              <strong>Token generated</strong>
              <div class="token-actions">
                <button class="btn btn-secondary btn-sm" @click="copyToClipboard(createdToken)">
                  Copy
                </button>
                <button class="btn btn-secondary btn-sm" @click="createdToken = null">
                  Dismiss
                </button>
              </div>
            </div>
            <p class="help">
              Store this token securely. It will not be shown again after you close this card.
            </p>
            <pre class="token-value">{{ createdToken }}</pre>
          </div>
        </div>
      </section>

      <!-- 3: Manage User -->
      <section
        v-show="activeTab === 3"
        class="card"
        role="tabpanel"
        :id="'admin-panel-manage-user'"
        :aria-labelledby="'admin-tab-manage-user'"
      >
        <div class="card-header">
          <div>
            <h3 class="card-title">Manage user</h3>
            <p class="card-subtitle">
              Update roles, unlock accounts, and generate reset tokens.
            </p>
          </div>
        </div>

        <div class="card-body">
          <div class="form-grid">
            <div class="field field-full">
              <label class="label">Select user</label>
              <select v-model="selectedUserId" @change="loadUserDetails" class="select">
                <option value="">Select a user…</option>
                <option v-for="u in users" :key="u.id" :value="u.id">
                  {{ u.username }} ({{ u.role }})
                </option>
              </select>
              <p class="help">Choose a user to view account details and actions.</p>
            </div>
          </div>

          <div v-if="!selectedUser && selectedUserId" class="empty-state">
            <div class="empty-title">Loading user details…</div>
            <div class="empty-text">Please wait while we fetch the profile.</div>
          </div>

          <div v-if="selectedUser" class="manage-grid">
            <!-- User summary -->
            <div class="subcard">
              <div class="subcard-head">
                <h4 class="subcard-title">User details</h4>
                <span
                  class="badge"
                  :class="selectedUser.is_locked ? 'badge-error' : (selectedUser.is_active ? 'badge-success' : 'badge-warning')"
                >
                  {{ selectedUser.is_locked ? 'Locked' : (selectedUser.is_active ? 'Active' : 'Disabled') }}
                </span>
              </div>

              <div class="info-grid">
                <div class="info-item">
                  <div class="info-k">Username</div>
                  <div class="info-v">{{ selectedUser.username }}</div>
                </div>
                <div class="info-item">
                  <div class="info-k">Role</div>
                  <div class="info-v">
                    <span class="badge" :class="selectedUser.role === 'admin' ? 'badge-warning' : 'badge-info'">
                      {{ selectedUser.role }}
                    </span>
                  </div>
                </div>
                <div class="info-item">
                  <div class="info-k">Created</div>
                  <div class="info-v">{{ formatDate(selectedUser.created_at) }}</div>
                </div>
                <div class="info-item">
                  <div class="info-k">Updated</div>
                  <div class="info-v">{{ formatDate(selectedUser.updated_at) }}</div>
                </div>
              </div>
            </div>

            <!-- Actions -->
            <div class="subcard">
              <div class="subcard-head">
                <h4 class="subcard-title">Actions</h4>
                <p class="subcard-subtitle">Changes are logged for audit.</p>
              </div>

              <!-- Update role -->
              <div class="action-block">
                <div class="action-block-title">Update role</div>
                <div class="action-inline">
                  <select v-model="updateRole.newRole" class="select">
                    <option value="user">Regular user</option>
                    <option value="admin">Admin</option>
                  </select>
                  <button class="btn btn-primary" @click="updateUserRole" :disabled="!selectedUserId">
                    Update
                  </button>
                </div>
                <p class="help">Role changes take effect immediately.</p>
              </div>

              <div class="divider" role="separator"></div>

              <!-- Reset token -->
              <div class="action-block">
                <div class="action-block-title">Generate password reset token</div>
                <p class="help">Create a one-time token for the user to reset their password.</p>
                <button class="btn btn-secondary" @click="generateResetToken" :disabled="!selectedUserId">
                  Generate token
                </button>

                <div v-if="resetToken" class="token-inline" role="status" aria-live="polite">
                  <pre class="token-value">{{ resetToken }}</pre>
                  <button class="btn btn-secondary btn-sm" @click="copyToClipboard(resetToken)">Copy</button>
                </div>
              </div>

              <!-- Unlock -->
              <div v-if="selectedUser.is_locked" class="action-block warn">
                <div class="action-block-title">Unlock account</div>
                <p class="help">This account is locked due to failed authentication attempts.</p>
                <button class="btn btn-success" @click="unlockAccount">Unlock now</button>
              </div>

              <div class="divider" role="separator"></div>

              <!-- Danger zone -->
              <div class="action-block danger">
                <div class="action-block-title">Danger zone</div>
                <p class="help">
                  Permanently delete this user. This action cannot be undone.
                </p>
                <button class="btn btn-danger" @click="openConfirm('deleteUser')">
                  Delete user
                </button>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- 4: All Users -->
      <section
        v-show="activeTab === 4"
        class="card"
        role="tabpanel"
        :id="'admin-panel-all-users'"
        :aria-labelledby="'admin-tab-all-users'"
      >
        <div class="card-header">
          <div>
            <h3 class="card-title">All users</h3>
            <p class="card-subtitle">Search and manage the user directory.</p>
          </div>
          <div class="card-actions">
            <button class="btn btn-primary" @click="setTabByKey('add-user')">
              Create user
            </button>
          </div>
        </div>

        <div class="card-body">
          <div class="table-tools">
            <div class="tool">
              <label class="tool-label">Search</label>
              <input v-model="userSearch" class="input" placeholder="Search by username…" />
            </div>
            <div class="tool">
              <label class="tool-label">Role</label>
              <select v-model="roleFilter" class="select">
                <option value="">All</option>
                <option value="admin">Admin</option>
                <option value="user">User</option>
              </select>
            </div>
            <div class="tool">
              <label class="tool-label">Status</label>
              <select v-model="statusFilter" class="select">
                <option value="">All</option>
                <option value="active">Active</option>
                <option value="locked">Locked</option>
                <option value="disabled">Disabled</option>
              </select>
            </div>
          </div>

          <div v-if="filteredUsers.length === 0" class="empty-state">
            <div class="empty-title">No users match your filters</div>
            <div class="empty-text">Try clearing search or changing filters.</div>
          </div>

          <div v-else class="table-wrap">
            <table class="table" aria-label="All users table">
              <thead>
                <tr>
                  <th>Username</th>
                  <th>Role</th>
                  <th>Created</th>
                  <th>Updated</th>
                  <th>Status</th>
                  <th class="col-actions">Actions</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="u in filteredUsers" :key="u.id">
                  <td class="strong">{{ u.username }}</td>
                  <td>
                    <span class="badge" :class="u.role === 'admin' ? 'badge-warning' : 'badge-info'">
                      {{ u.role }}
                    </span>
                  </td>
                  <td>{{ formatDate(u.created_at) }}</td>
                  <td>{{ formatDate(u.updated_at) }}</td>
                  <td>
                    <span class="badge"
                      :class="u.is_locked ? 'badge-error' : (u.is_active ? 'badge-success' : 'badge-warning')"
                    >
                      {{ u.is_locked ? 'Locked' : (u.is_active ? 'Active' : 'Disabled') }}
                    </span>
                  </td>
                  <td class="col-actions">
                    <button class="btn btn-secondary btn-sm" @click="editUser(u)">Manage</button>
                    <button class="btn btn-danger btn-sm" @click="openConfirm('deleteSpecific', u)">
                      Delete
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <!-- 5: Reset Requests -->
      <section
        v-show="activeTab === 5"
        class="card"
        role="tabpanel"
        :id="'admin-panel-reset-requests'"
        :aria-labelledby="'admin-tab-reset-requests'"
      >
        <div class="card-header">
          <div>
            <h3 class="card-title">Password reset requests</h3>
            <p class="card-subtitle">View pending and processed reset requests.</p>
          </div>
        </div>

        <div class="card-body">
          <div v-if="resetRequests.length === 0" class="empty-state">
            <div class="empty-title">No reset requests</div>
            <div class="empty-text">There are currently no pending or recent requests.</div>
          </div>

          <div v-else class="table-wrap">
            <table class="table" aria-label="Reset requests table">
              <thead>
                <tr>
                  <th>Username</th>
                  <th>Reason</th>
                  <th>Requested</th>
                  <th>Decided</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="r in resetRequests" :key="r.id">
                  <td class="strong">{{ r.username }}</td>
                  <td>{{ r.reason || '—' }}</td>
                  <td>{{ formatDate(r.created_at) }}</td>
                  <td>{{ formatDate(r.decided_at) }}</td>
                  <td>
                    <span class="badge"
                      :class="r.status === 'approved' ? 'badge-success' : (r.status === 'rejected' ? 'badge-error' : 'badge-warning')"
                    >
                      {{ r.status || 'pending' }}
                    </span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <!-- 6: Audit Logs -->
      <section
        v-show="activeTab === 6"
        class="card"
        role="tabpanel"
        :id="'admin-panel-audit'"
        :aria-labelledby="'admin-tab-audit'"
      >
        <div class="card-header">
          <div>
            <h3 class="card-title">Audit logs</h3>
            <p class="card-subtitle">Authentication and security events.</p>
          </div>
        </div>

        <div class="card-body">
          <div v-if="auditLogs.length === 0" class="empty-state">
            <div class="empty-title">No audit events</div>
            <div class="empty-text">No events available for the current window.</div>
          </div>

          <div v-else class="table-wrap">
            <table class="table" aria-label="Audit logs table">
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
                  <td class="strong">{{ log.username || '—' }}</td>
                  <td>
                    <span class="badge" :class="getEventBadgeClass(log.action)">
                      {{ log.action || '—' }}
                    </span>
                  </td>
                  <td>{{ log.area || '—' }}</td>
                  <td class="truncate" :title="log.message || ''">{{ log.message || '—' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <!-- 7: Ops Logs -->
      <section
        v-show="activeTab === 7"
        class="card"
        role="tabpanel"
        :id="'admin-panel-ops'"
        :aria-labelledby="'admin-tab-ops'"
      >
        <div class="card-header">
          <div>
            <h3 class="card-title">Operations logs</h3>
            <p class="card-subtitle">System activity and conversions.</p>
          </div>
        </div>

        <div class="card-body">
          <div v-if="opsLogs.length === 0" class="empty-state">
            <div class="empty-title">No operations logs</div>
            <div class="empty-text">No system operations available right now.</div>
          </div>

          <div v-else class="table-wrap">
            <table class="table" aria-label="Operations logs table">
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
                  <td class="strong">{{ log.username || '—' }}</td>
                  <td><span class="badge badge-info">{{ log.area || '—' }}</span></td>
                  <td class="strong">{{ log.action || '—' }}</td>
                  <td class="truncate" :title="log.message || ''">{{ log.message || '—' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <!-- 8: Conversion Exclusions -->
      <section
        v-show="activeTab === 8"
        class="card"
        role="tabpanel"
        :id="'admin-panel-conv-exclusions'"
        :aria-labelledby="'admin-tab-conv-exclusions'"
      >
        <div class="card-header">
          <div>
            <h3 class="card-title">Conversion exclusions</h3>
            <p class="card-subtitle">
              Exclude groups globally from conversion and AI embedding.
              Excluded groups are skipped during conversion and cannot be embedded.
            </p>
          </div>
          <div class="card-actions">
            <button class="btn btn-secondary" @click="reloadAIConfig" :disabled="aiConfigLoading">
              <span v-if="aiConfigLoading" class="spinner" aria-hidden="true"></span>
              {{ aiConfigLoading ? 'Loading…' : 'Reload' }}
            </button>
            <button class="btn btn-primary" @click="saveEmbeddingConfig" :disabled="saving">
              <span v-if="saving" class="spinner" aria-hidden="true"></span>
              {{ saving ? 'Saving…' : 'Save exclusions' }}
            </button>
          </div>
        </div>

        <div class="card-body">
          <div class="summary-strip" role="status" aria-live="polite">
            <div class="summary-pill">
              Excluded groups: <strong>{{ excludedGroups.length }}</strong>
            </div>
            <div class="summary-pill summary-off">
              Conversion: <strong>Skipped</strong>
            </div>
            <div class="summary-pill summary-off">
              AI indexing: <strong>Blocked</strong>
            </div>
          </div>

          <div class="info-banner" role="note">
            <div class="info-title">How it works</div>
            <div class="info-text">
              Groups moved to <strong>Excluded</strong> are prevented from conversion output and AI embedding.
              You can also add custom group names and remove them later.
            </div>
          </div>

          <div class="dual-selector">
            <!-- Available -->
            <div class="selector">
              <div class="selector-head">
                <h4 class="selector-title">Available</h4>
                <p class="selector-subtitle">Groups eligible for conversion/indexing.</p>
              </div>

              <div class="selector-tools">
                <input
                  v-model="availableExclusionSearch"
                  class="input"
                  type="text"
                  placeholder="Search available…"
                  aria-label="Search available exclusion groups"
                />
              </div>

              <div class="selector-add">
                <input
                  v-model="newExcludedCandidate"
                  class="input"
                  type="text"
                  placeholder="Add new group (e.g., REPORTS)"
                  @keyup.enter="addExcludedCandidate"
                  aria-label="Add new group for exclusions"
                />
                <button class="btn btn-secondary btn-sm" @click="addExcludedCandidate" :disabled="!newExcludedCandidate">
                  Add
                </button>
              </div>

              <div class="selector-list" role="group" aria-label="Available groups for exclusion">
                <label v-for="g in filteredAvailableExclusionGroups" :key="g" class="check-row">
                  <input type="checkbox" :value="g" v-model="selectedExclusionLeft" />
                  <span class="check-label">{{ formatOracleGroupLabel(g) }}</span>
                </label>

                <div v-if="filteredAvailableExclusionGroups.length === 0" class="empty-small">
                  No groups found.
                </div>
              </div>
            </div>

            <!-- Controls -->
            <div class="selector-controls" aria-label="Move exclusion controls">
              <button
                class="btn btn-primary btn-sm"
                @click="moveToExcluded"
                :disabled="!selectedExclusionLeft.length"
                title="Exclude selected"
              >
                Exclude →
              </button>
              <button
                class="btn btn-secondary btn-sm"
                @click="moveToAvailable"
                :disabled="!selectedExclusionRight.length"
                title="Unexclude selected"
              >
                ← Remove
              </button>
              <p class="muted selector-hint">
                Excluded groups are skipped in conversion and embedding.
              </p>
            </div>

            <!-- Excluded -->
            <div class="selector">
              <div class="selector-head">
                <h4 class="selector-title">Excluded</h4>
                <p class="selector-subtitle">Blocked from conversion and AI indexing.</p>
              </div>

              <div class="selector-tools">
                <input
                  v-model="excludedSearch"
                  class="input"
                  type="text"
                  placeholder="Search excluded…"
                  aria-label="Search excluded groups"
                />
              </div>

              <div class="selector-list" role="group" aria-label="Excluded groups">
                <label v-for="g in filteredExcludedGroups" :key="g" class="check-row">
                  <input type="checkbox" :value="g" v-model="selectedExclusionRight" />
                  <span class="check-label">{{ formatOracleGroupLabel(g) }}</span>
                </label>

                <div v-if="filteredExcludedGroups.length === 0" class="empty-small">
                  No excluded groups.
                </div>
              </div>
            </div>
          </div>

          <div class="action-row">
            <button class="btn btn-secondary btn-sm" @click="clearExcluded" :disabled="excludedGroups.length === 0">
              Clear excluded
            </button>
            <span class="muted">
              Save to apply globally.
            </span>
          </div>

          <div
            v-if="configStatus"
            class="alert"
            :class="configStatus.type === 'success' ? 'alert-success' : 'alert-error'"
            role="status"
            aria-live="polite"
          >
            {{ configStatus.message }}
          </div>
        </div>
      </section>

      <!-- 9: Sessions -->
      <section
        v-show="activeTab === 9"
        class="card"
        role="tabpanel"
        :id="'admin-panel-sessions'"
        :aria-labelledby="'admin-tab-sessions'"
      >
        <div class="card-header">
          <div>
            <h3 class="card-title">Sessions</h3>
            <p class="card-subtitle">Monitor active sessions and remove old session data.</p>
          </div>
          <div class="card-actions">
            <button class="btn btn-danger" @click="openConfirm('cleanupSessions')" :disabled="sessions.length === 0">
              Cleanup old sessions
            </button>
          </div>
        </div>

        <div class="card-body">
          <div v-if="sessions.length === 0" class="empty-state">
            <div class="empty-title">No active sessions</div>
            <div class="empty-text">There are no sessions currently tracked.</div>
          </div>

          <div v-else class="table-wrap">
            <table class="table" aria-label="Sessions table">
              <thead>
                <tr>
                  <th>Session ID</th>
                  <th>Username</th>
                  <th>Created</th>
                  <th>Last activity</th>
                  <th>Size</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="s in sessions" :key="s.session_id">
                  <td><code class="code">{{ shortId(s.session_id) }}</code></td>
                  <td class="strong">{{ s.username || '—' }}</td>
                  <td>{{ formatDate(s.created_at) }}</td>
                  <td>{{ formatDate(s.last_activity) }}</td>
                  <td>{{ s.size || '—' }}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <p class="help" style="margin-top: 10px;">
            Cleanup removes old session artifacts to reduce storage usage. Active sessions are not affected.
          </p>
        </div>
      </section>
    </section>

    <!-- Confirm Modal -->
    <div v-if="confirmModal.open" class="modal-backdrop" role="presentation" @click.self="closeConfirm">
      <div class="modal" role="dialog" aria-modal="true" :aria-labelledby="'confirm-title'">
        <div class="modal-head">
          <h3 id="confirm-title" class="modal-title">{{ confirmModal.title }}</h3>
        </div>
        <div class="modal-body">
          <p class="modal-text">{{ confirmModal.message }}</p>
        </div>
        <div class="modal-actions">
          <button class="btn btn-secondary" @click="closeConfirm">Cancel</button>
          <button
            class="btn"
            :class="confirmModal.variant === 'danger' ? 'btn-danger' : 'btn-primary'"
            @click="confirmModal.onConfirm"
          >
            {{ confirmModal.confirmText }}
          </button>
        </div>
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
import api, { longApi } from '@/utils/api'
import { ORACLE_APP_CODES, formatOracleGroupLabel } from '@/utils/oracleApps'
import { normalizeGroupName } from '@/utils/groups'
import { format } from 'date-fns'

const auth = useAuthStore()
const toast = useToastStore()
const router = useRouter()

/** Tabs */
const tabs = [
  { key: 'ai-agent', label: 'AI Assistant', icon: '✨' },
  { key: 'ai-indexing', label: 'AI Indexing', icon: '🧠' },
  { key: 'add-user', label: 'Create user', icon: '➕' },
  { key: 'manage-user', label: 'Manage user', icon: '⚙️' },
  { key: 'all-users', label: 'All users', icon: '👥' },
  { key: 'reset-requests', label: 'Reset requests', icon: '🔑' },
  { key: 'audit', label: 'Audit logs', icon: '🧾' },
  { key: 'ops', label: 'Operations', icon: '📦' },
  { key: 'conv-exclusions', label: 'Conversion Exclusions', icon: '🚫' },
  { key: 'sessions', label: 'Sessions', icon: '💾' }
]

const activeTab = ref(0)
function setTab(idx) { activeTab.value = idx }
function setTabByKey(key) {
  const idx = tabs.findIndex(t => t.key === key)
  if (idx >= 0) activeTab.value = idx
}
function onTabKeydown(e, idx) {
  const keys = ['ArrowLeft', 'ArrowRight', 'Home', 'End']
  if (!keys.includes(e.key)) return
  e.preventDefault()
  if (e.key === 'Home') return setTab(0)
  if (e.key === 'End') return setTab(tabs.length - 1)
  const dir = e.key === 'ArrowRight' ? 1 : -1
  const next = (idx + dir + tabs.length) % tabs.length
  setTab(next)
}

/** Data */
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
const refreshing = ref(false)

/** Filter sessions for Conversion Exclusions: only ACTIVE or today's sessions */
const activeExclSessions = computed(() => {
  const todayStart = new Date()
  todayStart.setHours(0, 0, 0, 0)
  const todayEpoch = Math.floor(todayStart.getTime() / 1000)
  return sessions.value.filter(s => {
    if (String(s.status || '').toUpperCase() === 'ACTIVE') return true
    const created = Number(s.created_at || 0)
    return created >= todayEpoch
  })
})

/** User header initials */
const userInitials = computed(() => {
  const name = auth.user?.username || 'Admin'
  return name
    .split(' ')
    .filter(Boolean)
    .map(s => s[0])
    .slice(0, 2)
    .join('')
    .toUpperCase()
})

/** Filters (All Users tab) */
const userSearch = ref('')
const roleFilter = ref('')
const statusFilter = ref('')

const filteredUsers = computed(() => {
  const q = userSearch.value.trim().toLowerCase()
  return (users.value || [])
    .filter(u => (!q ? true : (u.username || '').toLowerCase().includes(q)))
    .filter(u => (!roleFilter.value ? true : u.role === roleFilter.value))
    .filter(u => {
      if (!statusFilter.value) return true
      if (statusFilter.value === 'locked') return !!u.is_locked
      if (statusFilter.value === 'active') return !u.is_locked && !!u.is_active
      if (statusFilter.value === 'disabled') return !u.is_locked && !u.is_active
      return true
    })
})

/** AI Indexing Config */
const availableGroupsList = ref([])
const autoEmbeddedGroups = ref([])
const autoEmbedEnabled = ref(true)
const selectedLeftGroups = ref([])
const selectedRightGroups = ref([])
const newGroup = ref('')
const excludedGroups = ref([])
const selectedExclusionLeft = ref([])
const selectedExclusionRight = ref([])
const availableExclusionSearch = ref('')
const excludedSearch = ref('')
const newExcludedCandidate = ref('')
const saving = ref(false)
const configStatus = ref(null)
const aiConfigLoading = ref(false)

const availableSearch = ref('')
const enabledSearch = ref('')

const filteredAvailableGroups = computed(() => {
  const q = availableSearch.value.trim().toUpperCase()
  const list = availableGroupsList.value || []
  return !q ? list : list.filter(x => x.includes(q))
})
const filteredEnabledGroups = computed(() => {
  const q = enabledSearch.value.trim().toUpperCase()
  const list = autoEmbeddedGroups.value || []
  return !q ? list : list.filter(x => x.includes(q))
})

function addGroup() {
  if (!newGroup.value) return
  const val = normalizeGroupName(newGroup.value)
  if (!val) return
  if (!availableGroupsList.value.includes(val) && !autoEmbeddedGroups.value.includes(val)) {
    availableGroupsList.value = [...availableGroupsList.value, val].sort()
  }
  newGroup.value = ''
}
function moveToRight() {
  if (!selectedLeftGroups.value.length) return
  autoEmbeddedGroups.value = [...new Set([...autoEmbeddedGroups.value, ...selectedLeftGroups.value])].sort()
  availableGroupsList.value = availableGroupsList.value.filter(g => !selectedLeftGroups.value.includes(g))
  selectedLeftGroups.value = []
}
function moveToLeft() {
  if (!selectedRightGroups.value.length) return
  availableGroupsList.value = [...new Set([...availableGroupsList.value, ...selectedRightGroups.value])].sort()
  autoEmbeddedGroups.value = autoEmbeddedGroups.value.filter(g => !selectedRightGroups.value.includes(g))
  selectedRightGroups.value = []
}

const availableExclusionGroups = computed(() => {
  const allKnown = new Set([
    ...ORACLE_APP_CODES,
    ...(availableGroupsList.value || []),
    ...(autoEmbeddedGroups.value || []),
    ...(excludedGroups.value || [])
  ])

  for (const g of excludedGroups.value || []) {
    allKnown.add(g)
  }

  return [...allKnown].filter(g => !excludedGroups.value.includes(g)).sort()
})

const filteredAvailableExclusionGroups = computed(() => {
  const q = availableExclusionSearch.value.trim().toUpperCase()
  const list = availableExclusionGroups.value || []
  return !q ? list : list.filter(x => x.includes(q))
})

const filteredExcludedGroups = computed(() => {
  const q = excludedSearch.value.trim().toUpperCase()
  const list = excludedGroups.value || []
  return !q ? list : list.filter(x => x.includes(q))
})

function addExcludedCandidate() {
  if (!newExcludedCandidate.value) return
  const val = normalizeGroupName(newExcludedCandidate.value)
  if (!val) return
  if (!excludedGroups.value.includes(val) && !availableExclusionGroups.value.includes(val)) {
    availableGroupsList.value = [...new Set([...availableGroupsList.value, val])].sort()
  }
  newExcludedCandidate.value = ''
}

function moveToExcluded() {
  if (!selectedExclusionLeft.value.length) return
  excludedGroups.value = [...new Set([...excludedGroups.value, ...selectedExclusionLeft.value])].sort()
  autoEmbeddedGroups.value = autoEmbeddedGroups.value.filter(g => !selectedExclusionLeft.value.includes(g))
  selectedExclusionLeft.value = []
}

function moveToAvailable() {
  if (!selectedExclusionRight.value.length) return
  excludedGroups.value = excludedGroups.value.filter(g => !selectedExclusionRight.value.includes(g))
  selectedExclusionRight.value = []
}

function clearExcluded() {
  excludedGroups.value = []
  selectedExclusionRight.value = []
}

/** Formatting */
function formatDate(d) {
  if (!d) return '—'
  try { return format(new Date(d), 'MMM dd, yyyy HH:mm') } catch { return String(d) }
}
function shortId(id) {
  if (!id) return '—'
  return id.length > 12 ? `${id.slice(0, 12)}…` : id
}
function getEventBadgeClass(action) {
  const lower = (action || '').toLowerCase()
  if (lower.includes('login') && lower.includes('success')) return 'badge-success'
  if (lower.includes('login') && (lower.includes('fail') || lower.includes('failed'))) return 'badge-error'
  if (lower.includes('logout')) return 'badge-info'
  if (lower.includes('delete') || lower.includes('lock') || lower.includes('error')) return 'badge-error'
  return 'badge-warning'
}

/** Clipboard */
async function copyToClipboard(text) {
  try {
    await navigator.clipboard.writeText(text)
    toast.success('Copied to clipboard')
  } catch {
    toast.error('Copy failed. Please copy manually.')
  }
}

/** Refresh */
async function refresh() {
  refreshing.value = true
  try {
    const [statsRes, usersRes, resetRes, auditRes, opsRes, sessionsRes] = await Promise.all([
      api.get('/admin/stats'),
      api.get('/admin/users'),
      api.get('/admin/reset-requests'),
      api.get('/admin/audit-logs'),
      api.get('/admin/ops-logs'),
      api.get('/admin/sessions')
    ])

    Object.assign(stats, statsRes.data || {})
    users.value = usersRes.data || []
    resetRequests.value = resetRes.data || []
    auditLogs.value = auditRes.data || []
    opsLogs.value = opsRes.data || []
    sessions.value = sessionsRes.data || []
  } catch (e) {
    console.error('Failed to refresh admin data:', e)
    toast.error('Failed to refresh admin data')
  } finally {
    refreshing.value = false
  }
}

/** User detail */
async function loadUserDetails() {
  resetToken.value = null
  selectedUser.value = null
  if (!selectedUserId.value) return
  try {
    const res = await api.get(`/admin/users/${selectedUserId.value}`)
    selectedUser.value = res.data
    updateRole.newRole = res.data.role
  } catch {
    toast.error('Failed to load user details')
  }
}

/** Create user */
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

/** Update role */
async function updateUserRole() {
  if (!selectedUserId.value) return
  try {
    await api.put(`/admin/users/${selectedUserId.value}/role`, { role: updateRole.newRole })
    toast.success('Role updated')
    await loadUserDetails()
    await refresh()
  } catch {
    toast.error('Failed to update role')
  }
}

/** Reset token */
async function generateResetToken() {
  if (!selectedUserId.value) return
  try {
    const res = await api.post(`/admin/users/${selectedUserId.value}/reset-token`)
    resetToken.value = res.data.token
    toast.success('Reset token generated')
  } catch {
    toast.error('Failed to generate token')
  }
}

/** Unlock */
async function unlockAccount() {
  if (!selectedUserId.value) return
  try {
    await api.post(`/admin/users/${selectedUserId.value}/unlock`)
    toast.success('Account unlocked')
    await loadUserDetails()
    await refresh()
  } catch {
    toast.error('Failed to unlock account')
  }
}

/** Delete */
async function deleteSelectedUser() {
  if (!selectedUserId.value) return
  try {
    await api.delete(`/admin/users/${selectedUserId.value}`)
    toast.success('User deleted')
    selectedUserId.value = ''
    selectedUser.value = null
    await refresh()
  } catch {
    toast.error('Failed to delete user')
  }
}
async function deleteUserById(id, username) {
  try {
    await api.delete(`/admin/users/${id}`)
    toast.success(`User ${username} deleted`)
    await refresh()
  } catch {
    toast.error('Failed to delete user')
  }
}
function editUser(u) {
  selectedUserId.value = u.id
  setTabByKey('manage-user')
  loadUserDetails()
}

/** Sessions cleanup */
async function cleanupSessions() {
  try {
    await api.post('/admin/sessions/cleanup')
    toast.success('Cleanup complete')
    await refresh()
  } catch {
    toast.error('Cleanup failed')
  }
}

/** AI config persistence */
async function reloadAIConfig() {
  aiConfigLoading.value = true
  try {
    const res = await api.get('/admin/ai-indexing-config')
    excludedGroups.value = (res.data.excluded_groups || []).map(normalizeGroupName)
    autoEmbeddedGroups.value = (res.data.auto_embedded_groups || [])
      .map(normalizeGroupName)
      .filter(g => !excludedGroups.value.includes(g))

    const autoEmbedRaw = res?.data?.auto_embed_enabled ?? res?.data?.enable_auto_embedding
    autoEmbedEnabled.value = autoEmbedRaw === undefined ? true : !!autoEmbedRaw

    const backendAvailable = (res?.data?.available_groups || []).map(normalizeGroupName).filter(Boolean)
    const enabledSet = new Set(autoEmbeddedGroups.value)
    const excludedSet = new Set(excludedGroups.value)

    const canonicalAvailable = ORACLE_APP_CODES.filter(code => !enabledSet.has(code) && !excludedSet.has(code))
    const customAvailable = backendAvailable
      .filter(code => !enabledSet.has(code) && !excludedSet.has(code) && !ORACLE_APP_CODES.includes(code))
      .sort()

    availableGroupsList.value = [...canonicalAvailable, ...customAvailable]
  } catch (e) {
    console.error('Failed to load AI config', e)
    toast.error('Failed to load AI configuration')
    availableGroupsList.value = [...ORACLE_APP_CODES]
    excludedGroups.value = []
    autoEmbedEnabled.value = true
  } finally {
    aiConfigLoading.value = false
  }
}
async function saveEmbeddingConfig() {
  saving.value = true
  configStatus.value = null
  try {
    const cleanedExcluded = [...new Set((excludedGroups.value || []).map(normalizeGroupName).filter(Boolean))].sort()
    const cleanedAuto = [...new Set((autoEmbeddedGroups.value || []).map(normalizeGroupName).filter(Boolean))]
      .filter(g => !cleanedExcluded.includes(g))
      .sort()

    await api.post('/admin/ai-indexing-config', {
      auto_embed_enabled: autoEmbedEnabled.value,
      auto_embedded_groups: cleanedAuto,
      excluded_groups: cleanedExcluded
    })

    autoEmbeddedGroups.value = cleanedAuto
    excludedGroups.value = cleanedExcluded

    configStatus.value = { type: 'success', message: 'Configuration saved successfully.' }
    setTimeout(() => (configStatus.value = null), 3000)
    toast.success('Configuration saved')
  } catch (e) {
    configStatus.value = {
      type: 'error',
      message: 'Failed to save configuration: ' + (e.response?.data?.detail || e.message)
    }
  } finally {
    saving.value = false
  }
}

/** Confirm modal */
const confirmModal = reactive({
  open: false,
  title: '',
  message: '',
  confirmText: 'Confirm',
  variant: 'primary',
  onConfirm: () => {}
})

function openConfirm(type, payload = null) {
  if (type === 'deleteUser') {
    confirmModal.open = true
    confirmModal.title = 'Delete user'
    confirmModal.message =
      `This will permanently delete "${selectedUser.value?.username || 'this user'}". This action cannot be undone.`
    confirmModal.confirmText = 'Delete'
    confirmModal.variant = 'danger'
    confirmModal.onConfirm = async () => {
      closeConfirm()
      await deleteSelectedUser()
    }
    return
  }

  if (type === 'deleteSpecific' && payload) {
    confirmModal.open = true
    confirmModal.title = 'Delete user'
    confirmModal.message = `This will permanently delete "${payload.username}". This action cannot be undone.`
    confirmModal.confirmText = 'Delete'
    confirmModal.variant = 'danger'
    confirmModal.onConfirm = async () => {
      closeConfirm()
      await deleteUserById(payload.id, payload.username)
    }
    return
  }

  if (type === 'cleanupSessions') {
    confirmModal.open = true
    confirmModal.title = 'Cleanup old sessions'
    confirmModal.message = 'This removes old session artifacts to reduce storage usage. Continue?'
    confirmModal.confirmText = 'Cleanup'
    confirmModal.variant = 'danger'
    confirmModal.onConfirm = async () => {
      closeConfirm()
      await cleanupSessions()
    }
  }
}
function closeConfirm() {
  confirmModal.open = false
}

onMounted(async () => {
  await refresh()
  await reloadAIConfig()
})
</script>

<style scoped>
/* -------------------------------------------------------
   Enterprise Admin Console Styling
------------------------------------------------------- */

.admin-shell {
  padding: 16px 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

/* Header */
.admin-header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  padding: 14px 16px;
  border-radius: 14px;
  background: linear-gradient(145deg, var(--surface-base), var(--surface-elevated));
  border: 1px solid var(--border-light);
  box-shadow: var(--shadow-sm);
}

.header-left { max-width: 70ch; }
.page-title {
  margin: 0;
  font-size: 1.25rem;
  font-weight: 900;
  color: var(--text-heading, var(--text-primary));
}
.page-subtitle {
  margin: 6px 0 0 0;
  color: var(--text-secondary);
  font-size: 0.92rem;
  line-height: 1.35;
}

.header-right {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.user-pill {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-radius: 999px;
  border: 1px solid var(--border-light);
  background: var(--surface-elevated);
}

.avatar {
  width: 34px;
  height: 34px;
  border-radius: 12px;
  display: grid;
  place-items: center;
  font-weight: 900;
  background: var(--brand-subtle, rgba(99, 102, 241, 0.12));
  color: var(--text-primary);
  border: 1px solid var(--border-light);
}

.user-meta { display: flex; flex-direction: column; gap: 2px; }
.user-name { font-weight: 850; color: var(--text-primary); font-size: 0.9rem; }
.user-role { font-size: 0.8rem; color: var(--text-tertiary); }

.header-actions { display: flex; gap: 10px; flex-wrap: wrap; }

/* Metrics */
.metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(180px, 1fr));
  gap: 12px;
}
@media (max-width: 980px) { .metrics { grid-template-columns: 1fr 1fr; } }
@media (max-width: 560px) { .metrics { grid-template-columns: 1fr; } }

.metric-card {
  background: var(--surface-elevated);
  border: 1px solid var(--border-light);
  border-radius: 14px;
  padding: 14px;
  box-shadow: var(--shadow-sm);
}
.metric-soft { background: linear-gradient(145deg, var(--surface-base), var(--surface-elevated)); }
.metric-value { font-size: 1.4rem; font-weight: 950; color: var(--text-heading, var(--text-primary)); }
.metric-label { margin-top: 4px; font-size: 0.88rem; color: var(--text-secondary); }

/* Tabs */
.tabs {
  display: flex;
  gap: 8px;
  flex-wrap: nowrap;
  padding: 2px;
  overflow-x: auto;
  scrollbar-width: thin;
}
.tab {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid var(--border-light);
  background: var(--surface-base);
  color: var(--text-secondary);
  cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease;
}
.tab:hover { border-color: var(--brand-primary); background: var(--surface-hover); color: var(--text-primary); }
.tab.active {
  border-color: var(--brand-primary);
  background: linear-gradient(145deg, var(--surface-base), var(--surface-elevated));
  color: var(--text-primary);
  box-shadow: var(--shadow-sm);
}
.tab:focus-visible { outline: 2px solid var(--brand-primary); outline-offset: 2px; }
.tab-icon { opacity: 0.95; }
.tab-label { font-weight: 800; }

/* Panels */
.panel-stack { display: flex; flex-direction: column; gap: 14px; }
.card {
  background: var(--surface-elevated);
  border: 1px solid var(--border-light);
  border-radius: 14px;
  box-shadow: var(--shadow-sm);
}
.card-header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  padding: 14px 16px;
  border-bottom: 1px solid var(--border-light);
}
.card-title { margin: 0; font-size: 1.05rem; font-weight: 950; color: var(--text-heading, var(--text-primary)); }
.card-subtitle { margin: 6px 0 0 0; color: var(--text-secondary); font-size: 0.92rem; line-height: 1.35; }
.card-actions { display: flex; gap: 10px; flex-wrap: wrap; }
.card-body { padding: 14px 16px 16px 16px; }

/* Info banner */
.info-banner {
  border: 1px solid var(--border-light);
  background: linear-gradient(145deg, var(--surface-base), var(--surface-elevated));
  border-radius: 14px;
  padding: 12px 14px;
  margin-bottom: 12px;
}
.info-title { font-weight: 950; color: var(--text-primary); }
.info-text { margin-top: 6px; color: var(--text-secondary); font-size: 0.9rem; line-height: 1.35; }

/* Dual selector */
.dual-selector { display: grid; grid-template-columns: 1fr 160px 1fr; gap: 12px; align-items: start; }
@media (max-width: 980px) { .dual-selector { grid-template-columns: 1fr; } }

.selector {
  border: 1px solid var(--border-light);
  border-radius: 14px;
  background: var(--surface-base);
  padding: 12px;
}
.selector-head { margin-bottom: 10px; }
.selector-title { margin: 0; font-size: 0.95rem; font-weight: 950; }
.selector-subtitle { margin: 4px 0 0 0; color: var(--text-tertiary); font-size: 0.85rem; }
.selector-tools, .selector-add { display: flex; gap: 8px; margin-bottom: 10px; }
.selector-list { display: flex; flex-direction: column; gap: 6px; max-height: 320px; overflow: auto; padding-right: 4px; }

.summary-strip {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}

.summary-pill {
  padding: 8px 10px;
  border-radius: 999px;
  border: 1px solid var(--border-light);
  background: var(--surface-base);
  font-size: 0.86rem;
  color: var(--text-secondary);
}

.summary-pill.summary-on {
  border-color: rgba(34, 197, 94, 0.35);
  background: rgba(34, 197, 94, 0.10);
  color: var(--success, #2e7d32);
}

.summary-pill.summary-off {
  border-color: rgba(234, 179, 8, 0.35);
  background: rgba(234, 179, 8, 0.10);
  color: #a16207;
}

.config-top-row {
  border: 1px solid var(--border-light);
  border-radius: 14px;
  background: var(--surface-base);
  padding: 10px 12px;
  margin-bottom: 12px;
}

.toggle-inline {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-weight: 900;
  color: var(--text-primary);
}

.toggle-inline input {
  width: 18px;
  height: 18px;
  accent-color: var(--brand-primary);
}

.selector-hint {
  margin: 2px 0 0 0;
  text-align: center;
}

.check-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-radius: 12px;
  border: 1px solid var(--border-light);
  background: var(--surface-elevated);
  cursor: pointer;
}
.check-row:hover { background: var(--surface-hover); }
.check-row input { width: 18px; height: 18px; accent-color: var(--brand-primary); }
.check-label { font-weight: 800; color: var(--text-primary); font-size: 0.9rem; }
.selector-controls { display: flex; flex-direction: column; gap: 10px; justify-content: center; }

/* Forms */
.form { margin: 0; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; }
@media (max-width: 980px) { .form-grid { grid-template-columns: 1fr; } }
.field { background: var(--surface-base); border: 1px solid var(--border-light); border-radius: 14px; padding: 12px; }
.field-full { grid-column: 1 / -1; }
.label { display: block; font-weight: 950; color: var(--text-primary); font-size: 0.9rem; margin-bottom: 8px; }
.help { margin: 8px 0 0 0; color: var(--text-tertiary); font-size: 0.85rem; line-height: 1.3; }
.input, .select, .textarea {
  width: 100%;
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid var(--border-medium);
  background: var(--surface-elevated);
  color: var(--text-primary);
}
.input:focus-visible, .select:focus-visible, .textarea:focus-visible { outline: 2px solid var(--brand-primary); outline-offset: 2px; }

/* Action rows */
.action-row { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-top: 12px; }
.muted { color: var(--text-tertiary); font-size: 0.88rem; }

/* Token cards */
.token-card { margin-top: 14px; border: 1px solid var(--border-light); border-radius: 14px; background: var(--surface-base); padding: 12px; }
.token-header { display: flex; justify-content: space-between; gap: 12px; align-items: center; }
.token-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.token-value { margin-top: 10px; padding: 12px; border-radius: 12px; border: 1px solid var(--border-light); background: var(--surface-elevated); overflow: auto; font-size: 0.85rem; }

/* Manage layout */
.manage-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 12px; }
@media (max-width: 980px) { .manage-grid { grid-template-columns: 1fr; } }
.subcard { border: 1px solid var(--border-light); border-radius: 14px; background: var(--surface-base); padding: 12px; }
.subcard-head { display: flex; justify-content: space-between; gap: 10px; align-items: flex-start; margin-bottom: 10px; }
.subcard-title { margin: 0; font-weight: 950; font-size: 0.98rem; }
.subcard-subtitle { margin: 4px 0 0 0; color: var(--text-tertiary); font-size: 0.85rem; }
.info-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.info-item { border: 1px solid var(--border-light); border-radius: 12px; padding: 10px; background: var(--surface-elevated); }
.info-k { font-size: 0.8rem; color: var(--text-tertiary); }
.info-v { margin-top: 4px; font-weight: 900; color: var(--text-primary); }

/* Action blocks */
.action-block { padding: 10px; border-radius: 12px; border: 1px solid var(--border-light); background: var(--surface-elevated); }
.action-block + .action-block { margin-top: 10px; }
.action-block-title { font-weight: 950; margin-bottom: 8px; }
.action-inline { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.action-block.warn { border-color: rgba(234, 179, 8, 0.35); }
.action-block.danger { border-color: rgba(239, 68, 68, 0.45); }

/* Alerts */
.alert { margin-top: 12px; padding: 10px 12px; border-radius: 12px; border: 1px solid var(--border-light); background: var(--surface-elevated); }
.alert-success { border-color: rgba(34, 197, 94, 0.35); background: rgba(34, 197, 94, 0.10); color: var(--success, #2e7d32); }
.alert-error { border-color: rgba(239, 68, 68, 0.35); background: rgba(239, 68, 68, 0.10); color: var(--error, #c62828); }

/* Tables */
.table-tools { display: grid; grid-template-columns: 2fr 1fr 1fr; gap: 12px; margin-bottom: 12px; }
@media (max-width: 980px) { .table-tools { grid-template-columns: 1fr; } }
.tool-label { display: block; font-weight: 900; font-size: 0.85rem; margin-bottom: 6px; color: var(--text-primary); }
.table-wrap { border: 1px solid var(--border-light); border-radius: 14px; overflow: auto; background: var(--surface-base); }
.table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
.table thead th { position: sticky; top: 0; background: var(--surface-elevated); text-align: left; padding: 12px; border-bottom: 1px solid var(--border-light); font-weight: 950; color: var(--text-primary); }
.table tbody td { padding: 10px 12px; border-bottom: 1px solid var(--border-light); color: var(--text-secondary); }
.table tbody tr:nth-child(even) { background: var(--surface-hover); }
.col-actions { width: 180px; white-space: nowrap; }
.strong { font-weight: 900; color: var(--text-primary); }
.truncate { max-width: 520px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.code { padding: 3px 6px; border-radius: 8px; border: 1px solid var(--border-light); background: var(--surface-elevated); }

/* Badges */
.badge {
  display: inline-flex;
  align-items: center;
  padding: 5px 10px;
  border-radius: 999px;
  border: 1px solid var(--border-light);
  font-size: 0.82rem;
  font-weight: 900;
  background: var(--surface-elevated);
}
.badge-success { color: var(--success, #2e7d32); border-color: rgba(34, 197, 94, 0.35); }
.badge-warning { color: #a16207; border-color: rgba(234, 179, 8, 0.35); }
.badge-error { color: var(--error, #c62828); border-color: rgba(239, 68, 68, 0.35); }
.badge-info { color: #1d4ed8; border-color: rgba(59, 130, 246, 0.35); }

/* Empty states */
.empty-state { border: 1px dashed var(--border-medium); border-radius: 14px; padding: 16px; background: var(--surface-base); text-align: center; }
.empty-title { font-weight: 950; color: var(--text-primary); }
.empty-text { margin-top: 6px; color: var(--text-tertiary); font-size: 0.9rem; }
.empty-small { padding: 10px; color: var(--text-tertiary); font-size: 0.88rem; }

/* Divider */
.divider { height: 1px; background: var(--border-light); margin: 12px 0; }

/* Buttons */
.btn {
  border-radius: 12px;
  border: 1px solid var(--border-medium);
  background: var(--surface-elevated);
  color: var(--text-primary);
  padding: 10px 12px;
  cursor: pointer;
  font-weight: 900;
  transition: background 0.15s ease, border-color 0.15s ease, filter 0.15s ease, box-shadow 0.15s ease;
}
.btn:hover:not(:disabled) { background: var(--surface-hover); }
.btn:disabled { opacity: 0.55; cursor: not-allowed; }
.btn-sm { padding: 8px 10px; font-size: 0.85rem; border-radius: 10px; }

.btn-primary { background: var(--brand-primary); border-color: var(--brand-primary); color: #0b0b0b; }
.btn-primary:hover:not(:disabled) { filter: brightness(1.05); box-shadow: var(--shadow-sm); }

.btn-secondary { background: var(--surface-elevated); border-color: var(--border-light); }
.btn-success { background: rgba(34, 197, 94, 0.16); border-color: rgba(34, 197, 94, 0.35); color: var(--success, #2e7d32); }
.btn-danger { background: rgba(239, 68, 68, 0.16); border-color: rgba(239, 68, 68, 0.45); color: var(--error, #c62828); }

/* Spinner */
.spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid transparent;
  border-top-color: currentColor;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin-right: 8px;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* Modal */
.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.42);
  display: grid;
  place-items: center;
  padding: 16px;
  z-index: 999;
}
.modal {
  width: min(560px, 100%);
  border-radius: 16px;
  background: var(--surface-elevated);
  border: 1px solid var(--border-light);
  box-shadow: var(--shadow-lg);
  overflow: hidden;
}
.modal-head { padding: 14px 16px; border-bottom: 1px solid var(--border-light); }
.modal-title { margin: 0; font-weight: 950; font-size: 1.05rem; }
.modal-body { padding: 14px 16px; }
.modal-text { margin: 0; color: var(--text-secondary); line-height: 1.4; }
.modal-actions { padding: 14px 16px; border-top: 1px solid var(--border-light); display: flex; justify-content: flex-end; gap: 10px; flex-wrap: wrap; }

/* -------------------------------------------------------
   ✅ Conversion Exclusions UI additions
------------------------------------------------------- */
.excl-summary {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 10px;
  margin-bottom: 12px;
}
.excl-pill {
  min-width: 160px;
  border-radius: 14px;
  border: 1px solid var(--border-light);
  background: var(--surface-base);
  padding: 10px 12px;
}
.excl-pill .k { font-size: 0.8rem; color: var(--text-tertiary); }
.excl-pill .v { margin-top: 2px; font-weight: 950; font-size: 1.05rem; color: var(--text-primary); }

.excl-controls {
  display: grid;
  grid-template-columns: 2fr 1fr 1fr;
  gap: 12px;
  margin-top: 12px;
}
@media (max-width: 980px) { .excl-controls { grid-template-columns: 1fr; } }

.excl-actions-row {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  align-items: center;
  margin-top: 12px;
  margin-bottom: 10px;
}

.excl-list-wrap {
  border: 1px solid var(--border-light);
  border-radius: 14px;
  overflow: hidden;
  background: var(--surface-base);
}
.excl-list-head {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border-light);
  background: var(--surface-elevated);
}
.excl-list { max-height: 420px; overflow: auto; }
.excl-row {
  display: grid;
  grid-template-columns: 24px 1fr;
  gap: 10px;
  align-items: start;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border-light);
  cursor: pointer;
}
.excl-row:hover { background: var(--surface-hover); }
.excl-row:last-child { border-bottom: none; }
.excl-check { margin-top: 3px; width: 18px; height: 18px; accent-color: var(--brand-primary); }
.excl-name { font-weight: 950; color: var(--text-primary); }
.excl-meta { margin-top: 4px; display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
</style>
