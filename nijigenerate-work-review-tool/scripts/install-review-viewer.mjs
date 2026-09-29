#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const templateDir = path.join(here, "review-viewer-template");

function usage() {
  console.error("Usage: node install-review-viewer.mjs --project <project-dir> [--viewer <viewer-dir-name>]");
  process.exit(2);
}

function arg(name) {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : null;
}

const projectDir = arg("--project");
const viewerName = arg("--viewer") || "review-viewer";
if (!projectDir) usage();

try {
  if (!/^[a-zA-Z0-9][a-zA-Z0-9._-]*$/.test(viewerName)) throw new Error('Invalid viewer directory name');
  const projectRoot = path.resolve(projectDir);
  if (!fs.statSync(projectRoot).isDirectory()) throw new Error('Invalid project directory');
  const dest = path.join(projectRoot, viewerName);
  for (let current = dest; ; current = path.dirname(current)) {
    try {
      if (fs.lstatSync(current).isSymbolicLink()) throw new Error('Symlink path');
    } catch (error) { if (error.code !== 'ENOENT') throw error; }
    if (path.dirname(current) === current) break;
  }
  if (dest === templateDir || dest.startsWith(templateDir + path.sep)) throw new Error('Cannot install inside the template');
  fs.mkdirSync(dest); // Exclusive: an existing directory or dangling symlink is rejected.
  fs.cpSync(templateDir, dest, {
    recursive: true,
    force: false,
    errorOnExist: true,
    filter(source) {
      const rel = path.relative(templateDir, source);
      return !rel.split(path.sep).some(part => ['node_modules', 'dist', 'projects', 'reviews', 'review-results'].includes(part));
    },
  });
  console.log(JSON.stringify({
    viewerDir: viewerName,
    next: [
      `From your project directory: cd ${viewerName}`,
      'npm ci',
      'npm run dev -- --port 5173',
      'open http://127.0.0.1:5173/?manifest=/projects/<review-project>/manifest.json',
    ],
  }, null, 2));
} catch {
  console.error('Installation failed: choose a new viewer directory in an existing, non-symlink project directory. Existing files were not overwritten.');
  process.exitCode = 1;
}
