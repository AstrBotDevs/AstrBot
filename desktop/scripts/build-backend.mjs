import { spawnSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const rootDir = path.resolve(__dirname, '..', '..');
const outputDir = path.join(rootDir, 'desktop', 'resources', 'backend');
const workDir = path.join(rootDir, 'desktop', 'resources', '.pyinstaller');
const dataSeparator = process.platform === 'win32' ? ';' : ':';
const kbStopwordsSrc = path.join(
  rootDir,
  'astrbot',
  'core',
  'knowledge_base',
  'retrieval',
  'hit_stopwords.txt',
);
const kbStopwordsDest = 'astrbot/core/knowledge_base/retrieval';

const args = [
  'run',
  '--with',
  'pyinstaller',
  'python',
  '-m',
  'PyInstaller',
  '--noconfirm',
  '--clean',
  '--onefile',
  '--name',
  'astrbot-backend',
  '--collect-all',
  'aiosqlite',
  '--add-data',
  `${kbStopwordsSrc}${dataSeparator}${kbStopwordsDest}`,
  '--distpath',
  outputDir,
  '--workpath',
  workDir,
  '--specpath',
  workDir,
  path.join(rootDir, 'main.py'),
];

const result = spawnSync('uv', args, {
  cwd: rootDir,
  stdio: 'inherit',
  shell: process.platform === 'win32',
});

if (result.error) {
  console.error('Failed to run uv. Make sure uv and pyinstaller are installed.');
  process.exit(1);
}

process.exit(result.status ?? 1);
