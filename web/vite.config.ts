/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev requests are proxied to the FastAPI server so the dashboard is
// same-origin with the API — no CORS configuration on either side.
const API_TARGET = 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/proposals': API_TARGET,
      '/webhooks': API_TARGET,
      '/healthz': API_TARGET,
      '/audit': API_TARGET,
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: './src/test-setup.ts',
  },
})
