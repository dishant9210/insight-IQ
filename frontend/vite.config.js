import { defineConfig } from 'vite'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [
    tailwindcss(),
  ],
  // same-origin /api in dev too, like the gateway, so the refresh cookie works
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})