import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      'satellite.js': fileURLToPath(
        new URL('./src/lib/satellite-browser.js', import.meta.url),
      ),
    },
  },
})
