import { spawnSync } from 'node:child_process';
import { join } from 'node:path';
import { homedir } from 'node:os';
import { existsSync, readFileSync, writeFileSync } from 'node:fs';

// Durably add `dir` to the CURRENT USER's persistent PATH so new shells resolve
// binaries installed there (e.g. headroom from `pip install --user`). Idempotent
// and current-user scoped (no admin). Returns 'added' | 'present' | 'failed'.
export function ensureUserPath(dir) {
  return process.platform === 'win32' ? addWindows(dir) : addUnix(dir);
}

// Windows: edit the USER PATH via the .NET API, NOT `setx PATH "%PATH%;.."`.
// `%PATH%` is the merged user+system value (truncated at 1024 chars); writing it
// back corrupts PATH. SetEnvironmentVariable(...,'User') touches only the user
// portion and broadcasts WM_SETTINGCHANGE so the change is durable.
function addWindows(dir) {
  // Single-quoted PS literal; escape any embedded single quotes by doubling.
  const lit = dir.replace(/'/g, "''");
  const ps =
    `$d='${lit}';` +
    "$p=[Environment]::GetEnvironmentVariable('PATH','User');" +
    "if(-not $p){$p=''};" +
    "$parts=($p -split ';')|Where-Object{$_ -ne ''};" +
    'if($parts -notcontains $d){' +
    "[Environment]::SetEnvironmentVariable('PATH',($p.TrimEnd(';')+';'+$d),'User');" +
    "'added'}else{'present'}";
  const r = spawnSync(
    'powershell',
    ['-NoProfile', '-NonInteractive', '-Command', ps],
    { encoding: 'utf8' },
  );
  if (r.status !== 0 || !r.stdout) return 'failed';
  const out = r.stdout.trim();
  return out === 'added' || out === 'present' ? out : 'failed';
}

// Unix: append a marked `export PATH=...` block to the user's shell rc (and
// .profile for login shells). The marker is a SHELL comment (`#`) — not the HTML
// comment appendMarkedBlock uses, which would be a syntax error sourced by bash.
// No-ops per file if the marker is already present, so re-runs don't duplicate.
// 'added' if any file was written, else 'present'.
function addUnix(dir) {
  const home = homedir();
  const shell = process.env.SHELL || '';
  const rc = shell.includes('zsh') ? '.zshrc' : '.bashrc';
  const files = [...new Set([rc, '.profile'])];
  const marker = '# ufoz-tools:headroom-path';
  const blockToAppend = `\n${marker}\nexport PATH="${dir}:$PATH"\n`;
  try {
    let wrote = false;
    for (const f of files) {
      const path = join(home, f);
      const cur = existsSync(path) ? readFileSync(path, 'utf8') : '';
      if (cur.includes(marker)) continue; // already applied
      writeFileSync(path, cur.replace(/\s*$/, '\n') + blockToAppend, 'utf8');
      wrote = true;
    }
    return wrote ? 'added' : 'present';
  } catch {
    return 'failed';
  }
}
