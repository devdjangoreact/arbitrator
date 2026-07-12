import { runOrThrow } from '../lib/exec.js';

// Install ponytail as a real project-scoped Claude Code plugin. Declaring it in
// settings.json is NOT enough — CC activates a plugin for a project only when a
// per-project install record exists in ~/.claude/plugins/installed_plugins.json,
// which only `claude plugin install` writes. Both calls are idempotent. Requires
// the `claude` CLI and a plain terminal (running the wizard inside a CC session
// is unsupported — nested claude).
export const meta = {
  key: 'ponytail',
  label: 'Ponytail',
  kind: 'feature',
};

export async function run({ cwd }) {
  await runOrThrow(
    'claude',
    ['plugin', 'marketplace', 'add', 'DietrichGebert/ponytail', '--scope', 'project'],
    { cwd },
  );
  await runOrThrow(
    'claude',
    ['plugin', 'install', 'ponytail@ponytail', '--scope', 'project'],
    { cwd },
  );
}
