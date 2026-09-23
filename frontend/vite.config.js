import { readFileSync } from 'node:fs'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { BRAND } from './src/brand.js'

const pkg = JSON.parse(readFileSync(new URL('./package.json', import.meta.url), 'utf-8'))

function webManifest() {
  return JSON.stringify({
    name: BRAND.name,
    short_name: BRAND.name,
    description: BRAND.tagline,
    start_url: '/',
    scope: '/',
    display: 'standalone',
    background_color: BRAND.backgroundColor,
    theme_color: BRAND.themeColor,
    icons: [
      { src: '/pwa-192.png', sizes: '192x192', type: 'image/png', purpose: 'any maskable' },
      { src: '/pwa-512.png', sizes: '512x512', type: 'image/png', purpose: 'any maskable' },
    ],
  }, null, 2)
}

// index.html and the web manifest are derived from src/brand.js, so a rename
// never has to touch them by hand.
function brandPlugin() {
  const placeholders = {
    '%BRAND_NAME%': BRAND.name,
    '%BRAND_TAGLINE%': BRAND.tagline,
    '%BRAND_DESCRIPTION%': BRAND.description,
    '%BRAND_THEME_COLOR%': BRAND.themeColor,
  }
  return {
    name: 'brand',
    transformIndexHtml(html) {
      let out = html
      for (const [key, value] of Object.entries(placeholders)) {
        out = out.split(key).join(value)
      }
      const leftover = out.match(/%BRAND_[A-Z_]+%/)
      if (leftover) throw new Error(`Unknown brand placeholder ${leftover[0]} in index.html`)
      return out
    },
    configureServer(server) {
      server.middlewares.use('/manifest.webmanifest', (_req, res) => {
        res.setHeader('Content-Type', 'application/manifest+json')
        res.end(webManifest())
      })
    },
    generateBundle() {
      this.emitFile({ type: 'asset', fileName: 'manifest.webmanifest', source: webManifest() })
    },
  }
}

export default defineConfig({
  plugins: [react(), brandPlugin()],
  define: {
    __APP_VERSION__: JSON.stringify(pkg.version),
  },
  server: {
    host: '0.0.0.0',
    port: 3000,
    proxy: {
      '/api': {
        target: process.env.VITE_API_URL || 'http://localhost:5000',
        changeOrigin: true
      }
    }
  }
})
