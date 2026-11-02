import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: './',
  test: {
    environment: 'jsdom',
    globals: true,
  },
  resolve: {
    alias: {
      // Cria o alias apontando para a pasta src de forma absoluta
      '@': new URL('./src', import.meta.url).pathname,
    },
  },
  build: {
    rollupOptions: {
      output: {
        // Match exato por pacote: `includes('react')` também pegava react-markdown, lucide-react etc.
        manualChunks(id) {
          const path = id.replaceAll('\\', '/');
          if (/node_modules\/(react|react-dom|scheduler)\//.test(path)) return 'vendor-react';
          if (/node_modules\/(framer-motion|motion-dom|motion-utils)\//.test(path)) return 'vendor-framer';
        },
      },
    },
  },
})