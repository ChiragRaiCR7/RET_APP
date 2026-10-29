<script setup lang="ts">
import { Copy, KeyRound, LockOpen, Trash2, UserPlus } from "lucide-vue-next";
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";

import { del, get, patch, post, query, type AdminStats, type AuditEvent, type ResetRequest, type ResetToken, type User } from "@/api/client";
import PageHeader from "@/components/PageHeader.vue";
import { ago, bytes, dateTime, int } from "@/lib/format";
import { confirm } from "@/state/confirm";
import { session } from "@/state/session";
import { fail, notify } from "@/state/toasts";

const route = useRoute();
const router = useRouter();
const section = computed(() => (["users", "requests", "audit"].includes(String(route.query.s)) ? String(route.query.s) : "users"));
const stats = ref<AdminStats | null>(null);
const users = ref<User[]>([]);
const requests = ref<ResetRequest[]>([]);
const audit = ref<AuditEvent[]>([]);
const auditFilter = ref("");
const draft = ref({ username: "", password: "", role: "user" as "user" | "admin" });
const issued = ref<{ user: string; token: ResetToken } | null>(null);
const codeDlg = ref<HTMLDialogElement | null>(null);

async function refresh() {
  try {
    [stats.value, users.value, requests.value] = await Promise.all([
      get<AdminStats>("/admin/stats"), get<User[]>("/admin/users"), get<ResetRequest[]>("/admin/reset-requests"),
    ]);
    await loadAudit();
  } catch (e) {
    fail(e);
  }
}
async function loadAudit() {
  audit.value = await get<AuditEvent[]>(`/admin/audit${query({ limit: 300, action: auditFilter.value.trim() })}`);
}
onMounted(refresh);

async function createUser() {
  try {
    await post("/admin/users", draft.value);
    notify(`Created ${draft.value.username}.`);
    draft.value = { username: "", password: "", role: "user" };
    await refresh();
  } catch (e) {
    fail(e, "Could not create user");
  }
}

async function update(u: User, body: Partial<Pick<User, "role" | "is_active">>) {
  try {
    await patch(`/admin/users/${u.id}`, body);
    await refresh();
  } catch (e) {
    fail(e);
  }
}

async function unlock(u: User) {
  try {
    await post(`/admin/users/${u.id}/unlock`);
    notify(`Unlocked ${u.username}.`);
    await refresh();
  } catch (e) {
    fail(e);
  }
}

async function issue(u: User) {
  try {
    issued.value = { user: u.username, token: await post<ResetToken>(`/admin/users/${u.id}/reset-token`) };
    codeDlg.value?.showModal();
  } catch (e) {
    fail(e);
  }
}

async function remove(u: User) {
  if (!(await confirm({ title: `Delete ${u.username}?`, body: "Their account, workspaces, datasets and conversations are permanently deleted.", action: "Delete user", danger: true }))) return;
  try {
    await del(`/admin/users/${u.id}`);
    notify(`Deleted ${u.username}.`);
    await refresh();
  } catch (e) {
    fail(e);
  }
}

async function copy(text: string) {
  await navigator.clipboard.writeText(text);
  notify("Code copied.");
}

const locked = (u: User) => !!u.locked_until && new Date(u.locked_until) > new Date();
const userFor = (name: string) => users.value.find((u) => u.username === name);
</script>

<template>
  <div class="page">
    <PageHeader title="Administration">
      <template #lede>
        <span v-if="stats" class="num">
          {{ int(stats.users) }} users · {{ int(stats.active_sessions) }} signed in · {{ int(stats.workspaces) }} workspaces ·
          {{ int(stats.datasets) }} datasets · {{ bytes(stats.disk_bytes) }} on disk ·
          AI model {{ stats.llm_configured ? "configured" : "not configured (retrieval only)" }}
        </span>
      </template>
    </PageHeader>

    <nav class="tabs" aria-label="Administration sections">
      <button v-for="[k, l] in [['users', 'Users'], ['requests', 'Reset requests'], ['audit', 'Audit log']]" :key="k" type="button"
              class="tab" :aria-current="section === k ? 'page' : undefined" @click="router.replace({ query: { s: k } })">
        {{ l }}<span v-if="k === 'requests' && requests.length" class="count num">{{ requests.length }}</span>
      </button>
    </nav>

    <template v-if="section === 'users'">
      <form class="create panel" @submit.prevent="createUser">
        <h2>Add a user</h2>
        <div class="row">
          <div class="field"><label for="nu">Username</label>
            <input id="nu" v-model="draft.username" class="input" required minlength="3" maxlength="64" pattern="[A-Za-z0-9_.\-]+" autocomplete="off" spellcheck="false" />
            <p class="field-error">3–64 letters, digits, dots, dashes or underscores.</p></div>
          <div class="field"><label for="np">Initial password</label>
            <input id="np" v-model="draft.password" class="input" type="password" required minlength="10" autocomplete="new-password" />
            <p class="field-error">At least 10 characters, not containing the username.</p></div>
          <div class="field"><label for="nr">Role</label>
            <select id="nr" v-model="draft.role" class="input"><option value="user">User</option><option value="admin">Administrator</option></select></div>
          <button class="btn btn-primary"><UserPlus aria-hidden="true" /> Add user</button>
        </div>
      </form>

      <div class="table-region" tabindex="0" role="region" aria-label="Users">
        <table class="table">
          <thead><tr><th scope="col">User</th><th scope="col">Role</th><th scope="col">Status</th><th scope="col">Last sign-in</th><th scope="col"><span class="visually-hidden">Actions</span></th></tr></thead>
          <tbody>
            <tr v-for="u in users" :key="u.id">
              <th scope="row">{{ u.username }} <span v-if="u.id === session.user?.id" class="subtle small">(you)</span></th>
              <td>
                <select class="input sm" :value="u.role" :disabled="u.id === session.user?.id" :aria-label="`Role for ${u.username}`"
                        @change="update(u, { role: ($event.target as HTMLSelectElement).value as User['role'] })">
                  <option value="user">User</option><option value="admin">Administrator</option>
                </select>
              </td>
              <td>
                <span v-if="locked(u)" class="badge warn">Locked</span>
                <span v-else-if="!u.is_active" class="badge">Disabled</span>
                <span v-else class="badge ok">Active</span>
              </td>
              <td>{{ u.last_login_at ? ago(u.last_login_at) : "Never" }}</td>
              <td class="acts">
                <template v-if="u.id !== session.user?.id">
                  <button v-if="locked(u)" class="btn btn-sm" @click="unlock(u)"><LockOpen aria-hidden="true" /> Unlock</button>
                  <button class="btn btn-sm" @click="issue(u)"><KeyRound aria-hidden="true" /> Reset code</button>
                  <button class="btn btn-sm" @click="update(u, { is_active: !u.is_active })">{{ u.is_active ? "Disable" : "Enable" }}</button>
                  <button class="btn btn-sm btn-quiet btn-icon" :aria-label="`Delete ${u.username}`" @click="remove(u)"><Trash2 aria-hidden="true" /></button>
                </template>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>

    <template v-else-if="section === 'requests'">
      <p v-if="!requests.length" class="muted">No pending requests.</p>
      <div v-else class="table-region" tabindex="0" role="region" aria-label="Password reset requests">
        <table class="table">
          <thead><tr><th scope="col">Username</th><th scope="col">Note</th><th scope="col">Requested</th><th scope="col"><span class="visually-hidden">Action</span></th></tr></thead>
          <tbody>
            <tr v-for="r in requests" :key="r.id">
              <th scope="row">{{ r.username }}</th>
              <td class="wrap">{{ r.reason || "—" }}</td>
              <td>{{ ago(r.created_at) }}</td>
              <td class="acts">
                <button v-if="userFor(r.username)" class="btn btn-sm" @click="issue(userFor(r.username)!)"><KeyRound aria-hidden="true" /> Issue code</button>
                <span v-else class="subtle small">No such user</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>

    <template v-else>
      <form class="audit-tools" @submit.prevent="loadAudit">
        <label for="af" class="visually-hidden">Filter by action</label>
        <input id="af" v-model="auditFilter" class="input" placeholder="Filter by action, e.g. login or workspace." />
        <button class="btn">Filter</button>
      </form>
      <div class="table-region" tabindex="0" role="region" aria-label="Audit log">
        <table class="table">
          <thead><tr><th scope="col">When</th><th scope="col">Who</th><th scope="col">Action</th><th scope="col">Target</th><th scope="col">Details</th></tr></thead>
          <tbody>
            <tr v-for="a in audit" :key="a.id">
              <td><time :datetime="a.created_at">{{ dateTime(a.created_at) }}</time></td>
              <td>{{ a.actor ?? "—" }}</td>
              <td><code :class="{ bad: a.action.includes('failed') || a.action.includes('locked') }">{{ a.action }}</code></td>
              <td class="mono small">{{ a.target ?? "" }}</td>
              <td class="mono small wrap">{{ a.details ? JSON.stringify(a.details) : "" }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>

    <dialog ref="codeDlg" class="dialog" aria-labelledby="code-title" @close="issued = null">
      <form v-if="issued" method="dialog" class="code">
        <h2 id="code-title">Reset code for {{ issued.user }}</h2>
        <p class="muted">Give this code to {{ issued.user }} privately. It works once and expires {{ dateTime(issued.token.expires_at) }}. It will not be shown again.</p>
        <div class="token"><code>{{ issued.token.token }}</code>
          <button type="button" class="btn btn-sm" @click="copy(issued.token.token)"><Copy aria-hidden="true" /> Copy</button></div>
        <div class="end"><button class="btn btn-primary" autofocus>Done</button></div>
      </form>
    </dialog>
  </div>
</template>

<style scoped>
.page { display: grid; gap: var(--space-4); padding: var(--space-5) var(--space-6) var(--space-7); max-width: 1180px; align-content: start; }
.tabs { display: flex; gap: 4px; border-bottom: 1px solid var(--line); }
.tab { position: relative; display: inline-flex; gap: 8px; align-items: center; padding: 10px 14px 12px; border: 0; background: none;
  color: var(--ink-2); font: 600 var(--text-md)/1 var(--sans); cursor: pointer;
  &:hover { color: var(--ink); }
  &[aria-current="page"] { color: var(--ink); }
  &[aria-current="page"]::after { content: ""; position: absolute; inset: auto 8px -1px; height: 2px; border-radius: 2px; background: var(--gold); } }
.count { padding: 1px 7px; border-radius: 999px; background: var(--gold-wash); color: var(--gold-ink); font-size: var(--text-xs); }
.create { display: grid; gap: var(--space-3); padding: var(--space-4); & h2 { font-size: var(--text-lg); } }
.row { display: grid; grid-template-columns: 1fr 1fr 180px auto; gap: var(--space-3); align-items: start;
  & .btn { margin-top: 25px; } }
.input.sm { min-height: 28px; padding: 2px 6px; width: auto; }
.acts { display: flex; gap: 6px; justify-content: flex-end; }
.wrap { white-space: normal; max-width: 50ch; overflow-wrap: anywhere; }
.audit-tools { display: flex; gap: 8px; max-width: 520px; }
code.bad { color: var(--bad); }
.code { display: grid; gap: var(--space-3); padding: var(--space-5); & h2 { font-size: var(--text-lg); } }
.token { display: flex; gap: 8px; align-items: center; padding: 10px 12px; border-radius: var(--radius); background: var(--sunken);
  & code { flex: 1; overflow-wrap: anywhere; font-size: var(--text-md); } }
.end { display: flex; justify-content: flex-end; }
@media (max-width: 900px) { .page { padding: var(--space-4); } .row { grid-template-columns: 1fr; & .btn { margin-top: 0; } } }
</style>
