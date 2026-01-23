<template>
  <div id="app" class="ret-backdrop" :data-theme="theme">
    <div class="ret-container">
      <BrandHeader @toggle-theme="toggleTheme" />
      <router-view />
      <footer class="ret-footer">© 2025 TATA Consultancy Services — RET v4</footer>
    </div>
  </div>
</template>

<script setup>
import BrandHeader from '@/components/common/BrandHeader.vue'
import { useTheme } from '@/composable/useTheme'

const { theme, toggleTheme } = useTheme()
</script>
