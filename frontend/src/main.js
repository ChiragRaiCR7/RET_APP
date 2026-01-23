import { createApp } from 'vue'
import { createPinia } from 'pinia'
import router from './router'
import App from './App.vue'
import './assets/styles/tokens.css'
import './assets/styles/base.css'
import './assets/styles/components.css'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount('#app')
