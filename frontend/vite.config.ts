import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import { fileURLToPath } from 'node:url';

const configDirectory = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, configDirectory, '');
  const apiProxyTarget =
    process.env.VITE_API_PROXY_TARGET?.trim()
    || env.VITE_API_PROXY_TARGET
    || process.env.VITE_API_URL?.trim()
    || env.VITE_API_URL
    || 'http://localhost:5000';

  return {
    plugins: [react()],
    resolve: {
      alias: {
        '@': path.resolve(configDirectory, './src'),
      },
    },
    server: {
      port: 5173,
      proxy: {
        '/api': {
          target: apiProxyTarget,
          changeOrigin: true,
        },
      },
    },
    build: {
      outDir: 'dist',
      sourcemap: true,
    },
  };
});
