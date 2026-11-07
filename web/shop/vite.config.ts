import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'
import vuetify from 'vite-plugin-vuetify'
import VueRouter from 'vue-router/vite'

// Same Content-Security-Policy as staging/production (deploy/staging-lite/gateway.conf), so the browser
// tests catch violations before deployment.
const csp =
  "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
const proxy = { '/api/identity': { target: process.env.IDENTITY_URL ?? 'http://localhost:18001', changeOrigin: false } }

// File-based routing (APD §1): src/pages/<route>.vue. Dev: /api goes to the dev stack (identity on 18001).
export default defineConfig({
  plugins: [
    VueRouter({ routesFolder: 'src/pages', dts: 'src/typed-router.d.ts' }),
    vue(),
    vuetify({ autoImport: true }),
  ],
  server: { port: 15173, strictPort: true, proxy },
  preview: { port: 15173, strictPort: true, proxy, headers: { 'Content-Security-Policy': csp } },
  build: {
    target: 'es2022',
    sourcemap: true,
    chunkSizeWarningLimit: 900,
    // Never inline fonts as data: URIs (the CSP allows fonts from 'self' only).
    assetsInlineLimit: (file: string) => (/\.(woff2?|ttf|otf)$/.test(file) ? false : undefined),
  },
})
