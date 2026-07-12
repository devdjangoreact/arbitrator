import { spawnSync } from 'node:child_process';

// Probe whether a command exists on PATH. Cached per process so repeated checks
// across handlers are free.
const cache = new Map();

export function has(bin) {
  if (cache.has(bin)) return cache.get(bin);
  // `--version` is the most portable existence probe; some tools use `-V`.
  // We only care that the binary resolves, not what it prints.
  const probes = [['--version'], ['-V'], ['version']];
  let found = false;
  for (const args of probes) {
    const r = spawnSync(bin, args, {
      stdio: 'ignore',
      shell: process.platform === 'win32',
    });
    if (r.status === 0) {
      found = true;
      break;
    }
    // status null + no error sometimes still means present; ENOENT means not.
    if (r.error && r.error.code !== 'ENOENT' && r.status !== null) {
      found = true;
      break;
    }
  }
  cache.set(bin, found);
  return found;
}

// Return the first available python-package installer for graphify, or null.
// Order matches graphify's own docs: uv > pipx > pip.
export function pythonInstaller() {
  if (has('uv')) return 'uv';
  if (has('pipx')) return 'pipx';
  if (has('pip')) return 'pip';
  return null;
}

// Find a CPython interpreter >= minMinor (3.x) that also has pip. Returns the
// interpreter command ('python' | 'python3' | 'py') or null. Cached.
// Needed by headroom: its abi3 wheel requires cp310+, and we must install via
// that interpreter's `pip` (NOT pipx, which may pick a Python with no matching
// wheel and trigger a doomed Rust/maturin source build).
let _pyCache;
export function pythonAtLeast(minMinor = 10) {
  if (_pyCache !== undefined) return _pyCache;
  const candidates = ['python', 'python3', 'py'];
  // Use single-quoted string literal inside so there are no double-quotes to be
  // mangled by the Windows shell; spawn without a shell so the -c arg is passed
  // verbatim (python.exe resolves on PATH without a shell).
  const probe =
    "import sys;import importlib.util as u;" +
    "print(sys.version_info[0],sys.version_info[1],1 if u.find_spec('pip') else 0)";
  for (const cmd of candidates) {
    const r = spawnSync(cmd, ['-c', probe], { encoding: 'utf8' });
    if (r.status !== 0 || !r.stdout) continue;
    const [maj, min, hasPip] = r.stdout.trim().split(/\s+/).map(Number);
    if (maj === 3 && min >= minMinor && hasPip === 1) {
      _pyCache = cmd;
      return cmd;
    }
  }
  _pyCache = null;
  return null;
}

// Given the selected feature/addon set, compute the runtimes that MUST exist.
// Returns an array of { need, why } for anything missing. Empty => good to go.
// Plan decision #3: any gap is a hard failure before we write anything.
export function preflight(selection) {
  const missing = [];

  // npx underpins caveman + react-doctor.
  const needsNpx = selection.caveman || selection.reactDoctor;
  if (needsNpx && !has('npx')) {
    missing.push({ need: 'npx', why: 'caveman / react-doctor install', fix: 'install Node.js ≥18 (includes npx): https://nodejs.org' });
  }

  // Ponytail installs via the Claude Code CLI (`claude plugin install`).
  if (selection.ponytail && !has('claude')) {
    missing.push({
      need: 'claude (Claude Code CLI)',
      why: 'ponytail install (`claude plugin install`)',
      fix: 'install Claude Code so the `claude` CLI is on PATH: https://claude.com/code',
    });
  }

  // Graphify: any python installer (uv > pipx > pip). graphifyy builds cleanly.
  if (selection.graphify && !pythonInstaller()) {
    missing.push({
      need: 'uv | pipx | pip',
      why: 'graphify install (python package `graphifyy`)',
      fix: 'install uv (https://docs.astral.sh/uv) or pipx (https://pipx.pypa.io)',
    });
  }

  // Headroom: needs CPython >= 3.10 WITH pip specifically — its only prebuilt
  // wheels are cp310-abi3 (+ mac/linux). Installing via pipx can land on a
  // Python with no matching wheel -> Rust/maturin source build -> failure. So
  // we require a real python>=3.10+pip and install through it.
  if (selection.headroom && !pythonAtLeast(10)) {
    missing.push({
      need: 'python ≥3.10 with pip',
      why: 'headroom install (`headroom-ai` CLI, abi3 wheel needs cp310+)',
      fix: 'install Python 3.10+ from https://python.org (ensure pip is included)',
    });
  }

  return missing;
}
