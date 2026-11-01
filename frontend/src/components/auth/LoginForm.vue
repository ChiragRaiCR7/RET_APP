
<template>
  <form
    class="login-form animate-in"
    @submit.prevent="submit"
    aria-labelledby="login-form-title"
    novalidate
  >
    <h3 id="login-form-title" class="sr-only">Sign in</h3>

    <!-- Username -->
    <div class="form-group">
      <label class="form-label" for="username">Username</label>
      <input
        ref="usernameRef"
        id="username"
        v-model.trim="form.username"
        class="form-input"
        type="text"
        required
        autocomplete="username"
        aria-required="true"
        :aria-invalid="!!error"
        :aria-describedby="error ? errorId : undefined"
        :disabled="loading"
        @input="clearError"
      />
    </div>

    <!-- Password -->
    <div class="form-group">
      <label class="form-label" for="password">Password</label>

      <div class="password-field">
        <input
          id="password"
          v-model="form.password"
          class="form-input password-input"
          :type="showPassword ? 'text' : 'password'"
          required
          autocomplete="current-password"
          aria-required="true"
          :aria-invalid="!!error"
          :aria-describedby="passwordHelpId"
          :disabled="loading"
          @keydown="onPasswordKeydown"
          @input="clearError"
        />

        <button
          type="button"
          class="pwd-toggle"
          @click="togglePassword"
          :aria-pressed="showPassword"
          :aria-label="showPassword ? 'Hide password' : 'Show password'"
          :title="showPassword ? 'Hide password' : 'Show password'"
          :disabled="loading"
        >
          <span class="pwd-toggle-text">{{ showPassword ? 'Hide' : 'Show' }}</span>
        </button>
      </div>

      <!-- Password help / caps lock -->
      <div class="password-help" :id="passwordHelpId">
        <span class="hint">
          Use your organization password.
        </span>

        <span v-if="capsLockOn" class="caps-warning" role="status" aria-live="polite">
          Caps Lock is on
        </span>
      </div>
    </div>

    <!-- Remember + reset -->
    <div class="login-row">
      <label class="remember">
        <input
          type="checkbox"
          v-model="form.remember"
          :disabled="loading"
        />
        <span>Remember me</span>
      </label>

      <button
        type="button"
        class="link-button"
        @click="emit('reset')"
        :disabled="loading"
      >
        Forgot password?
      </button>
    </div>

    <!-- Actions -->
    <div class="actions">
      <button class="btn btn-primary" :disabled="!canSubmit" type="submit">
        <span v-if="loading" class="spinner" aria-hidden="true"></span>
        <span>{{ loading ? 'Signing in…' : 'Sign in' }}</span>
      </button>

      <button
        v-if="enableDemo"
        class="btn btn-secondary"
        type="button"
        @click="demoLogin"
        :disabled="loading"
        title="Use demo credentials"
      >
        Demo
      </button>
    </div>

    <!-- Error -->
    <p
      v-if="error"
      class="form-error"
      :id="errorId"
      role="alert"
      aria-live="assertive"
    >
      {{ error }}
    </p>

    <!-- Small compliance note -->
    <p class="fineprint">
      By signing in, you agree to your organization’s acceptable use policies.
    </p>
  </form>
</template>

<script setup lang="ts">
import { reactive, ref, computed, onMounted } from 'vue'
import { useAuthStore } from '@/stores/authStore'

const auth = useAuthStore()

const emit = defineEmits(['success', 'reset'])

const props = defineProps({
  enableDemo: { type: Boolean, default: true },
  demoCredentials: {
    type: Object,
    default: () => ({ username: 'user1', password: 'user123' })
  }
})

const loading = ref(false)
const error = ref('')
const showPassword = ref(false)
const capsLockOn = ref(false)
const usernameRef = ref<HTMLInputElement | null>(null)

const form = reactive({
  username: '',
  password: '',
  remember: true
})

const errorId = 'login-error'
const passwordHelpId = 'password-help'

const canSubmit = computed(() => {
  if (loading.value) return false
  return !!form.username.trim() && !!form.password
})

function clearError() {
  if (error.value) error.value = ''
}

function togglePassword() {
  showPassword.value = !showPassword.value
}

function onPasswordKeydown(e: KeyboardEvent) {
  // Detect Caps Lock (best-effort)
  if (typeof e.getModifierState === 'function') {
    capsLockOn.value = e.getModifierState('CapsLock')
  }
}

async function submit() {
  if (!canSubmit.value) return

  loading.value = true
  error.value = ''
  capsLockOn.value = false

  try {
    await auth.login(form.username, form.password, form.remember)
    emit('success')
  } catch (e) {
    const data = (e as { response?: { data?: { detail?: string; message?: string } } }).response?.data
    error.value =
      data?.detail ||
      data?.message ||
      'Sign in failed. Please check your credentials and try again.'
    // Focus username for quick recovery if username empty; otherwise keep focus where user is.
    if (!form.username.trim()) usernameRef.value?.focus?.()
  } finally {
    loading.value = false
  }
}

function demoLogin() {
  form.username = props.demoCredentials.username
  form.password = props.demoCredentials.password
  submit()
}

onMounted(() => {
  // Improve UX: focus username on load
  usernameRef.value?.focus?.()
})
</script>

<style scoped>
/* =========================================================
   LoginForm — Enterprise refinements
   (Uses tokens + your component classes)
   ========================================================= */

.login-form {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  border: 0;
}

/* Password field layout */
.password-field {
  position: relative;
  display: flex;
  align-items: center;
}

.password-input {
  padding-right: 96px; /* room for toggle */
}

/* Toggle button — enterprise style (no emoji) */
.pwd-toggle {
  position: absolute;
  right: 10px;
  height: calc(100% - 12px);
  top: 6px;

  display: inline-flex;
  align-items: center;
  justify-content: center;

  padding: 0 12px;
  border-radius: var(--radius-md);

  background: transparent;
  border: 1px solid transparent;

  color: var(--text-secondary);
  font-weight: 850;
  font-size: 0.85rem;

  transition: background var(--transition-fast), border-color var(--transition-fast), color var(--transition-fast);
}

.pwd-toggle:hover:not(:disabled) {
  background: var(--surface-hover);
  border-color: var(--border-light);
  color: var(--text-body);
}

.pwd-toggle:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);
}

.pwd-toggle:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.pwd-toggle-text {
  letter-spacing: 0.01em;
}

/* Help row under password */
.password-help {
  margin-top: 8px;
  display: flex;
  justify-content: space-between;
  gap: var(--space-sm);
  flex-wrap: wrap;
}

.hint {
  color: var(--text-tertiary);
  font-size: var(--text-xs);
}

.caps-warning {
  color: var(--warning);
  font-weight: 850;
  font-size: var(--text-xs);
  background: var(--warning-bg);
  border: 1px solid var(--warning-border);
  padding: 4px 10px;
  border-radius: var(--radius-full);
}

/* Remember + forgot row */
.login-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-md);
  flex-wrap: wrap;
  margin-top: 2px;
}

.remember {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  color: var(--text-secondary);
  font-weight: 750;
}

.remember input {
  width: 18px;
  height: 18px;
  accent-color: var(--brand-primary);
}

/* Use button styled like a link for correct semantics */
.link-button {
  border: none;
  background: none;
  color: var(--link, var(--brand-primary));
  font-weight: 850;
  padding: 0;
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 0.18em;
}

.link-button:hover:not(:disabled) {
  color: var(--link-hover, var(--brand-secondary));
}

.link-button:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);
  border-radius: var(--radius-sm);
}

.link-button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* Actions */
.actions {
  display: flex;
  gap: var(--space-sm);
  align-items: center;
  flex-wrap: wrap;
  margin-top: 2px;
}

/* Make primary button feel “first-class” in a form */
.actions .btn-primary {
  min-width: 160px;
}

/* Spinner alignment inside button */
.spinner {
  width: 16px;
  height: 16px;
  margin-right: 8px;
  vertical-align: middle;
}

/* Fine print */
.fineprint {
  margin: 0;
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  line-height: 1.4;
}

/* Small screens */
@media (max-width: 560px) {
  .actions .btn-primary {
    width: 100%;
    justify-content: center;
  }
  .actions .btn-secondary {
    width: 100%;
  }
}
</style>
