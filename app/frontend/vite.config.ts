import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // Gọi backend qua proxy để cùng origin, không cần CORS.
  server: { proxy: { '/runs': 'http://localhost:8000' } },
})
