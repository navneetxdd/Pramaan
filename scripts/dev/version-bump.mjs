#!/usr/bin/env node
/**
 * Bump semver across engine, npm package, and Tauri bundle config in one commit.
 * Usage: npm run version:bump -- 0.3.0
 */
import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

const version = process.argv[2];
if (!version || !/^\d+\.\d+\.\d+$/.test(version)) {
  console.error("Usage: npm run version:bump -- <semver>, e.g. 0.3.0");
  process.exit(1);
}

const root = resolve(import.meta.dirname, "..");

function patchFile(path, replacer) {
  const full = resolve(root, path);
  const next = replacer(readFileSync(full, "utf8"));
  writeFileSync(full, next);
}

patchFile("engine/app/core/config.py", (text) =>
  text.replace(/APP_VERSION = "[^"]+"/, `APP_VERSION = "${version}"`),
);

patchFile("engine/app/__init__.py", (text) =>
  text.replace(/__version__ = "[^"]+"/, `__version__ = "${version}"`),
);

patchFile("package.json", (text) => {
  const pkg = JSON.parse(text);
  pkg.version = version;
  return `${JSON.stringify(pkg, null, 2)}\n`;
});

patchFile("src-tauri/tauri.conf.json", (text) => {
  const conf = JSON.parse(text);
  conf.version = version;
  return `${JSON.stringify(conf, null, 2)}\n`;
});

console.log(`Version bumped to ${version}`);
