from __future__ import annotations

import asyncio
from collections.abc import Sequence

from arbitrator.config.logger import logger
from arbitrator.domain.exchange.named_exchange import NamedExchange
from arbitrator.domain.universe.token_identity import (
    CurrencyNetworkInfo,
    MatchResult,
    TokenIdentityComparer,
)


class TokenIdentityService:
    """Loads and caches currency network info; compares token identity across exchanges.

    Usage pattern:
      1. Call load(exchanges, base_codes) once at startup (or on-demand).
      2. Call compare(base_code, exchange_a, exchange_b) synchronously per trade.
      3. Call common_currencies_report(exchanges) for audit logging.

    The cache is keyed by (exchange_id, base_code) -> CurrencyNetworkInfo.  It is never
    invalidated automatically — tokens don't change contract addresses.
    """

    def __init__(self) -> None:
        # (exchange_id, base_code) -> CurrencyNetworkInfo
        self._cache: dict[tuple[str, str], CurrencyNetworkInfo] = {}
        # exchange_id -> commonCurrencies remapping dict
        self._common_currencies: dict[str, dict[str, str]] = {}

    async def load(
        self,
        named_exchanges: Sequence[NamedExchange],
        base_codes: Sequence[str],
    ) -> None:
        """Fetch currency network info for all exchanges in parallel.

        Missing exchanges (fetchCurrencies unsupported) are silently skipped.
        Partial results are fine — compare() degrades gracefully when info is absent.
        """
        if not base_codes:
            return

        async def _fetch_one(exchange: NamedExchange) -> None:
            try:
                result = await exchange.gateway.fetch_currency_networks(base_codes)
            except Exception:
                logger.exception(
                    "token_identity load failed | exchange={}",
                    exchange.exchange_id,
                )
                return
            for code, info in result.items():
                self._cache[(exchange.exchange_id, code)] = info
            logger.info(
                "token_identity loaded | exchange={} codes_found={}/{}",
                exchange.exchange_id,
                len(result),
                len(base_codes),
            )
            # Log exchanges where most codes have no network info — operators
            # need to know this so they don't assume coverage that doesn't exist.
            no_networks = sum(
                1 for info in result.values() if not info.network_ids
            )
            if no_networks > len(result) * 0.5:
                logger.warning(
                    "token_identity: {}/{} codes have no network data | exchange={}. "
                    "Cross-exchange matching will fall back to symbol_only_ccxt_dedup.",
                    no_networks,
                    len(result),
                    exchange.exchange_id,
                )

        await asyncio.gather(*(_fetch_one(ex) for ex in named_exchanges))

    async def load_common_currencies(
        self,
        named_exchanges: Sequence[NamedExchange],
    ) -> dict[str, dict[str, str]]:
        """Fetch and cache the commonCurrencies table for each exchange.

        Returns the mapping for all exchanges so callers can log / audit it.
        """
        async def _fetch_one(exchange: NamedExchange) -> None:
            try:
                mapping = await exchange.gateway.common_currencies()
            except Exception:
                logger.exception(
                    "common_currencies fetch failed | exchange={}",
                    exchange.exchange_id,
                )
                return
            self._common_currencies[exchange.exchange_id] = mapping
            logger.info(
                "commonCurrencies loaded | exchange={} remappings={}",
                exchange.exchange_id,
                len(mapping),
            )
            logger.debug("commonCurrencies detail | exchange={} {}", exchange.exchange_id, mapping)

        await asyncio.gather(*(_fetch_one(ex) for ex in named_exchanges))
        return dict(self._common_currencies)

    def compare(
        self,
        base_code: str,
        exchange_a: str,
        exchange_b: str,
    ) -> MatchResult:
        """Compare token identity for base_code between two exchanges.

        Resolution order:
        1. If commonCurrencies remapping differs between the two exchanges →
           "conflict", should_block=True. (Works even when fetchCurrencies is
           unsupported, e.g. MEXC: the ccxt per-exchange remap table knows when
           a ticker symbol resolves to a different canonical name.)
        2. If both have network info → full contract-id comparison via
           TokenIdentityComparer.
        3. Otherwise → "symbol_only_ccxt_dedup", should_block=False (soft pass).
        """
        # Step 1: commonCurrencies cross-check.
        # ccxt remaps exchange-native symbols to unified names (e.g. "EDGE" →
        # "EdgeCoin" on one exchange vs "Edge Network" on another).  When the
        # canonical names differ, the symbols represent different tokens — block.
        cc_a = self._common_currencies.get(exchange_a, {})
        cc_b = self._common_currencies.get(exchange_b, {})
        # Only compare when at least one exchange has a remapping for this code
        # AND both have the table loaded (empty dict = not yet loaded).
        if cc_a or cc_b:
            canonical_a = cc_a.get(base_code, base_code)
            canonical_b = cc_b.get(base_code, base_code)
            if canonical_a.strip().lower() != canonical_b.strip().lower():
                return MatchResult(
                    base_code=base_code,
                    exchange_a=exchange_a,
                    exchange_b=exchange_b,
                    match_type="conflict",
                    shared_networks=[],
                    compared_ids={},
                    should_block=True,
                    notes=(
                        f"commonCurrencies name mismatch: "
                        f"{exchange_a}={canonical_a!r} vs {exchange_b}={canonical_b!r}. "
                        "Different tokens sharing the same ticker. BLOCK."
                    ),
                )

        # Step 2: full network / contract-id comparison.
        info_a = self._cache.get((exchange_a, base_code))
        info_b = self._cache.get((exchange_b, base_code))

        if info_a is None or info_b is None:
            missing = [
                ex for ex, info in ((exchange_a, info_a), (exchange_b, info_b))
                if info is None
            ]
            return MatchResult(
                base_code=base_code,
                exchange_a=exchange_a,
                exchange_b=exchange_b,
                match_type="symbol_only_ccxt_dedup",
                shared_networks=[],
                compared_ids={},
                should_block=False,
                notes=(
                    f"No currency network info cached for: {missing}. "
                    "Relying on ccxt commonCurrencies only. Manual review recommended."
                ),
            )

        return TokenIdentityComparer.compare(base_code, info_a, info_b)

    def build_report_rows(
        self,
        exchange_pairs: list[tuple[str, str]],
        base_codes: Sequence[str],
    ) -> list[dict[str, object]]:
        """Build a list of report rows for all (exchange_a, exchange_b, base_code) triples.

        Only includes base_codes that are present on BOTH exchanges in the cache.
        This is the audit artefact — not used in live trading logic.
        """
        rows: list[dict[str, object]] = []
        for ex_a, ex_b in exchange_pairs:
            for code in base_codes:
                if (ex_a, code) not in self._cache or (ex_b, code) not in self._cache:
                    continue
                result = self.compare(code, ex_a, ex_b)
                shared = result.shared_networks
                id_matches = all(
                    a == b
                    for a, b in result.compared_ids.values()
                    if a is not None and b is not None
                )
                rows.append({
                    "base": code,
                    "exchange_a": ex_a,
                    "exchange_b": ex_b,
                    "shared_networks": ",".join(shared) if shared else "—",
                    "ids_match": id_matches if shared else None,
                    "match_type": result.match_type,
                    "should_block": result.should_block,
                    "notes": result.notes,
                })
        return rows

    def cached_info(
        self,
        exchange_id: str,
        base_code: str,
    ) -> CurrencyNetworkInfo | None:
        return self._cache.get((exchange_id, base_code))
