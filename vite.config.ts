import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { resolve } from 'path';

const apiProxy = {
  '/api': { target: process.env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8787', changeOrigin: true },
  '/media': { target: process.env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8787', changeOrigin: true },
};

export default defineConfig({
  plugins: [react()],
  base: './',
  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: false,
    allowedHosts: true,
    proxy: apiProxy,
  },
  preview: {
    host: '0.0.0.0',
    allowedHosts: true,
    proxy: apiProxy,
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    chunkSizeWarningLimit: 1200,
    rollupOptions: {
      // The marketing site is index.html at the repository root; the actual app lives in app.html.
      input: { index: resolve(__dirname, 'app.html') },
    },
  },
});
