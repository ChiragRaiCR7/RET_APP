<script setup lang="ts">
import { Monitor, Moon, Sun } from "lucide-vue-next";
import { onBeforeUnmount, onMounted, ref } from "vue";

import { post } from "@/api/client";
import PageHeader from "@/components/PageHeader.vue";
import { dateTime } from "@/lib/format";
import { session } from "@/state/session";
import { fail, notify } from "@/state/toasts";

const pw = ref({ current: "", next: "", confirm: "" });
const busy = ref(false);

async function change() {
  if (pw.value.next !== pw.value.confirm) return fail(new Error("The new passwords do not match."));
  busy.value = true;
  try {
    await post("/auth/password", { current_password: pw.value.current, new_password: pw.value.next });
    notify("Password changed. Other sessions were signed out.");
    pw.value = { current: "", next: "", confirm: "" };
  } catch (e) {
    fail(e);
  } finally {
    busy.value = false;
  }
}

// Appearance: three explicit states on a settings surface (System / Light / Dark).
type Scheme = "system" | "light" | "dark";
const meta = document.querySelector<HTMLMetaElement>('meta[name="color-scheme"]');
const dark = matchMedia("(prefers-color-scheme: dark)");
const scheme = ref<Scheme>(readScheme());
const systemIsDark = ref(dark.matches);

function readScheme(): Scheme {
  try {
    const v = localStorage.getItem("color-scheme");
    return v === "light" || v === "dark" ? v : "system";
  } catch {
    return "system";
  }
}
function apply(s: Scheme) {
  scheme.value = s;
  try {
    if (s === "system") localStorage.removeItem("color-scheme");
    else localStorage.setItem("color-scheme", s);
  } catch {
    /* storage blocked: the choice still applies to this tab */
  }
  if (meta) meta.content = s === "system" ? "light dark" : s;
}
const onSystem = (e: MediaQueryListEvent) => (systemIsDark.value = e.matches);
const onStorage = (e: StorageEvent) => e.key === "color-scheme" && apply(readScheme());
onMounted(() => {
  dark.addEventListener("change", onSystem);
  window.addEventListener("storage", onStorage);
});
onBeforeUnmount(() => {
  dark.removeEventListener("change", onSystem);
  window.removeEventListener("storage", onStorage);
});
</script>

<template>
  <div class="page">
    <PageHeader title="Account">
      <template #lede>
        Signed in as <strong>{{ session.user?.username }}</strong> ({{ session.user?.role === "admin" ? "administrator" : "user" }})
        <template v-if="session.user?.created_at"> · member since {{ dateTime(session.user.created_at) }}</template>
      </template>
    </PageHeader>

    <section class="panel block" aria-labelledby="appearance">
      <h2 id="appearance">Appearance</h2>
      <fieldset class="schemes">
        <legend class="visually-hidden">Color scheme</legend>
        <label class="scheme" :class="{ on: scheme === 'system' }"><input type="radio" name="scheme" :checked="scheme === 'system'" @change="apply('system')" />
          <Monitor aria-hidden="true" /> System <span class="subtle small">(currently {{ systemIsDark ? "dark" : "light" }})</span></label>
        <label class="scheme" :class="{ on: scheme === 'light' }"><input type="radio" name="scheme" :checked="scheme === 'light'" @change="apply('light')" />
          <Sun aria-hidden="true" /> Light</label>
        <label class="scheme" :class="{ on: scheme === 'dark' }"><input type="radio" name="scheme" :checked="scheme === 'dark'" @change="apply('dark')" />
          <Moon aria-hidden="true" /> Dark</label>
      </fieldset>
    </section>

    <section class="panel block" aria-labelledby="pw-title">
      <h2 id="pw-title">Change password</h2>
      <form class="form" @submit.prevent="change">
        <div class="field"><label for="cur">Current password</label>
          <input id="cur" v-model="pw.current" class="input" type="password" autocomplete="current-password" required /></div>
        <div class="field"><label for="new">New password</label>
          <input id="new" v-model="pw.next" class="input" type="password" autocomplete="new-password" required minlength="10" />
          <p class="hint">At least 10 characters and not containing your username.</p></div>
        <div class="field"><label for="cnf">Repeat new password</label>
          <input id="cnf" v-model="pw.confirm" class="input" type="password" autocomplete="new-password" required minlength="10" /></div>
        <div><button class="btn btn-primary" :disabled="busy" :aria-busy="busy">Change password</button></div>
      </form>
    </section>
  </div>
</template>

<style scoped>
.page { display: grid; gap: var(--space-4); padding: var(--space-5) var(--space-6) var(--space-7); max-width: 760px; align-content: start; }
.block { display: grid; gap: var(--space-3); padding: var(--space-5); & h2 { font-size: var(--text-lg); } }
.schemes { display: flex; flex-wrap: wrap; gap: 8px; margin: 0; padding: 0; border: 0; }
.scheme { display: inline-flex; align-items: center; gap: 8px; padding: 8px 14px; border: 1px solid var(--line-strong);
  border-radius: var(--radius); cursor: pointer; font-weight: 550;
  & input { position: absolute; opacity: 0; pointer-events: none; }
  & svg { width: 16px; height: 16px; }
  &.on { border-color: var(--gold-ink); background: var(--gold-wash); }
  &:has(input:focus-visible) { outline: 2px solid var(--focus); outline-offset: 2px; } }
.form { display: grid; gap: var(--space-3); max-width: 420px; }
@media (max-width: 860px) { .page { padding: var(--space-4); } }
</style>
