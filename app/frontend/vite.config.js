import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
  build: {
    outDir: 'dist',
    // 'static' not the default 'assets' — the app has an /assets page route,
    // and the backend mount at /assets would shadow it (see main.py).
    assetsDir: 'static',
    sourcemap: false,
  },
})
