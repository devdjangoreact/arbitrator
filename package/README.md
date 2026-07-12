# ufoz-tools

One-shot setup wizard that installs a chosen set of Claude Code tools into the
current project — delegating to each tool's own official installer instead of
reimplementing them.

## Usage

Run it inside the project you want to set up:

    npx ufoz-tools

It's interactive: answer Yes/No per tool, then it does the rest. Requires
Node ≥18.

## What it installs

The wizard groups tools into three sections — **Core** installs machine-wide,
everything else is per-project.

**Core** (global install)

| Choice | What it does |
|--------|--------------|
| Headroom | `pip install --user headroom-ai` (Python ≥3.10) installs the CLI **globally**; `headroom init claude` wires hooks into **this project** only |

**Features** (per-project)

| Choice | What it does |
|--------|--------------|
| Caveman | runs `npx github:JuliusBrussee/caveman -- --only claude` |
| Karpathy CLAUDE.md | writes an opinionated `CLAUDE.md` (appends, never clobbers) |
| Supabase MCP | writes a Supabase server block to `.mcp.json` (token gitignored) |
| Ponytail | runs `claude plugin install ponytail@ponytail` (project scope) |

**Addons** (per-project skills)

| Choice | What it does |
|--------|--------------|
| anvilCV | copies the AnvilCV extractor skill into `.claude/skills/` |
| Graphify | `uv\|pipx\|pip install graphifyy` + `graphify install --project` |
| React-Doctor | runs `npx react-doctor@latest install` |

## Safe by design

All writes are non-destructive and the wizard is idempotent (safe to re-run).
If a required runtime (npm/npx/uv/pipx/pip, the `claude` CLI for Ponytail, or
Python ≥3.10 for Headroom) for a selected tool is missing, it aborts **before**
making any changes and tells you what to install.

> Run the wizard in a plain terminal, not inside a Claude Code session — Ponytail
> installs via the `claude` CLI, which can't be nested.

## More

Part of [agent-toolbox](https://github.com/UfozDelta/agent-toolbox) — see the
repo for full docs and the `ufoz` Claude Code plugin.
