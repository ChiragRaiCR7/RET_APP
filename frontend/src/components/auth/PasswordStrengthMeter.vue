<template>
  <div>
    <div class="password-strength-meter" aria-hidden="true">
      <div class="password-strength-fill" :style="{ width: pct + '%' }"></div>
    </div>
    <div class="password-strength-label" :class="labelClass">{{ label }}</div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
const props = defineProps({ value: { type: String, default: '' } })

function calcScore(s) {
  let score = 0
  if (!s) return 0
  if (s.length >= 8) score += 30
  if (/[A-Z]/.test(s)) score += 20
  if (/[0-9]/.test(s)) score += 20
  if (/[^A-Za-z0-9]/.test(s)) score += 30
  return Math.min(100, score)
}

const pct = computed(() => calcScore(props.value))
const label = computed(() => {
  const p = pct.value
  if (p < 30) return 'Weak'
  if (p < 60) return 'Fair'
  if (p < 85) return 'Good'
  return 'Strong'
})
const labelClass = computed(() => {
  const p = pct.value
  if (p < 30) return 'pw-weak'
  if (p < 60) return 'pw-fair'
  if (p < 85) return 'pw-good'
  return 'pw-strong'
})
</script>
