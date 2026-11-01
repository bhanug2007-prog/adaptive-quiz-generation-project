import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In development /api is forwarded to the FastAPI backend, so cookies stay same-origin.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': { target: process.env.VITE_BACKEND_URL || 'http://127.0.0.1:8000', changeOrigin: true } },
  },
  // No manual chunks: three.js and recharts are only imported by lazy-loaded pages, so the bundler keeps
  // them out of the first download. (A manualChunks rule pulled shared runtime helpers into the charts
  // chunk and made every page load it.)
  build: { chunkSizeWarningLimit: 700 },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.js'],
    include: ['src/**/*.test.{js,jsx}'],
    css: false,
  },
})
