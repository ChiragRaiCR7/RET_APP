/**
 * Vite configuration for RET v4 frontend
 *
 * Features:
 *   - Vue 3 SPA with @ alias to src/
 *   - Dev proxy to FastAPI backend on :8000
 *   - Handles cookies cleanly (refresh token is HttpOnly cookie)
 *   - Code-splitting: vendor libs extracted to separate chunk
 *   - Terser minification, no sourcemaps in production
 *
 * Non-breaking improvements:
 *   - Backend proxy target configurable via env (VITE_BACKEND_URL)
 *   - Proxy /health endpoints too (optional)
 *   - Safer defaults + optional debug hooks kept as comments
 */

import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig(({ mode }) => {
  // Load env variables (supports .env, .env.development, etc.)
  const env = loadEnv(mode, process.cwd(), '')

  // Default backend target remains the same as your current config
  const BACKEND_URL = env.VITE_BACKEND_URL || 'http://127.0.0.1:8000'

  return {
    plugins: [vue()],

    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url))
      }
    },

    // Optional compatibility: some libs still check process.env.NODE_ENV
    define: {
      'process.env.NODE_ENV': JSON.stringify(mode)
    },

    server: {
      port: 5173,
      host: 'localhost',
      strictPort: true,

      /**
       * ✅ Proxy all /api requests to FastAPI
       * This allows the frontend to call /api/v1/... without CORS issues.
       */
      proxy: {
        '/api': {
          target: BACKEND_URL,
          changeOrigin: true,
          secure: false,
          ws: true,

          /**
           * ✅ Keep path unchanged: /api/v1/... -> /api/v1/...
           */
          rewrite: (path) => path,

          /**
           * ✅ Helps when backend sets cookies with a domain or a restrictive path.
           * Useful for refresh-token HttpOnly cookies.
           */
          cookieDomainRewrite: {
            '*': 'localhost'
          },
          cookiePathRewrite: {
            '*': '/'
          },

          /**
           * ✅ Optional: helpful proxy hooks for debugging
           */
          configure: (proxy) => {
            proxy.on('proxyReq', (proxyReq) => {
              // Uncomment to debug requests:
              // console.log('[proxyReq]', proxyReq.method, proxyReq.path)
            })

            proxy.on('proxyRes', (proxyRes) => {
              // Uncomment to debug Set-Cookie:
              // const setCookie = proxyRes.headers['set-cookie']
              // if (setCookie) console.log('[proxyRes][set-cookie]', setCookie)
            })

            proxy.on('error', (err) => {
              console.error('[proxy error]', err)
            })
          }
        },

        /**
         * ✅ Optional: proxy health endpoints too (if UI calls /health directly)
         * Keeps behavior unchanged if you never call it.
         */
        '/health': {
          target: BACKEND_URL,
          changeOrigin: true,
          secure: false,
          rewrite: (path) => path
        }
      }
    },

    build: {
      target: 'esnext',
      minify: 'terser',
      sourcemap: false,

      rollupOptions: {
        output: {
          manualChunks: {
            'vendor-vue': ['vue', 'vue-router', 'pinia'],
            'vendor-ui': ['@headlessui/vue', 'axios'],
            'vendor-charts': ['chart.js', 'vue-chartjs'],
            'vendor-markdown': ['marked', 'mermaid']
          }
        }
      }
    }
  }
})