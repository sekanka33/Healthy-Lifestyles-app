/// <reference types="vitest/config" />
import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { port: 5174, strictPort: true },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: false,
    // Run files one after another: parallel jsdom workers time out starting on slower machines.
    // Threads start much faster than forked processes; forks timed out starting on slow Windows machines.
    pool: 'threads',
    fileParallelism: false,
    // Reuse one worker for all files (setup.ts resets DOM, storage and stubbed globals after each test).
    isolate: false,
    testTimeout: 20_000,
  },
});
