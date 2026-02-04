import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

export default defineConfig(({ command }) => ({
  base: command === "build" ? "/v1ui/" : "/",   // ← dev at '/', prod at '/v1ui/'
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
    outDir: 'dist', 
    assetsDir: 'assets',
    emptyOutDir: true,
    cssCodeSplit: false,              // one CSS file
    sourcemap: false,
    rollupOptions: {
      output: {
        // fixed names -> no content hashes
        entryFileNames: 'assets/app.js',
        chunkFileNames: 'assets/[name].js',      // if you do dynamic imports
        assetFileNames: (asset) => {
          // collapse CSS to a fixed name; keep other assets stable
          if (asset.name?.endsWith('.css')) return 'assets/app.css';
          return 'assets/[name][extname]';
        },
      },
    },
  }
}));


