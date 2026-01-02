import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 3000,
    host: '0.0.0.0',
    proxy: {
      '/api': {
        // In Docker: use service name; locally: use VITE_API_URL or fallback
        target: process.env.VITE_API_URL || 'http://api:8000',
        changeOrigin: true,
      },
    },
  },
})
