import { spawnSync } from 'node:child_process';
import { delimiter } from 'node:path';
import { runOrThrow, run as exec } from '../lib/exec.js';
import { pythonAtLeast } from '../lib/runtimes.js';
import { ensureUserPath } from '../lib/path.js';
import { log } from '../lib/log.js';

// Headroom = token-compression layer ("context optimization"). The real
// `headroom` CLI ships in the PYTHON package `headroom-ai` (the npm package of
// the same name is a JS library with NO bin — unusable for the CLI).
//
// Install gotcha: PyPI provides prebuilt wheels only as cp310-abi3 (+ macOS-arm64
// / Linux). On a Python without a matching wheel, pip builds the Rust extension
// from sdist via maturin and fails on most machines. pipx is the trap here — it
// spins an isolated venv that may use a Python (e.g. 3.12) with no wheel. So we
// install with `python -m pip --user` through a CPython >= 3.10 (preflight
// guarantees one), which resolves the abi3 wheel and just works.
//
// Integration: use `headroom init claude` (durable Claude Code hooks + provider
// routing, then returns) — NOT `headroom wrap claude`, which launches Claude
// live through the proxy and blocks.
export const meta = {
  key: 'headroom',
  label: 'Headroom',
  kind: 'feature',
};

// Ask the interpreter where pip --user scripts land, so we can find the
// `headroom` entry point even if that dir isn't on this process's PATH yet.
function userScriptsDir(py) {
  const code =
    'import sysconfig,site,os;' +
    "print(sysconfig.get_path('scripts',f'{os.name}_user') or " +
    "os.path.join(site.getuserbase(),'Scripts'))";
  // No shell: pass the -c arg verbatim (avoids Windows quote mangling).
  const r = spawnSync(py, ['-c', code], { encoding: 'utf8' });
  return r.status === 0 && r.stdout ? r.stdout.trim() : null;
}

export async function run({ cwd }) {
  const py = pythonAtLeast(10); // preflight guarantees non-null
  if (!py) throw new Error('no CPython ≥3.10 with pip found');

  // Install the base package (pure-python + abi3 wheel). No `[all]` — those
  // extras pull native/ML deps that need a build toolchain.
  await runOrThrow(py, ['-m', 'pip', 'install', '--user', 'headroom-ai'], { cwd });

  // Make the user-scripts dir visible to the `headroom init` call.
  const scripts = userScriptsDir(py);
  const env = { ...process.env };
  if (scripts) env.PATH = `${scripts}${delimiter}${env.PATH || ''}`;

  // Durable Claude Code integration. headroom binary now resolvable via PATH.
  const { code } = await exec('headroom', ['init', 'claude'], { cwd, env });
  if (code !== 0) {
    throw new Error(
      `headroom installed but \`headroom init claude\` exited ${code}. ` +
        `Run it manually: ${scripts ? scripts + '\\' : ''}headroom init claude`,
    );
  }

  // Durably put the scripts dir on the user's PATH so `headroom` resolves in new
  // shells (the env.PATH prepend above only covered this process).
  if (scripts) {
    const r = ensureUserPath(scripts);
    if (r === 'added') {
      log.success(`Added ${scripts} to your user PATH — open a new terminal to use \`headroom\`.`);
    } else if (r === 'present') {
      log.dim('headroom scripts dir already on PATH.');
    } else {
      log.warn(`Could not update PATH automatically. Add this dir yourself: ${scripts}`);
    }
  }
}
