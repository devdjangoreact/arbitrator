#!/usr/bin/env node
import {
  intro,
  outro,
  confirm,
  multiselect,
  text,
  note,
  isCancel,
  cancel,
  group,
} from '@clack/prompts';

import { log } from './lib/log.js';
import { preflight } from './lib/runtimes.js';

import * as headroom from './handlers/headroom.js';
import * as caveman from './handlers/caveman.js';
import * as karpathy from './handlers/karpathy.js';
import * as supabase from './handlers/supabase.js';
import * as ponytail from './handlers/ponytail.js';
import * as anvilcv from './handlers/anvilcv.js';
import * as graphify from './handlers/graphify.js';
import * as reactDoctor from './handlers/reactDoctor.js';

// Ordered: features first (config/installers), addons last (skills).
const HANDLERS = [
  headroom,
  caveman,
  karpathy,
  supabase,
  ponytail,
  anvilcv,
  graphify,
  reactDoctor,
];

function bail(value) {
  if (isCancel(value)) {
    cancel('Setup cancelled.');
    process.exit(0);
  }
  return value;
}

async function main() {
  const cwd = process.cwd();
  intro('ufoz-tools — Claude Code setup');
  log.dim(`Target project: ${cwd}`);

  // --- 1. Core --------------------------------------------------------------
  note(
    'Installs the headroom CLI GLOBALLY (pip --user, shared across projects);\n' +
      'hooks wire into THIS project only.',
    'Core',
  );
  const core = {
    headroom: bail(
      await confirm({
        message: 'Headroom (global CLI + project hooks)?',
        initialValue: false,
      }),
    ),
  };

  // --- 2. Feature toggles ---------------------------------------------------
  const features = await group(
    {
      caveman: () =>
        confirm({ message: 'Caveman (compressed agent comms)?', initialValue: false }),
      karpathy: () =>
        confirm({ message: 'Karpathy CLAUDE.md (opinionated agent guide)?', initialValue: false }),
      supabase: () =>
        confirm({ message: 'Supabase MCP server?', initialValue: false }),
      ponytail: () =>
        confirm({ message: 'Ponytail (minimal-code enforcement plugin)?', initialValue: false }),
    },
    { onCancel: () => bail(Symbol.for('cancel')) },
  );

  // --- 3. Addons (multiselect) ---------------------------------------------
  const addons = bail(
    await multiselect({
      message: 'Addons (space to toggle, enter to confirm):',
      required: false,
      options: [
        { value: 'anvilcv', label: 'anvilCV', hint: 'resume-bullet context extractor' },
        { value: 'graphify', label: 'Graphify', hint: 'codebase knowledge graph' },
        { value: 'reactDoctor', label: 'React-Doctor', hint: 'React lint/audit skill' },
      ],
    }),
  );

  // Flatten into one selection map keyed by handler.meta.key.
  const selection = {
    ...core,
    ...features,
    anvilcv: addons.includes('anvilcv'),
    graphify: addons.includes('graphify'),
    reactDoctor: addons.includes('reactDoctor'),
  };

  const chosen = HANDLERS.filter((h) => selection[h.meta.key]);
  if (chosen.length === 0) {
    outro('Nothing selected — exiting.');
    return;
  }

  // --- 4. Conditional follow-up prompts ------------------------------------
  const answers = {};
  if (selection.supabase) {
    answers.supabase = {
      projectRef: bail(
        await text({
          message: 'Supabase project ref (optional, leave blank to fill later):',
          placeholder: 'abcdefghijklmnop',
          defaultValue: '',
        }),
      ),
      token: bail(
        await text({
          message: 'Supabase access token (optional — blank uses ${SUPABASE_ACCESS_TOKEN} env):',
          placeholder: '',
          defaultValue: '',
        }),
      ),
    };
  }

  // --- 5. Pre-flight: hard-fail on any missing runtime ---------------------
  const missing = preflight(selection);
  if (missing.length) {
    log.error('Missing required runtime(s) — aborting before any changes:');
    for (const m of missing) {
      log.plain(`  • ${m.need}  (needed for ${m.why})`);
      log.dim(`      → ${m.fix}`);
    }
    cancel('No changes were made. Install the runtime(s) above and re-run.');
    process.exit(1);
  }

  // --- 6. Dispatch ----------------------------------------------------------
  const results = [];
  for (const h of chosen) {
    log.step(`Installing ${h.meta.label}…`);
    try {
      await h.run({ cwd, answers });
      log.success(`${h.meta.label} done`);
      results.push({ label: h.meta.label, ok: true });
    } catch (err) {
      log.error(`${h.meta.label} failed: ${err.message}`);
      results.push({ label: h.meta.label, ok: false, err: err.message });
    }
  }

  // --- 7. Summary -----------------------------------------------------------
  log.plain('');
  log.plain('Summary:');
  for (const r of results) {
    if (r.ok) log.success(r.label);
    else log.error(`${r.label} — ${r.err}`);
  }
  const failed = results.filter((r) => !r.ok).length;
  outro(
    failed
      ? `Finished with ${failed} failure(s). Re-run after fixing, the wizard is idempotent.`
      : 'All set. Launch Claude Code in this project to use the new tools.',
  );
  process.exit(failed ? 1 : 0);
}

main().catch((err) => {
  log.error(err.stack || String(err));
  process.exit(1);
});
