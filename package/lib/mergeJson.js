import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'node:fs';
import { dirname } from 'node:path';

// Non-destructive deep merge for config files like .claude/settings.json and
// .mcp.json. Existing user values win on scalar conflicts UNLESS `overwrite` is
// passed; objects merge recursively; arrays are concatenated + de-duped by JSON
// identity. Never blind-clobbers a file we didn't create.

function isPlainObject(v) {
  return v !== null && typeof v === 'object' && !Array.isArray(v);
}

export function deepMerge(base, patch, { overwrite = false } = {}) {
  if (Array.isArray(base) && Array.isArray(patch)) {
    const out = [...base];
    for (const item of patch) {
      const sig = JSON.stringify(item);
      if (!out.some((x) => JSON.stringify(x) === sig)) out.push(item);
    }
    return out;
  }
  if (isPlainObject(base) && isPlainObject(patch)) {
    const out = { ...base };
    for (const [k, v] of Object.entries(patch)) {
      if (k in out) {
        out[k] = deepMerge(out[k], v, { overwrite });
      } else {
        out[k] = v;
      }
    }
    return out;
  }
  // scalar conflict
  return overwrite ? patch : base;
}

export function readJson(path) {
  if (!existsSync(path)) return {};
  const raw = readFileSync(path, 'utf8').trim();
  if (!raw) return {};
  return JSON.parse(raw);
}

export function writeJson(path, obj) {
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, JSON.stringify(obj, null, 2) + '\n', 'utf8');
}

// Read -> merge patch in -> write. Returns the merged object.
export function mergeIntoJsonFile(path, patch, opts) {
  const merged = deepMerge(readJson(path), patch, opts);
  writeJson(path, merged);
  return merged;
}
