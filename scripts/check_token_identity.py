"""Token identity cross-exchange audit tool.

Fetches fetchCurrencies() from all enabled exchanges, compares contract
addresses / network ids for each base code that appears on multiple exchanges,
and writes a markdown report + logs commonCurrencies remappings.

Usage:
  .venv\\Scripts\\python.exe scripts\\check_token_identity.py
  .venv\\Scripts\\python.exe scripts\\check_token_identity.py --output report.md
  .venv\\Scripts\\python.exe scripts\\check_token_identity.py --base EDGE BTC SOL

Never places any orders. Read-only.
"""
from __future__ import annotations

import argparse
import asyncio
import itertools
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from arbitrator.application.token_identity_service import TokenIdentityService
from arbitrator.config.logger import init_logger, logger
from arbitrator.config.settings import Settings
from arbitrator.exchanges.factory import Factory


async def _run(
    settings: Settings,
    factory: Factory,
    base_codes: list[str] | None,
    output_path: Path | None,
) -> int:
    named_exchanges = factory.create_many(settings.enabled_exchanges)
    if not named_exchanges:
        logger.error("No enabled exchanges in settings.")
        return 1

    exchange_ids = [ex.exchange_id for ex in named_exchanges]
    logger.info("Exchanges: {}", exchange_ids)

    # ── Step 1: resolve base codes ────────────────────────────────────────
    if base_codes:
        codes_to_check = base_codes
    else:
        # Derive from the symbol universe: take base part of each USDT-M swap
        all_symbols: set[str] = set()
        for ex in named_exchanges:
            try:
                syms = await ex.gateway.list_symbols()
                all_symbols.update(syms)
            except Exception:
                logger.exception("list_symbols failed | exchange={}", ex.exchange_id)
        codes_to_check = sorted({s.split("/")[0] for s in all_symbols if "/" in s})
        logger.info("Derived {} base codes from symbol universe", len(codes_to_check))

    if not codes_to_check:
        logger.error("No base codes to check.")
        return 1

    # ── Step 2: load currency network info ───────────────────────────────
    service = TokenIdentityService()
    await service.load(named_exchanges, codes_to_check)

    # ── Step 3: log commonCurrencies (shows ccxt-internal remappings) ─────
    logger.info("=== commonCurrencies per exchange ===")
    common = await service.load_common_currencies(named_exchanges)
    for ex_id, mapping in common.items():
        if mapping:
            # Filter to only show remappings relevant to our base codes
            relevant = {k: v for k, v in mapping.items() if k in codes_to_check or v in codes_to_check}
            if relevant:
                logger.warning(
                    "commonCurrencies relevant remappings | exchange={} mappings={}",
                    ex_id, relevant,
                )
            else:
                logger.info("commonCurrencies | exchange={} (no relevant remappings)", ex_id)
        else:
            logger.info("commonCurrencies | exchange={} empty / unsupported", ex_id)

    # ── Step 4: build report ─────────────────────────────────────────────
    pairs = list(itertools.combinations(exchange_ids, 2))
    rows = service.build_report_rows(
        [(a, b) for a, b in pairs],
        codes_to_check,
    )

    if not rows:
        logger.warning(
            "No base codes found on multiple exchanges — "
            "possibly fetchCurrencies is unsupported or returned no data."
        )

    conflicts = [r for r in rows if r["match_type"] == "conflict"]
    verified = [r for r in rows if r["match_type"] == "network_verified"]
    unverified = [r for r in rows if r["match_type"] == "symbol_only_ccxt_dedup"]

    logger.info(
        "Report summary | total={} conflicts={} verified={} unverified={}",
        len(rows), len(conflicts), len(verified), len(unverified),
    )

    if conflicts:
        logger.warning("=== CONFLICTS — these pairs will be BLOCKED ===")
        for r in conflicts:
            logger.warning(
                "CONFLICT | base={} {}/{} notes={}",
                r["base"], r["exchange_a"], r["exchange_b"], r["notes"],
            )

    # ── Step 5: write markdown ───────────────────────────────────────────
    md = _build_markdown(rows, conflicts, exchange_ids)
    if output_path:
        output_path.write_text(md, encoding="utf-8")
        logger.info("Report written to {}", output_path)
    else:
        print(md)

    # Clean up
    for ex in named_exchanges:
        try:
            await ex.gateway.close()
        except Exception:
            pass

    return 1 if conflicts else 0


def _build_markdown(
    rows: list[dict[str, object]],
    conflicts: list[dict[str, object]],
    exchange_ids: list[str],
) -> str:
    lines: list[str] = [
        "# Token Identity Cross-Exchange Audit",
        "",
        f"Exchanges checked: `{'`, `'.join(exchange_ids)}`",
        "",
    ]

    if conflicts:
        lines += [
            "## ⚠ Conflicts (different contract on same network — BLOCKED)",
            "",
            "| base | exchange_a | exchange_b | shared_networks | notes |",
            "| ---- | ---------- | ---------- | --------------- | ----- |",
        ]
        for r in conflicts:
            lines.append(
                f"| {r['base']} | {r['exchange_a']} | {r['exchange_b']} "
                f"| {r['shared_networks']} | {r['notes']} |"
            )
        lines.append("")

    lines += [
        "## Full Results",
        "",
        "| base | exchange_a | exchange_b | shared_networks | ids_match | match_type | block |",
        "| ---- | ---------- | ---------- | --------------- | --------- | ---------- | ----- |",
    ]
    for r in rows:
        ids_match = r["ids_match"]
        ids_str = "✓" if ids_match is True else ("✗" if ids_match is False else "—")
        block_str = "**YES**" if r["should_block"] else "no"
        lines.append(
            f"| {r['base']} | {r['exchange_a']} | {r['exchange_b']} "
            f"| {r['shared_networks']} | {ids_str} | {r['match_type']} | {block_str} |"
        )

    lines += [
        "",
        "### Legend",
        "- **network_verified**: ≥1 shared network with matching contract address — high confidence",
        "- **symbol_only_ccxt_dedup**: no contract data; relies on ccxt commonCurrencies only — manual review",
        "- **conflict**: contract ids differ on a shared network — **BLOCKED**",
        "",
        "> Note: `ids_match = —` means contract ids were absent (None) for that network on at least one side.",
        "> This does NOT mean a conflict — it means the exchange did not provide the address.",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Token identity cross-exchange audit.")
    parser.add_argument("--output", type=Path, help="Write markdown report to file.")
    parser.add_argument(
        "--base",
        nargs="+",
        metavar="CODE",
        help="Base codes to check (default: derived from symbol universe).",
    )
    args = parser.parse_args()

    settings = Settings()
    init_logger(console_level=settings.log_level)
    factory = Factory(settings=settings)
    raise SystemExit(
        asyncio.run(
            _run(
                settings=settings,
                factory=factory,
                base_codes=args.base,
                output_path=args.output,
            )
        )
    )


if __name__ == "__main__":
    main()
