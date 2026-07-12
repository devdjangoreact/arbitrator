import { runOrThrow } from '../lib/exec.js';
import { pythonInstaller } from '../lib/runtimes.js';

// Graphify = python CLI (`graphifyy` package, `graphify` command). Install via
// the first available python installer (uv > pipx > pip), then register the
// skill project-scoped so it writes into the target .claude/.
export const meta = {
  key: 'graphify',
  label: 'Graphify',
  kind: 'addon',
};

export async function run({ cwd }) {
  const installer = pythonInstaller(); // preflight guaranteed non-null
  if (installer === 'uv') {
    await runOrThrow('uv', ['tool', 'install', 'graphifyy'], { cwd });
  } else if (installer === 'pipx') {
    await runOrThrow('pipx', ['install', 'graphifyy'], { cwd });
  } else {
    await runOrThrow('pip', ['install', 'graphifyy'], { cwd });
  }
  // `graphify` bin is now on PATH (uv/pipx shim) or in pip's bin dir.
  await runOrThrow('graphify', ['install', '--project'], { cwd });
}
