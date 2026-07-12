import { join } from 'node:path';
import { mergeIntoJsonFile } from '../lib/mergeJson.js';
import { ensureGitignore } from '../lib/files.js';
import { log } from '../lib/log.js';

// Supabase MCP server config. We never run anything — just write a server block
// into .mcp.json. The access token is sensitive: we prefer an env placeholder
// and gitignore .mcp.json so a literal token can't be committed by accident.
export const meta = {
  key: 'supabase',
  label: 'Supabase MCP',
  kind: 'feature',
};

// answers.supabase = { projectRef, token } (token may be empty -> env placeholder)
export async function run({ cwd, answers }) {
  const { projectRef = '', token = '' } = answers.supabase || {};

  const env = token
    ? { SUPABASE_ACCESS_TOKEN: token }
    : { SUPABASE_ACCESS_TOKEN: '${SUPABASE_ACCESS_TOKEN}' };

  const args = ['-y', '@supabase/mcp-server-supabase@latest'];
  if (projectRef) args.push(`--project-ref=${projectRef}`);

  mergeIntoJsonFile(join(cwd, '.mcp.json'), {
    mcpServers: {
      supabase: { command: 'npx', args, env },
    },
  });

  // Keep secrets out of git.
  ensureGitignore(cwd, '.mcp.json');

  if (token) {
    log.warn('Supabase token written to .mcp.json (gitignored). Prefer the SUPABASE_ACCESS_TOKEN env var for shared repos.');
  } else {
    log.dim('Supabase configured with ${SUPABASE_ACCESS_TOKEN} placeholder — set that env var before launching Claude.');
  }
}
