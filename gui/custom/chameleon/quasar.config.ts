import { defineConfig } from '#q-app/wrappers'

export default defineConfig((/* ctx */) => {
  return {
    boot: [],

    css: ['app.scss'],

    extras: ['roboto-font', 'material-icons'],

    build: {
      distDir: 'dist/spa',
      publicPath: '/chameleon/',

      target: {
        browser: ['es2022', 'firefox115', 'chrome115', 'safari14'],
        node: 'node20',
      },

      typescript: {
        strict: true,
        vueShim: true,
      },

      vueRouterMode: 'hash',

      vitePlugins: [
        [
          'vite-plugin-checker',
          {
            vueTsc: true,
            eslint: {
              lintCommand: 'eslint -c ./eslint.config.js "./src*/**/*.{ts,js,mjs,cjs,vue}"',
              useFlatConfig: true,
            },
          },
          { server: false },
        ],
      ],

      extendViteConf(viteConf) {
        viteConf.build = viteConf.build || {}
        viteConf.build.rollupOptions = viteConf.build.rollupOptions || {}
        viteConf.build.rollupOptions.output = {
          entryFileNames: `assets/[name].js`,
          chunkFileNames: `assets/[name].js`,
          assetFileNames: `assets/[name].[ext]`,
        }
      },
    },

    devServer: {
      proxy: {
        '/api': {
          target: 'http://localhost:8212',
          changeOrigin: true,
          secure: false,
          ws: true,
        },
      },
      open: true,
    },

    framework: {
      config: { dark: true },
      plugins: ['Dialog', 'Notify'],
    },

    animations: [],
  }
})