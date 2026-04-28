import { chmod, copyFile, mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(scriptDir, "../..");
const publicScriptsDir = resolve(repoRoot, "docs/public/scripts");

const files = [
  { name: "deploy-cli.sh", mode: 0o755 },
  { name: "deploy-cli.ps1", mode: 0o644 },
];

await mkdir(publicScriptsDir, { recursive: true });

for (const file of files) {
  const source = resolve(repoRoot, "scripts", file.name);
  const target = resolve(publicScriptsDir, file.name);
  await copyFile(source, target);
  await chmod(target, file.mode);
  console.log(`Copied ${file.name} to docs/public/scripts/`);
}
