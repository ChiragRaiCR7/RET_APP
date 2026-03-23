
<template>
  <section class="reset-shell" aria-label="Password reset">
    <!-- Tabs -->
    <div class="tab-list reset-tabs" role="tablist" aria-label="Password reset options">
      <button
        class="tab-button"
        :class="{ active: mode === 'request' }"
        type="button"
        role="tab"
        :id="tabIds.request"
        :aria-selected="mode === 'request'"
        :aria-controls="panelIds.request"
        :tabindex="mode === 'request' ? 0 : -1"
        :disabled="loading"
        @click="setMode('request')"
        @keydown="onTabKeydown($event, 'request')"
      >
        Request reset
      </button>

      <button
        class="tab-button"
        :class="{ active: mode === 'confirm' }"
        type="button"
        role="tab"
        :id="tabIds.confirm"
        :aria-selected="mode === 'confirm'"
        :aria-controls="panelIds.confirm"
        :tabindex="mode === 'confirm' ? 0 : -1"
        :disabled="loading"
        @click="setMode('confirm')"
        @keydown="onTabKeydown($event, 'confirm')"
      >
        Use reset token
      </button>
    </div>

    <!-- Status banners -->
    <div v-if="message" class="alert alert-info reset-alert" role="status" aria-live="polite">
      <div class="alert-content">
        <div class="alert-title">Update</div>
        <div>{{ message }}</div>
      </div>
    </div>

    <div v-if="error" class="alert alert-error reset-alert" role="alert" aria-live="assertive">
      <div class="alert-content">
        <div class="alert-title">Attention required</div>
        <div :id="errorId">{{ error }}</div>
      </div>
    </div>

    <!-- Request panel -->
    <form
      v-if="mode === 'request'"
      :id="panelIds.request"
      class="reset-panel animate-in"
      role="tabpanel"
      :aria-labelledby="tabIds.request"
      aria-label="Request password reset"
      @submit.prevent="requestReset"
      novalidate
    >
      <div class="form-group">
        <label class="form-label" for="reset-username">Username</label>
        <input
          ref="usernameRef"
          id="reset-username"
          class="form-input"
          v-model.trim="username"
          autocomplete="username"
          placeholder="john.doe"
          :disabled="loading"
          :aria-invalid="!!error"
          :aria-describedby="error ? errorId : requestHintId"
          @input="clearBanners"
        />
        <p class="form-hint" :id="requestHintId">
          We’ll create a reset request. An administrator will provide a one-time reset token.
        </p>
      </div>

      <div class="reset-actions">
        <button class="btn btn-primary" :disabled="!canRequest" type="submit">
          <span v-if="loading" class="spinner" aria-hidden="true"></span>
          {{ loading ? 'Requesting…' : 'Request reset' }}
        </button>

        <button class="btn btn-secondary" @click="emitDone" type="button" :disabled="loading">
          Back
        </button>
      </div>

      <div class="reset-footer">
        <span class="muted">
          Tip: If you already have a token, switch to “Use reset token”.
        </span>
        <button
          class="link-button"
          type="button"
          @click="setMode('confirm')"
          :disabled="loading"
        >
          I already have a token
        </button>
      </div>
    </form>

    <!-- Confirm panel -->
    <form
      v-else
      :id="panelIds.confirm"
      class="reset-panel animate-in"
      role="tabpanel"
      :aria-labelledby="tabIds.confirm"
      aria-label="Confirm password reset"
      @submit.prevent="confirmReset"
      novalidate
    >
      <div class="form-group">
        <label class="form-label" for="reset-token">Reset token</label>
        <input
          ref="tokenRef"
          id="reset-token"
          class="form-input token-input"
          v-model.trim="token"
          placeholder="Paste reset token"
          autocomplete="one-time-code"
          spellcheck="false"
          :disabled="loading"
          :aria-invalid="tokenTouched && !tokenValid"
          :aria-describedby="tokenHelpId"
          @input="onTokenInput"
          @blur="tokenTouched = true"
        />
        <p class="form-hint" :id="tokenHelpId">
          Tokens are one-time and expire. Paste the full token exactly as provided.
        </p>
      </div>

      <div class="form-group">
        <label class="form-label" for="new-password">New password</label>

        <div class="password-field">
          <input
            id="new-password"
            class="form-input password-input"
            :type="showPassword ? 'text' : 'password'"
            v-model="newPassword"
            autocomplete="new-password"
            :disabled="loading"
            :aria-invalid="pwTouched && !passwordStrong"
            :aria-describedby="pwHelpId"
            @input="onPasswordInput"
            @keydown="onPasswordKeydown"
            @blur="pwTouched = true"
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

        <div class="password-help" :id="pwHelpId">
          <span class="hint">
            Must be strong (min 8 chars, includes uppercase and a number).
          </span>

          <span v-if="capsLockOn" class="caps-warning" role="status" aria-live="polite">
            Caps Lock is on
          </span>
        </div>

        <div class="strength-wrap">
          <PasswordStrengthMeter :value="newPassword" />
        </div>
      </div>

      <div class="form-group">
        <label class="form-label" for="confirm-password">Confirm new password</label>
        <input
          id="confirm-password"
          class="form-input"
          :type="showPassword ? 'text' : 'password'"
          v-model="confirmPassword"
          autocomplete="new-password"
          :disabled="loading"
          :aria-invalid="confirmTouched && !passwordsMatch"
          :aria-describedby="confirmHelpId"
          @input="onConfirmInput"
          @blur="confirmTouched = true"
        />
        <div class="password-help" :id="confirmHelpId">
          <span class="hint" v-if="confirmPassword.length === 0">Re-enter the new password to confirm.</span>
          <span class="match-ok" v-else-if="passwordsMatch">Passwords match</span>
          <span class="match-bad" v-else>Passwords do not match</span>
        </div>
      </div>

      <div class="reset-actions">
        <button class="btn btn-primary" :disabled="!canConfirm" type="submit">
          <span v-if="loading" class="spinner" aria-hidden="true"></span>
          {{ loading ? 'Updating…' : 'Update password' }}
        </button>

        <button class="btn btn-secondary" @click="emitDone" type="button" :disabled="loading">
          Back
        </button>
      </div>

      <div class="reset-footer">
        <span class="muted">
          Keep your token private. If you suspect compromise, request a new token.
        </span>
      </div>
    </form>
  </section>
</template>

<script setup>
import { ref, computed, nextTick, onMounted } from 'vue'
import api from '@/utils/api'
import PasswordStrengthMeter from '@/components/auth/PasswordStrengthMeter.vue'

function isStrongPassword(s) {
  if (!s) return false
  return s.length >= 8 && /[A-Z]/.test(s) && /[0-9]/.test(s)
}

const emit = defineEmits(['done'])

const props = defineProps({
  initialMode: { type: String, default: 'request' }, // 'request' | 'confirm'
  requestEndpoint: { type: String, default: '/auth/password-reset/request' },
  confirmEndpoint: { type: String, default: '/auth/password-reset/confirm' },
  autoSwitchToConfirmAfterRequest: { type: Boolean, default: true }
})

const mode = ref(props.initialMode === 'confirm' ? 'confirm' : 'request')

const username = ref('')
const token = ref('')
const newPassword = ref('')
const confirmPassword = ref('')

const showPassword = ref(false)
const capsLockOn = ref(false)

const loading = ref(false)
const message = ref('')
const error = ref('')

/** Touch states for UX validation */
const tokenTouched = ref(false)
const pwTouched = ref(false)
const confirmTouched = ref(false)

/** Refs for focus management */
const usernameRef = ref(null)
const tokenRef = ref(null)

/** A11y IDs */
const errorId = 'reset-error'
const requestHintId = 'reset-request-hint'
const tokenHelpId = 'reset-token-help'
const pwHelpId = 'reset-pw-help'
const confirmHelpId = 'reset-confirm-help'

const tabIds = {
  request: 'reset-tab-request',
  confirm: 'reset-tab-confirm'
}
const panelIds = {
  request: 'reset-panel-request',
  confirm: 'reset-panel-confirm'
}

/** Derived validation */
const tokenValid = computed(() => !!token.value.trim())
const passwordStrong = computed(() => isStrongPassword(newPassword.value))
const passwordsMatch = computed(() => newPassword.value.length > 0 && newPassword.value === confirmPassword.value)

const canRequest = computed(() => !loading.value && !!username.value.trim())
const canConfirm = computed(() => {
  if (loading.value) return false
  if (!tokenValid.value) return false
  if (!passwordStrong.value) return false
  if (!passwordsMatch.value) return false
  return true
})

function clearBanners() {
  if (error.value) error.value = ''
  if (message.value) message.value = ''
}

function setMode(next) {
  if (loading.value) return
  clearBanners()
  mode.value = next

  // Focus the primary field in the panel
  nextTick(() => {
    if (next === 'request') usernameRef.value?.focus?.()
    else tokenRef.value?.focus?.()
  })
}

function onTabKeydown(e, current) {
  const keys = ['ArrowLeft', 'ArrowRight', 'Home', 'End']
  if (!keys.includes(e.key)) return

  e.preventDefault()
  if (loading.value) return

  if (e.key === 'Home') return setMode('request')
  if (e.key === 'End') return setMode('confirm')

  const next = current === 'request' ? 'confirm' : 'request'
  setMode(next)
}

function emitDone() {
  if (loading.value) return
  emit('done')
}

function togglePassword() {
  showPassword.value = !showPassword.value
}

function onPasswordKeydown(e) {
  // best-effort Caps Lock detection
  if (typeof e.getModifierState === 'function') {
    capsLockOn.value = e.getModifierState('CapsLock')
  }
}

function onTokenInput() {
  clearBanners()
}

function onPasswordInput() {
  clearBanners()
}

function onConfirmInput() {
  clearBanners()
}

async function requestReset() {
  if (!canRequest.value) return

  loading.value = true
  error.value = ''
  message.value = ''

  try {
    await api.post(props.requestEndpoint, { username: username.value.trim() })

    message.value = 'Request submitted. Contact an administrator for your one-time reset token.'

    if (props.autoSwitchToConfirmAfterRequest) {
      // Switch to confirm panel and focus token input
      setTimeout(() => setMode('confirm'), 250)
    }
  } catch (e) {
    error.value = e?.response?.data?.message || e?.response?.data?.detail || 'Failed to request reset.'
  } finally {
    loading.value = false
  }
}

async function confirmReset() {
  // Show validation messages only once the user tried
  tokenTouched.value = true
  pwTouched.value = true
  confirmTouched.value = true

  if (!canConfirm.value) {
    if (!tokenValid.value) error.value = 'Reset token is required.'
    else if (!passwordStrong.value) error.value = 'Password must be at least 8 characters and include an uppercase letter and a number.'
    else if (!passwordsMatch.value) error.value = 'Passwords do not match.'
    return
  }

  loading.value = true
  error.value = ''
  message.value = ''

  try {
    await api.post(props.confirmEndpoint, {
      token: token.value.trim(),
      new_password: newPassword.value
    })

    message.value = 'Password updated successfully. You can now sign in.'
    // Clear sensitive inputs
    token.value = ''
    newPassword.value = ''
    confirmPassword.value = ''
    tokenTouched.value = false
    pwTouched.value = false
    confirmTouched.value = false
    capsLockOn.value = false
  } catch (e) {
    error.value =
      e?.response?.data?.detail ||
      e?.response?.data?.message ||
      'Failed to reset password.'
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  // Focus first field for the initial mode
  nextTick(() => {
    if (mode.value === 'request') usernameRef.value?.focus?.()
    else tokenRef.value?.focus?.()
  })
})
</script>

<style scoped>
/* =========================================================
   ResetPasswordForm — Enterprise refinements
   Uses your tokens + component classes
   ========================================================= */

.reset-shell {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.reset-tabs {
  margin-bottom: var(--space-lg);
}

.reset-panel {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

/* Alerts inside this component spacing */
.reset-alert {
  margin-bottom: 0; /* controlled by shell gap */
}

/* Actions row */
.reset-actions {
  display: flex;
  gap: var(--space-sm);
  flex-wrap: wrap;
  align-items: center;
}

/* Make primary action stand out */
.reset-actions .btn-primary {
  min-width: 180px;
}

/* Footer row under forms */
.reset-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-md);
  flex-wrap: wrap;
  padding-top: var(--space-xs);
}

.muted {
  color: var(--text-tertiary);
  font-size: var(--text-xs);
}

/* Link styled button (semantically a button) */
.link-button {
  border: none;
  background: none;
  padding: 0;
  cursor: pointer;
  color: var(--link, var(--brand-primary));
  font-weight: 850;
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

/* Password field */
.password-field {
  position: relative;
  display: flex;
  align-items: center;
}

.password-input {
  padding-right: 96px; /* space for toggle */
}

.pwd-toggle {
  position: absolute;
  right: 10px;
  top: 6px;
  height: calc(100% - 12px);

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

.pwd-toggle-text { letter-spacing: 0.01em; }

/* Help rows */
.password-help {
  margin-top: var(--space-xs);
  display: flex;
  justify-content: space-between;
  gap: var(--space-sm);
  flex-wrap: wrap;
}

.hint {
  color: var(--text-tertiary);
  font-size: var(--text-xs);
}

/* Caps lock badge */
.caps-warning {
  color: var(--warning);
  font-weight: 850;
  font-size: var(--text-xs);
  background: var(--warning-bg);
  border: 1px solid var(--warning-border);
  padding: 4px 10px;
  border-radius: var(--radius-full);
}

/* Match indicator */
.match-ok {
  color: var(--success);
  font-weight: 850;
  font-size: var(--text-xs);
  background: var(--success-bg);
  border: 1px solid var(--success-border);
  padding: 4px 10px;
  border-radius: var(--radius-full);
}

.match-bad {
  color: var(--error);
  font-weight: 850;
  font-size: var(--text-xs);
  background: var(--error-bg);
  border: 1px solid var(--error-border);
  padding: 4px 10px;
  border-radius: var(--radius-full);
}

/* Strength meter spacing */
.strength-wrap {
  margin-top: var(--space-xs);
}

/* Token input gets a slightly “secure / code” feel */
.token-input {
  font-family: var(--font-mono);
  letter-spacing: 0.01em;
}

/* Small screens */
@media (max-width: 560px) {
  .reset-actions .btn-primary,
  .reset-actions .btn-secondary {
    width: 100%;
    justify-content: center;
  }
}
</style>
