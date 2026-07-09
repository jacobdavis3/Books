import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import basicSsl from '@vitejs/plugin-basic-ssl'

// https://vite.dev/config/
export default defineConfig(({ command }) => ({
  base: command === 'build' ? '/Books/' : '/',
  plugins: [react(), basicSsl()],
}))
