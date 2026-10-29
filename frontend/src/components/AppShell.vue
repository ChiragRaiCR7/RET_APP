<script setup lang="ts">
import { FolderArchive, GitCompareArrows, LogOut, ShieldCheck, UserRound } from "lucide-vue-next";
import { RouterLink, useRouter } from "vue-router";

import { session, signOut } from "@/state/session";

const router = useRouter();

async function leave() {
  await signOut();
  await router.replace({ name: "login" });
}
</script>

<template>
  <div class="shell">
    <a class="skip" href="#main">Skip to content</a>
    <header class="rail">
      <RouterLink to="/" class="brand" aria-label="RET home">
        <span class="mark" aria-hidden="true">R</span>
        <span class="word">RET</span>
      </RouterLink>
      <nav aria-label="Primary" class="nav">
        <RouterLink to="/" class="nav-link" :class="{ on: $route.path === '/' || $route.path.startsWith('/w/') }">
          <FolderArchive aria-hidden="true" /> <span>Workspaces</span>
        </RouterLink>
        <RouterLink to="/compare" class="nav-link" active-class="on">
          <GitCompareArrows aria-hidden="true" /> <span>Compare</span>
        </RouterLink>
        <RouterLink v-if="session.user?.role === 'admin'" to="/admin" class="nav-link" active-class="on">
          <ShieldCheck aria-hidden="true" /> <span>Admin</span>
        </RouterLink>
      </nav>
      <div class="me">
        <RouterLink to="/account" class="nav-link" active-class="on">
          <UserRound aria-hidden="true" />
          <span class="who"><span class="visually-hidden">Account settings for </span>{{ session.user?.username }}</span>
        </RouterLink>
        <button type="button" class="nav-link" @click="leave">
          <LogOut aria-hidden="true" /> <span>Sign out</span>
        </button>
      </div>
    </header>
    <main id="main" tabindex="-1">
      <slot />
    </main>
  </div>
</template>

<style scoped>
.shell {
  display: grid;
  grid-template-columns: 216px minmax(0, 1fr);
  min-height: 100dvh;
}
.skip {
  position: absolute; left: 8px; top: -40px; z-index: 10; padding: 8px 12px;
  background: var(--gold); color: var(--on-gold); border-radius: var(--radius); font-weight: 600;
  &:focus { top: 8px; }
}
.rail {
  position: sticky; top: 0; height: 100dvh;
  display: flex; flex-direction: column; gap: var(--space-5);
  padding: var(--space-4) var(--space-3);
  background: var(--sunken); border-right: 1px solid var(--line);
}
.brand {
  display: flex; align-items: center; gap: 10px; padding: 4px 8px; text-decoration: none;
}
.mark {
  display: grid; place-items: center; width: 28px; height: 28px; border-radius: 7px;
  background: var(--gold); color: var(--on-gold); font: 800 15px/1 var(--sans);
}
.word { font-weight: 750; letter-spacing: 0.06em; font-size: 15px; }
.nav, .me { display: grid; gap: 2px; }
.me { margin-top: auto; padding-top: var(--space-3); border-top: 1px solid var(--line); }
.nav-link {
  display: flex; align-items: center; gap: 10px; min-height: 34px; padding: 0 10px;
  border: 0; border-radius: var(--radius); background: none; color: var(--ink-2);
  font: 550 var(--text-md)/1 var(--sans); text-decoration: none; cursor: pointer; text-align: start;
  & svg { width: 17px; height: 17px; flex: none; }
  &:hover { background: color-mix(in srgb, var(--line) 60%, transparent); color: var(--ink); }
  &.on { background: var(--surface); color: var(--ink); box-shadow: var(--shadow); & svg { color: var(--gold-ink); } }
}
.who { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
main { min-width: 0; outline: none; }

@media (max-width: 860px) {
  .shell { grid-template-columns: 1fr; grid-template-rows: auto 1fr; }
  .rail {
    position: sticky; z-index: 5; height: auto; flex-direction: row; align-items: center;
    gap: var(--space-2); padding: 8px 12px; border-right: 0; border-bottom: 1px solid var(--line);
    overflow-x: auto;
  }
  .word { display: none; }
  .nav, .me { display: flex; gap: 2px; }
  .me { margin: 0 0 0 auto; padding: 0; border: 0; }
  /* Icon-only on small screens; labels stay in the accessibility tree (display:none would drop them). */
  .nav-link { padding: 0 8px; & > span { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; } }
  .nav-link.on { box-shadow: inset 0 -2px 0 var(--gold); }
}
</style>
