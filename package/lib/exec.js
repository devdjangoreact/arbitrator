import { spawn } from 'node:child_process';

// Run a command, streaming its stdout/stderr straight to our terminal so the
// underlying installers (caveman, react-doctor, graphify, npm) show their own
// progress. stdin is NOT inherited: these installers are non-interactive (we
// pass -y/--only/--project), and @clack leaves our own stdin in raw mode, which
// a spawned child that inherits it can choke on (caveman exited 1 inside the
// wizard but 0 standalone). Giving the child no stdin avoids that. Resolves with
// { code } — never rejects on a non-zero exit; callers decide what a tool-level
// failure means. Rejects only when the binary itself can't be spawned (ENOENT
// etc.), which the runtime pre-flight should prevent.
export function run(cmd, args = [], opts = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(cmd, args, {
      stdio: ['ignore', 'inherit', 'inherit'],
      // npx/headroom/graphify are .cmd shims on Windows -> shell needed.
      shell: process.platform === 'win32',
      ...opts,
    });
    child.on('error', reject);
    child.on('close', (code) => resolve({ code: code ?? 1 }));
  });
}

// Convenience: throw if the command exits non-zero. Used where a failure should
// surface in the final summary as ✗.
export async function runOrThrow(cmd, args = [], opts = {}) {
  const { code } = await run(cmd, args, opts);
  if (code !== 0) {
    throw new Error(`\`${cmd} ${args.join(' ')}\` exited with code ${code}`);
  }
}
