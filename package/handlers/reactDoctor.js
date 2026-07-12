import { runOrThrow } from '../lib/exec.js';

// React-Doctor installs its skill/rules into the current project's .claude via
// its own installer. Run in the target cwd so it writes there.
export const meta = {
  key: 'reactDoctor',
  label: 'React-Doctor',
  kind: 'addon',
};

export async function run({ cwd }) {
  await runOrThrow('npx', ['-y', 'react-doctor@latest', 'install'], { cwd });
}
