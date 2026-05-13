import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => ({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
    watch: {
      usePolling: false,
      ignored: ['**/backend/**', '**/__pycache__/**', '**/*.pyc', '**/node_modules/**', '**/db/**'],
    },
    headers: {
      'Cache-Control': 'no-store',
    },
    // Dev-only proxy — in production, VITE_API_URL points directly to Render
    ...(mode === 'development' && {
      proxy: {
        // Proxy all /auth/* routes — safe now that Google OAuth (with its
        // client-side /auth/callback route) has been removed.
        '/auth': 'http://localhost:8000',
        '/attendance': 'http://localhost:8000',
        '/hierarchy': 'http://localhost:8000',
        '/admin': 'http://localhost:8000',
      }
    }),
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
}))
