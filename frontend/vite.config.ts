import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The board runs on localhost:5173 and talks to the FastAPI backend on localhost:8000.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, strictPort: true },
})
