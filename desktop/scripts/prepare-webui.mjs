import { cp, mkdir, rm } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const rootDir = path.resolve(__dirname, '..', '..');
const distDir = path.join(rootDir, 'dashboard', 'dist');
const targetDir = path.join(rootDir, 'desktop', 'resources', 'webui');

if (!existsSync(distDir)) {
  console.error('dashboard/dist is missing. Run `pnpm --dir dashboard build` first.');
  process.exit(1);
}

await rm(targetDir, { recursive: true, force: true });
await mkdir(targetDir, { recursive: true });
await cp(distDir, targetDir, { recursive: true });

console.log(`Copied WebUI to ${targetDir}`);
