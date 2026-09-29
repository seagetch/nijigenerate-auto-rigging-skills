import { defineConfig } from 'vite';
import { fileURLToPath } from 'node:url';
import { reviewReceiver } from './review-security.mjs';

export default defineConfig({
  plugins: [reviewReceiver({ endpoint: '/api/checklist-review', prefix: 'checklist-review' })],
  server: {
    host: '127.0.0.1',
    port: 5174,
    strictPort: false,
    cors: false,
    fs: { strict: true, allow: [fileURLToPath(new URL('.', import.meta.url))] },
  },
  preview: { host: '127.0.0.1', cors: false },
});
