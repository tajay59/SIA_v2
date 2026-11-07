import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'
import vuetify from 'vite-plugin-vuetify'
import VueRouter from 'vue-router/vite'

const proxy = { '/api/identity': { target: process.env.IDENTITY_URL ?? 'http://localhost:18001', changeOrigin: false } }

// File-based routing (APD §1): src/pages/<route>.vue. Dev: /api goes to the dev stack (identity on 18001).
export default defineConfig({
  plugins: [
    VueRouter({ routesFolder: 'src/pages', dts: 'src/typed-router.d.ts' }),
    vue(),
    vuetify({ autoImport: true }),
  ],
  server: { port: 15174, strictPort: true, proxy },
  preview: { port: 15174, strictPort: true, proxy },
  build: { target: 'es2022', sourcemap: true, chunkSizeWarningLimit: 900 },
})
