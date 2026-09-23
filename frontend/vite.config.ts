import { resolve } from 'node:path';
import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const chartProxyTarget = env.VITE_CHART_PROXY_TARGET ?? 'http://127.0.0.1:5055';
  const legacyProxyTarget = env.VITE_LEGACY_PROXY_TARGET ?? 'http://127.0.0.1:5055';
  const devServerPort = Number(env.VITE_DEV_SERVER_PORT ?? '5174');
  const configDir = process.cwd();

  return {
    plugins: [react()],
    resolve: {
      alias: {
        '@': resolve(configDir, 'src'),
      },
    },
    server: {
      port: Number.isFinite(devServerPort) ? devServerPort : 5174,
      strictPort: true,
      proxy: {
        '/api': {
          target: legacyProxyTarget,
          changeOrigin: true,
        },
        '/chart-api': {
          target: chartProxyTarget,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/chart-api/, ''),
        },
        '/legacy-api': {
          target: legacyProxyTarget,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/legacy-api/, ''),
        },
      },
    },
    test: {
      environment: 'node',
    },
    build: {
      assetsDir: 'react-assets',
      // Keep the previous asset generation available while a new build is written.
      // This prevents Flask-served SPA routes from going blank mid-build when a tab
      // still references the prior hashed bundle.
      emptyOutDir: false,
    },
  };
});
