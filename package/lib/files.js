import {
  readFileSync,
  writeFileSync,
  existsSync,
  mkdirSync,
  cpSync,
} from 'node:fs';
import { dirname } from 'node:path';

// Write a file only if it does not already exist. Returns true if written,
// false if it was left alone. Used for CLAUDE.md and other user-owned docs we
// must never clobber.
export function writeIfMissing(path, content) {
  if (existsSync(path)) return false;
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, content, 'utf8');
  return true;
}

// Append a fenced, marked block to a file (creating it if absent), but only
// once: if the marker is already present we leave the file untouched so re-runs
// don't duplicate. Marker is an HTML comment so it survives in Markdown.
export function appendMarkedBlock(path, marker, block) {
  const begin = `<!-- ${marker}:begin -->`;
  const end = `<!-- ${marker}:end -->`;
  const wrapped = `${begin}\n${block}\n${end}\n`;
  if (existsSync(path)) {
    const cur = readFileSync(path, 'utf8');
    if (cur.includes(begin)) return false; // already applied
    writeFileSync(path, cur.replace(/\s*$/, '\n\n') + wrapped, 'utf8');
    return true;
  }
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, wrapped, 'utf8');
  return true;
}

// Recursive directory copy (skill folders). Does not overwrite existing files
// unless force=true.
export function copyDir(src, dest, { force = false } = {}) {
  cpSync(src, dest, { recursive: true, force, errorOnExist: false });
}

// Ensure a line exists in .gitignore (create file if needed). Idempotent.
export function ensureGitignore(repoRoot, line) {
  const path = `${repoRoot}/.gitignore`;
  let cur = existsSync(path) ? readFileSync(path, 'utf8') : '';
  const lines = cur.split(/\r?\n/);
  if (lines.includes(line)) return false;
  cur = cur.replace(/\s*$/, '\n') + line + '\n';
  writeFileSync(path, cur, 'utf8');
  return true;
}
