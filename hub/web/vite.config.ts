import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

export default defineConfig(({ command }) => ({
  base: command === "build" ? "/ui/" : "/",   // ← dev at '/', prod at '/ui/'
  plugins: [svelte()],
  server: {
    host: '127.0.0.1',           // 👈 avoid ::1/IPv6 “happy eyeballs” delays
    port: 5173,
    strictPort: true,
    proxy: {
      // dev-only proxy to your hub (edit port if needed)
      '^/api': { target: 'http://127.0.0.1:8212', changeOrigin: true, ws: true },
      '^/ui':  { target: 'http://127.0.0.1:8212', changeOrigin: true },
      '^/ws':  { target: 'http://127.0.0.1:8212', changeOrigin: true, ws: true }
    }
  },
  build: {
    outDir: 'dist', emptyOutDir: true
  }
}));
