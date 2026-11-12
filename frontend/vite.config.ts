import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Forward API calls to the FastAPI backend (run it on port 8000) so the browser sees one origin.
  server: {
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/verify": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
})
