---
name: anvilcv-extract
description: Explore the current codebase and produce an AnvilCV context document used to generate resume bullets. Run on demand inside the repo you want bullets for.
disable-model-invocation: true
---

# AnvilCV Context Extractor

Read the full extraction protocol at `${CLAUDE_SKILL_DIR}/content_extract.md`
and follow it exactly.

That file tells you:
- which two questions to ask the developer before exploring,
- which `git` commands to run for ownership / contributor checks,
- the exact headed-section output format to emit.

Do not begin exploring the codebase or writing any section until the developer
has answered the opening questions, as instructed in the protocol file.

Two hard rules from the protocol, restated so they are not missed:
- **Ask the three opening questions first, then STOP** and wait for the reply
  before doing anything else.
- **The final output is a file, not chat.** Write the completed document to
  `anvilcv-context.md` in the repo root (current working directory), overwriting
  if present. In chat, report only the file path plus a 2–3 line summary — never
  paste the section contents.
