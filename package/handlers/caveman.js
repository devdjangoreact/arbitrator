import { runOrThrow } from '../lib/exec.js';

// Caveman ships its own idempotent installer. We invoke the single-agent npx
// form scoped to claude-code. Repo: JuliusBrussee/caveman (not ufoz).
export const meta = {
  key: 'caveman',
  label: 'Caveman',
  kind: 'feature',
};

export async function run({ cwd }) {
  // Agent id is `claude` (Claude Code) per `caveman --list`, not `claude-code`.
  await runOrThrow(
    'npx',
    ['-y', 'github:JuliusBrussee/caveman', '--', '--only', 'claude'],
    { cwd },
  );
}
