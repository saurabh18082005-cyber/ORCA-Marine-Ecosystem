import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // host: true binds Vite to 0.0.0.0 instead of only localhost, so a phone
  // on the same Wi-Fi/hotspot as your laptop can open
  // http://<your-laptop-LAN-IP>:5173 and reach the dev server. Without this,
  // "npm run dev" only answers on localhost and mobile testing silently
  // fails to even load the page.
  server: {
    host: true,
  },
  preview: {
    host: true,
  },
})
