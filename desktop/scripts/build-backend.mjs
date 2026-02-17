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
const builtinStarsSrc = path.join(rootDir, 'astrbot', 'builtin_stars');
const builtinStarsDest = 'astrbot/builtin_stars';

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
  '--collect-all',
  'pip',
  '--collect-all',
  'bs4',
  '--collect-all',
  'readability',
  '--collect-all',
  'lxml',
  '--collect-all',
  'lxml_html_clean',
  '--collect-all',
  'rfc3987_syntax',
  '--collect-submodules',
  'astrbot.api',
  '--collect-submodules',
  'astrbot.builtin_stars',
  '--collect-data',
  'certifi',
  '--add-data',
  `${builtinStarsSrc}${dataSeparator}${builtinStarsDest}`,
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
  console.error(`Failed to run 'uv': ${result.error.message}`);
  process.exit(typeof result.status === 'number' ? result.status : 1);
}

if (result.status !== 0) {
  console.error(
    `'uv' exited with status ${result.status} while running PyInstaller. ` +
      'Verify that uv and pyinstaller are installed and that arguments are valid.',
  );
  process.exit(result.status ?? 1);
}

process.exit(0);
