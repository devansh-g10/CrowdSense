import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwind from '@tailwindcss/vite'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', 'CROWDROUTE_')
  const proxy = { '/api': env.CROWDROUTE_BACKEND_URL || 'http://127.0.0.1:8000' }
  return { plugins: [react(), tailwind()], server: { proxy }, preview: { proxy } }
})
