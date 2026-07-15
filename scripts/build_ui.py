"""Assemble static/index.html from partials under static/partials/."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "src" / "arbitrator" / "presentation" / "static"
PARTIALS = STATIC / "partials"
INCLUDE_RE = re.compile(r"<!--\s*include\s+([\w./-]+)\s*-->")


def _read_partial(rel_path: str) -> str:
    path = PARTIALS / rel_path
    if not path.is_file():
        raise FileNotFoundError(f"Missing partial: {path}")
    return path.read_text(encoding="utf-8")


def _expand_includes(content: str, depth: int = 0) -> str:
    if depth > 20:
        raise RuntimeError("Include depth exceeded (circular includes?)")

    def repl(match: re.Match[str]) -> str:
        included = _expand_includes(_read_partial(match.group(1)), depth + 1)
        return included.rstrip() + "\n"

    return INCLUDE_RE.sub(repl, content)


def build_index_html() -> str:
    body_parts = [
        _expand_includes(_read_partial("sidebar.html")),
        "  <div class=\"main\">\n",
        _expand_includes(_read_partial("pages/screener.html")),
        _expand_includes(_read_partial("pages/monitors.html")),
        _expand_includes(_read_partial("pages/opportunity.html")),
        _expand_includes(_read_partial("pages/orders.html")),
        _expand_includes(_read_partial("pages/paper_trades.html")),
        _expand_includes(_read_partial("pages/settings.html")),
        "  </div>\n",
    ]
    head = _read_partial("layout/head.html")
    scripts = _read_partial("layout/scripts.html")
    return (
        "<!DOCTYPE html>\n"
        "<html lang=\"uk\">\n"
        "<head>\n"
        f"{head}"
        "</head>\n"
        "<body>\n"
        "<div class=\"app\">\n"
        f"{''.join(body_parts)}"
        "</div>\n"
        f"{scripts}"
        "</body>\n"
        "</html>\n"
    )


def main() -> None:
    out_path = STATIC / "index.html"
    out_path.write_text(build_index_html(), encoding="utf-8")
    print("Wrote", out_path)


if __name__ == "__main__":
    main()
