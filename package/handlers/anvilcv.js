import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { existsSync } from 'node:fs';
import { copyDir } from '../lib/files.js';

// anvilCV is a skill bundled in this repo (skills/anvilcv-extract). Copy it into
// the target project's .claude/skills/ so it loads as /ufoz:anvilcv-extract.
export const meta = {
  key: 'anvilcv',
  label: 'anvilCV',
  kind: 'addon',
};

const here = dirname(fileURLToPath(import.meta.url)); // cli/handlers
// Skill is bundled inside the package at cli/skills/anvilcv-extract so it ships
// with `npx ufoz-tools` (npm can't pack files above the package root).
const SKILL_SRC = join(here, '..', 'skills', 'anvilcv-extract');

export async function run({ cwd }) {
  if (!existsSync(SKILL_SRC)) {
    throw new Error(`anvilCV skill source not found at ${SKILL_SRC}`);
  }
  const dest = join(cwd, '.claude', 'skills', 'anvilcv-extract');
  copyDir(SKILL_SRC, dest, { force: false });
}
