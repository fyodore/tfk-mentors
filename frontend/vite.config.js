import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import shopify from 'vite-plugin-shopify'

const enableShopifyPlugin = process.env.VITE_SHOPIFY_PLUGIN === 'true'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    ...(enableShopifyPlugin
      ? shopify({
          themeRoot: './',
          sourceCodeDir: 'src',
          entrypointsDir: 'src/entrypoints',
          additionalEntrypoints: ['src/main.tsx'],
        })
      : []),
  ],
  build: {
    chunkSizeWarningLimit: 900,
  },
  server: {
    host: true,
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.VITE_API_PROXY || 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
