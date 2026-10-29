<script setup lang="ts">
import { CircleAlert, CircleCheck, LoaderCircle } from "lucide-vue-next";
import { ref } from "vue";
import { useRoute, useRouter } from "vue-router";

import { ApiError, post } from "@/api/client";
import { signIn } from "@/state/session";

type Mode = "signin" | "request" | "reset";
const route = useRoute();
const router = useRouter();
const mode = ref<Mode>("signin");
const busy = ref(false);
const error = ref("");
const done = ref("");
const form = ref({ username: "", password: "", reason: "", token: "", newPassword: "" });
const expired = route.query.expired === "1";

function switchTo(m: Mode) {
  mode.value = m;
  error.value = "";
  done.value = "";
}

async function submit() {
  busy.value = true;
  error.value = "";
  done.value = "";
  try {
    if (mode.value === "signin") {
      await signIn(form.value.username.trim(), form.value.password);
      const next = typeof route.query.next === "string" && route.query.next.startsWith("/") ? route.query.next : "/";
      await router.replace(next);
    } else if (mode.value === "request") {
      const r = await post<{ message: string }>("/auth/reset-requests", {
        username: form.value.username.trim(),
        reason: form.value.reason.trim() || null,
      });
      done.value = r.message;
    } else {
      const r = await post<{ message: string }>("/auth/reset", {
        token: form.value.token.trim(),
        new_password: form.value.newPassword,
      });
      form.value.password = "";
      switchTo("signin");
      done.value = r.message;
    }
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : "Could not reach the server.";
  } finally {
    busy.value = false;
  }
}

const titles: Record<Mode, string> = {
  signin: "Sign in to RET",
  request: "Ask for a password reset",
  reset: "Set a new password",
};
</script>

<template>
  <div class="page">
    <main class="card" aria-labelledby="login-title">
      <div class="brand">
        <span class="mark" aria-hidden="true">R</span>
        <div>
          <p class="name">RET</p>
          <p class="tag">Oracle extract workbench</p>
        </div>
      </div>
      <h1 id="login-title">{{ titles[mode] }}</h1>

      <p v-if="expired && mode === 'signin' && !error && !done" class="callout warn" role="status">
        <CircleAlert aria-hidden="true" /> Your session ended. Sign in again to continue.
      </p>
      <p v-if="error" class="callout bad" role="alert"><CircleAlert aria-hidden="true" />{{ error }}</p>
      <p v-if="done" class="callout ok" role="status"><CircleCheck aria-hidden="true" />{{ done }}</p>

      <form class="form" @submit.prevent="submit">
        <template v-if="mode !== 'reset'">
          <div class="field">
            <label for="username">Username</label>
            <input id="username" v-model="form.username" class="input" autocomplete="username"
                   required autofocus spellcheck="false" autocapitalize="off" />
          </div>
        </template>
        <div v-if="mode === 'signin'" class="field">
          <label for="password">Password</label>
          <input id="password" v-model="form.password" class="input" type="password"
                 autocomplete="current-password" required />
        </div>
        <div v-if="mode === 'request'" class="field">
          <label for="reason">Note for the administrator <span class="subtle">(optional)</span></label>
          <textarea id="reason" v-model="form.reason" class="input" rows="2" maxlength="500" />
        </div>
        <template v-if="mode === 'reset'">
          <div class="field">
            <label for="token">Reset code</label>
            <input id="token" v-model="form.token" class="input mono" autocomplete="one-time-code"
                   required minlength="16" spellcheck="false" autofocus />
            <p class="hint">Your administrator gives you this code. It works once and expires.</p>
          </div>
          <div class="field">
            <label for="newpw">New password</label>
            <input id="newpw" v-model="form.newPassword" class="input" type="password"
                   autocomplete="new-password" required minlength="10" />
            <p class="field-error">Use at least 10 characters.</p>
          </div>
        </template>

        <button class="btn btn-primary submit" :aria-busy="busy" :disabled="busy">
          <LoaderCircle v-if="busy" class="spin" aria-hidden="true" />
          {{ mode === "signin" ? "Sign in" : mode === "request" ? "Send request" : "Update password" }}
        </button>
      </form>

      <div class="alt">
        <template v-if="mode === 'signin'">
          <button type="button" class="link" @click="switchTo('request')">Forgot your password?</button>
          <button type="button" class="link" @click="switchTo('reset')">I have a reset code</button>
        </template>
        <button v-else type="button" class="link" @click="switchTo('signin')">Back to sign in</button>
      </div>
    </main>
  </div>
</template>

<style scoped>
.page {
  min-height: 100dvh; display: grid; place-items: center; padding: var(--space-5) var(--space-4);
}
.card {
  width: min(400px, 100%); display: grid; gap: var(--space-4); padding: var(--space-6);
  background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
}
.brand { display: flex; align-items: center; gap: 12px; margin-bottom: var(--space-2); }
.mark {
  display: grid; place-items: center; width: 40px; height: 40px; border-radius: 9px;
  background: var(--gold); color: var(--on-gold); font: 800 21px/1 var(--sans);
}
.name { font-weight: 800; letter-spacing: 0.08em; }
.tag { font-size: var(--text-sm); color: var(--ink-3); }
h1 { font-size: var(--text-xl); }
.form { display: grid; gap: var(--space-4); }
.submit { min-height: 40px; width: 100%; }
.alt { display: flex; justify-content: space-between; flex-wrap: wrap; gap: var(--space-2); }
.link {
  padding: 0; border: 0; background: none; color: var(--ink-2); font: inherit; font-size: var(--text-sm);
  text-decoration: underline; text-underline-offset: 0.2em; text-decoration-color: var(--line-strong); cursor: pointer;
  &:hover { color: var(--ink); text-decoration-color: var(--gold); }
}
</style>
