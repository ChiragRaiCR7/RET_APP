<template>
  <main class="auth-shell" role="main" aria-labelledby="auth-title">
    <!-- Top bar / Brand -->
    <header class="auth-topbar" role="banner">
      <div class="brand">
        <div class="brand-mark" aria-hidden="true">RET</div>
        <div class="brand-text">
          <div class="brand-name">RET Platform</div>
          <div class="brand-meta">Secure workspace for document conversion</div>
        </div>
      </div>

      <div class="topbar-actions">
        <span class="pill" :class="themePillClass" role="status" aria-live="polite">
          <span class="dot" :class="themeDotClass" aria-hidden="true"></span>
          {{ themeLabel }}
        </span>
      </div>
    </header>

    <!-- Content grid -->
    <section class="auth-layout" aria-label="Authentication">
      <!-- Left: Hero -->
      <aside class="auth-hero" aria-label="Product overview">
        <h1 id="auth-title" class="hero-title">
          Convert ZIP content to structured outputs—fast and reliable.
        </h1>

        <p class="hero-subtitle">
          Built for teams that need consistent results, clear traceability, and predictable downloads.
        </p>

        <!-- Hero image (theme-aware) -->
        <figure class="hero-media" v-if="heroImage">
          <img
            :src="heroImage"
            class="hero-image"
            :alt="heroAlt"
            loading="eager"
            decoding="async"
          />
          <figcaption class="hero-caption">
            Upload. Convert. Review. Download—within one workspace.
          </figcaption>
        </figure>

        <!-- Value props -->
        <ul class="value-list">
          <li class="value-item">
            <span class="value-icon" aria-hidden="true">⚡</span>
            <div>
              <div class="value-title">Quick turnaround</div>
              <div class="value-desc">Convert and prepare downloads in fewer steps.</div>
            </div>
          </li>
          <li class="value-item">
            <span class="value-icon" aria-hidden="true">🧾</span>
            <div>
              <div class="value-title">Audit-friendly</div>
              <div class="value-desc">Clear actions and outputs for easier validation.</div>
            </div>
          </li>
          <li class="value-item">
            <span class="value-icon" aria-hidden="true">📦</span>
            <div>
              <div class="value-title">Bulk-ready</div>
              <div class="value-desc">Handle large ZIP archives with grouped downloads.</div>
            </div>
          </li>
          <li class="value-item">
            <span class="value-icon" aria-hidden="true">🔒</span>
            <div>
              <div class="value-title">Enterprise security cues</div>
              <div class="value-desc">Session-based workflow with automatic expiration.</div>
            </div>
          </li>
        </ul>

        <!-- Trust strip -->
        <div class="trust-strip" role="note">
          <div class="trust-badge">Secure session</div>
          <p class="trust-text">
            Don’t share credentials. If this isn’t your device, avoid using “Remember me” in the login form.
          </p>
        </div>
      </aside>

      <!-- Right: Auth card -->
      <section class="auth-panel" aria-label="Sign in panel">
        <div class="auth-card" aria-live="polite">
          <div class="auth-card-header">
            <h2 class="card-title">
              {{ showReset ? 'Reset your password' : 'Sign in' }}
            </h2>
            <p class="card-subtitle">
              {{ showReset
                ? 'Enter your email to receive reset instructions.'
                : 'Use your organization account to continue.' }}
            </p>
          </div>

          <!-- Tabs -->
          <div class="tabs" role="tablist" aria-label="Authentication options">
            <button
              class="tab"
              role="tab"
              :id="tabIds.login"
              :aria-selected="!showReset"
              :aria-controls="panelIds.login"
              :tabindex="!showReset ? 0 : -1"
              :class="{ active: !showReset }"
              @click="activate('login')"
              @keydown="onTabKeydown($event, 'login')"
              type="button"
            >
              Login
            </button>

            <button
              class="tab"
              role="tab"
              :id="tabIds.reset"
              :aria-selected="showReset"
              :aria-controls="panelIds.reset"
              :tabindex="showReset ? 0 : -1"
              :class="{ active: showReset }"
              @click="activate('reset')"
              @keydown="onTabKeydown($event, 'reset')"
              type="button"
            >
              Reset password
            </button>
          </div>

          <!-- Panels -->
          <div class="tab-panels">
            <transition name="fade-slide" mode="out-in">
              <div
                v-if="!showReset"
                :key="'login'"
                class="panel"
                role="tabpanel"
                :id="panelIds.login"
                :aria-labelledby="tabIds.login"
              >
                <LoginForm @success="onSuccess" @reset="activate('reset')" />
                <div class="panel-footer">
                  <button class="link" type="button" @click="activate('reset')">
                    Forgot password?
                  </button>
                  <span class="sep" aria-hidden="true">•</span>
                  <a class="link" href="#" @click.prevent="openSupport">
                    Need help?
                  </a>
                </div>
              </div>

              <div
                v-else
                :key="'reset'"
                class="panel"
                role="tabpanel"
                :id="panelIds.reset"
                :aria-labelledby="tabIds.reset"
              >
                <ResetPasswordForm @done="activate('login')" />
                <div class="panel-footer">
                  <button class="link" type="button" @click="activate('login')">
                    Back to login
                  </button>
                  <span class="sep" aria-hidden="true">•</span>
                  <a class="link" href="#" @click.prevent="openSupport">
                    Contact support
                  </a>
                </div>
              </div>
            </transition>
          </div>

          <!-- Divider -->
          <div class="divider" role="separator" aria-label="Additional information"></div>

          <!-- Small compliance / guidance -->
          <div class="fineprint">
            <p>
              By continuing, you agree to your organization’s acceptable use policies.
            </p>
            <p class="muted">
              If you suspect suspicious activity, reset your password and contact support immediately.
            </p>
          </div>
        </div>

        <footer class="auth-footer" aria-label="Footer">
          <span class="muted">© {{ year }} RET Platform</span>
          <span class="sep" aria-hidden="true">•</span>
          <a class="link" href="#" @click.prevent="openPrivacy">Privacy</a>
          <span class="sep" aria-hidden="true">•</span>
          <a class="link" href="#" @click.prevent="openTerms">Terms</a>
        </footer>
      </section>
    </section>
  </main>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/authStore'
import { useTheme } from '@/composable/useTheme'

import LoginForm from '@/components/auth/LoginForm.vue'
import ResetPasswordForm from '@/components/auth/ResetPasswordForm.vue'

import LightModeImage from '@/assets/Light_mode.png'
import DarkModeImage from '@/assets/Dark_mode.png'

const router = useRouter()
const auth = useAuthStore()
const { theme } = useTheme()

const showReset = ref(false)

const year = new Date().getFullYear()

// Theme-aware hero image
const heroImage = computed(() => (theme.value === 'dark' ? DarkModeImage : LightModeImage))
const heroAlt = computed(() =>
  theme.value === 'dark'
    ? 'RET workspace illustration in dark mode'
    : 'RET workspace illustration in light mode'
)

// Topbar theme label (enterprise-friendly)
const themeLabel = computed(() => (theme.value === 'dark' ? 'Dark theme' : 'Light theme'))
const themePillClass = computed(() => (theme.value === 'dark' ? 'pill-dark' : 'pill-light'))
const themeDotClass = computed(() => (theme.value === 'dark' ? 'dot-dark' : 'dot-light'))

const tabIds = {
  login: 'auth-tab-login',
  reset: 'auth-tab-reset'
}
const panelIds = {
  login: 'auth-panel-login',
  reset: 'auth-panel-reset'
}

function activate(which) {
  showReset.value = which === 'reset'
}

function onTabKeydown(e, current) {
  // Keyboard-friendly tab switch (Left/Right, Home/End)
  const keys = ['ArrowLeft', 'ArrowRight', 'Home', 'End']
  if (!keys.includes(e.key)) return

  e.preventDefault()

  if (e.key === 'Home' || e.key === 'End') {
    activate(e.key === 'Home' ? 'login' : 'reset')
    return
  }

  if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
    const next = current === 'login' ? 'reset' : 'login'
    activate(next)
  }
}

async function onSuccess() {
  // Fetch user details after successful login
  await auth.fetchMe()

  // Redirect based on role
  if (auth.user?.role === 'admin') {
    router.push({ name: 'admin' })
  } else {
    router.push({ name: 'main' })
  }
}

/* Placeholder handlers: wire to your routes/modals */
function openSupport() {
  // You can route to a support page or open a modal.
  // router.push({ name: 'support' })
  console.info('Support link clicked')
}

function openPrivacy() {
  console.info('Privacy link clicked')
}

function openTerms() {
  console.info('Terms link clicked')
}
</script>

<style scoped>
/* =========================================================
   Enterprise Auth Shell
   Uses existing CSS tokens (var(--...)) where available.
   ========================================================= */

.auth-shell {
  min-height: 100vh;
  padding: clamp(16px, 2vw, 28px);
  background:
    radial-gradient(900px 500px at 20% 10%, rgba(120, 140, 255, 0.10), transparent 60%),
    radial-gradient(900px 500px at 80% 30%, rgba(0, 200, 140, 0.08), transparent 55%),
    var(--app-background, var(--surface-base));
  color: var(--text-primary);
}

/* Topbar */
.auth-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 4px 2px 18px 2px;
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
}

.brand-mark {
  width: 40px;
  height: 40px;
  border-radius: 12px;
  display: grid;
  place-items: center;
  font-weight: 900;
  letter-spacing: 0.5px;
  background: linear-gradient(135deg, var(--brand-primary), var(--brand-secondary, var(--brand-primary)));
  color: #0b0b0b;
  box-shadow: var(--shadow-sm);
}

.brand-name {
  font-weight: 900;
  color: var(--text-heading, var(--text-primary));
  line-height: 1.1;
}

.brand-meta {
  font-size: 0.86rem;
  color: var(--text-tertiary);
  margin-top: 2px;
}

.topbar-actions {
  display: flex;
  gap: 10px;
  align-items: center;
}

/* Theme pill */
.pill {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 999px;
  border: 1px solid var(--border-light);
  font-size: 0.85rem;
  color: var(--text-secondary);
  background: var(--surface-elevated);
  white-space: nowrap;
}

.pill-light {
  background: rgba(255, 255, 255, 0.65);
}

.pill-dark {
  background: rgba(20, 20, 20, 0.55);
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
}
.dot-light { background: #4f46e5; }
.dot-dark { background: #22c55e; }

/* Layout grid */
.auth-layout {
  display: grid;
  grid-template-columns: minmax(420px, 1.2fr) minmax(360px, 440px);
  gap: clamp(16px, 2.5vw, 32px);
  align-items: start;
}

/* Responsive: stack on smaller screens */
@media (max-width: 980px) {
  .auth-layout {
    grid-template-columns: 1fr;
  }
}

/* Hero */
.auth-hero {
  padding: clamp(10px, 1.5vw, 18px);
  border-radius: 16px;
}

.hero-title {
  font-size: clamp(1.6rem, 2.2vw, 2.2rem);
  font-weight: 950;
  margin: 6px 0 10px 0;
  color: var(--text-heading, var(--text-primary));
  letter-spacing: -0.02em;
}

.hero-subtitle {
  margin: 0 0 14px 0;
  font-size: 1rem;
  color: var(--text-secondary);
  line-height: 1.5;
  max-width: 70ch;
}

.hero-media {
  margin: 16px 0;
}

.hero-image {
  width: 100%;
  border-radius: 16px;
  border: 1px solid var(--border-light);
  box-shadow: var(--shadow-lg);
  background: var(--surface-elevated);
}

.hero-caption {
  margin-top: 10px;
  font-size: 0.88rem;
  color: var(--text-tertiary);
}

/* Value list */
.value-list {
  list-style: none;
  padding: 0;
  margin: 16px 0 0 0;
  display: grid;
  gap: 10px;
}

.value-item {
  display: grid;
  grid-template-columns: 34px 1fr;
  gap: 12px;
  padding: 12px;
  border-radius: 14px;
  border: 1px solid var(--border-light);
  background: linear-gradient(145deg, var(--surface-base), var(--surface-elevated));
}

.value-icon {
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  border-radius: 12px;
  background: var(--brand-subtle, rgba(99, 102, 241, 0.12));
  border: 1px solid var(--border-light);
}

.value-title {
  font-weight: 900;
  color: var(--text-primary);
}

.value-desc {
  margin-top: 2px;
  color: var(--text-secondary);
  font-size: 0.9rem;
}

/* Trust strip */
.trust-strip {
  margin-top: 16px;
  padding: 12px;
  border-radius: 14px;
  border: 1px solid var(--border-light);
  background: var(--surface-base);
}

.trust-badge {
  display: inline-flex;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 0.8rem;
  font-weight: 900;
  border: 1px solid var(--border-light);
  background: var(--surface-elevated);
  color: var(--text-primary);
}

.trust-text {
  margin: 8px 0 0 0;
  color: var(--text-secondary);
  font-size: 0.9rem;
  line-height: 1.35;
}

/* Panel */
.auth-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.auth-card {
  background: var(--surface-elevated);
  border: 1px solid var(--border-light);
  border-radius: 16px;
  padding: 18px;
  box-shadow: var(--shadow-md);
}

.auth-card-header {
  margin-bottom: 14px;
}

.card-title {
  margin: 0;
  font-size: 1.2rem;
  font-weight: 950;
  color: var(--text-heading, var(--text-primary));
}

.card-subtitle {
  margin: 8px 0 0 0;
  color: var(--text-secondary);
  font-size: 0.92rem;
  line-height: 1.35;
}

/* Tabs */
.tabs {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin-top: 12px;
  margin-bottom: 10px;
}

.tab {
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid var(--border-light);
  background: var(--surface-base);
  color: var(--text-secondary);
  font-weight: 850;
  cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease;
}

.tab:hover {
  background: var(--surface-hover);
  border-color: var(--brand-primary);
  color: var(--text-primary);
}

.tab.active {
  background: linear-gradient(145deg, var(--surface-base), var(--surface-elevated));
  border-color: var(--brand-primary);
  color: var(--text-primary);
  box-shadow: var(--shadow-sm);
}

.tab:focus-visible {
  outline: 2px solid var(--brand-primary);
  outline-offset: 2px;
}

/* Panels */
.tab-panels {
  margin-top: 6px;
}

.panel {
  padding-top: 6px;
}

.panel-footer {
  margin-top: 12px;
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.divider {
  margin: 16px 0 12px;
  height: 1px;
  background: var(--border-light);
}

/* Links */
.link {
  border: none;
  background: none;
  padding: 0;
  margin: 0;
  cursor: pointer;
  color: var(--brand-primary);
  font-weight: 800;
  text-decoration: none;
}
.link:hover {
  text-decoration: underline;
}

.sep {
  color: var(--text-tertiary);
}

/* Fine print */
.fineprint p {
  margin: 0;
  font-size: 0.86rem;
  line-height: 1.35;
}
.fineprint .muted {
  margin-top: 6px;
  color: var(--text-tertiary);
}

/* Footer */
.auth-footer {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  padding: 4px 2px;
}

.muted {
  color: var(--text-tertiary);
  font-size: 0.88rem;
}

/* Motion */
@media (prefers-reduced-motion: no-preference) {
  .fade-slide-enter-active,
  .fade-slide-leave-active {
    transition: opacity 0.16s ease, transform 0.16s ease;
  }
  .fade-slide-enter-from {
    opacity: 0;
    transform: translateY(6px);
  }
  .fade-slide-leave-to {
    opacity: 0;
    transform: translateY(-6px);
  }
}
</style>
