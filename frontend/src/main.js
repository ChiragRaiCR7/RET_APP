
/**
 * main.js — Application entry point for RET v4 frontend
 *
 * Bootstraps:
 *   - Vue 3 app instance
 *   - Pinia state management (authStore, toastStore)
 *   - Vue Router (lazy-loaded MainView + AdminView, eager LoginView)
 *   - Global CSS: design tokens → base → components → ai-chat-enhanced
 *
 * The CSS import order matters — tokens.css defines variables consumed
 * by all subsequent stylesheets.
 */
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import router from './router'
import App from './App.vue'

/* Global styles — order matters: tokens → base → components → chat */
import './assets/styles/tokens.css'
import './assets/styles/base.css'
import './assets/styles/components.css'
import './assets/styles/ai-chat-enhanced.css'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount('#app')

