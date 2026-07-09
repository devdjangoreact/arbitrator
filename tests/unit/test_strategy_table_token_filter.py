"""Tests for StrategyTableService token-identity filtering and auto-exclusion.

All I/O is mocked — no file system, no exchange calls.
"""
from __future__ import annotations

from unittest.mock import MagicMock


from arbitrator.application.market_data.market_data_cache_memory import MarketDataCacheMemory
from arbitrator.application.strategies.strategy_table_service import StrategyTableService
from arbitrator.application.account.token_identity_service import TokenIdentityService
from arbitrator.config.settings import Settings
from arbitrator.domain.universe.symbol_exclusions_repository import SymbolExclusionsRepository
from arbitrator.domain.market.ticker import Ticker
from arbitrator.domain.universe.token_identity import CurrencyNetworkInfo, MatchResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SYM = "TLM/USDT:USDT"
SHORT_EX = "bitget"
LONG_EX = "mexc"


def _ticker(last: float) -> Ticker:
    return Ticker(
        symbol=SYM, last=last, bid=last * 0.999, ask=last * 1.001,
        high_24h=last, low_24h=last, base_volume_24h=1.0, quote_volume_24h=1_000_000.0,
        timestamp_ms=0,
    )


def _snapshot(short_price: float = 105.0, long_price: float = 100.0) -> dict[tuple[str, str], Ticker]:
    return {
        (SHORT_EX, SYM): _ticker(short_price),
        (LONG_EX, SYM): _ticker(long_price),
    }


def _blocked_result() -> MatchResult:
    return MatchResult(
        base_code="TLM",
        exchange_a=SHORT_EX,
        exchange_b=LONG_EX,
        match_type="conflict",
        shared_networks=["ERC20"],
        compared_ids={"ERC20": ("0xAAAA", "0xBBBB")},
        should_block=True,
        notes="Contract id mismatch on networks: ['ERC20']. BLOCK.",
    )


def _passing_result() -> MatchResult:
    return MatchResult(
        base_code="TLM",
        exchange_a=SHORT_EX,
        exchange_b=LONG_EX,
        match_type="symbol_only_ccxt_dedup",
        shared_networks=[],
        compared_ids={},
        should_block=False,
        notes="No shared networks.",
    )


def _make_service(
    token_identity: TokenIdentityService | None = None,
    exclusions_repo: SymbolExclusionsRepository | None = None,
) -> StrategyTableService:
    cache = MarketDataCacheMemory()
    assembler = MagicMock()
    engine = MagicMock()
    engine.compute.return_value = MagicMock()  # non-None → symbol ends up in tables
    settings = Settings()
    return StrategyTableService(
        cache=cache,
        assembler=assembler,
        engine=engine,
        settings=settings,
        token_identity=token_identity,
        exclusions_repo=exclusions_repo,
    )


# ---------------------------------------------------------------------------
# No token_identity injected — passthrough
# ---------------------------------------------------------------------------

def test_no_token_identity_symbol_appears_in_tables() -> None:
    svc = _make_service()
    tables = svc.refresh(_snapshot(), now_ms=0)
    assert SYM in tables


# ---------------------------------------------------------------------------
# token_identity injected, conflict → symbol filtered out
# ---------------------------------------------------------------------------

def test_conflict_symbol_excluded_from_tables() -> None:
    identity = MagicMock(spec=TokenIdentityService)
    identity.compare.return_value = _blocked_result()

    svc = _make_service(token_identity=identity)
    tables = svc.refresh(_snapshot(), now_ms=0)
    assert SYM not in tables


def test_conflict_calls_compare_with_correct_base_and_exchanges() -> None:
    identity = MagicMock(spec=TokenIdentityService)
    identity.compare.return_value = _blocked_result()

    svc = _make_service(token_identity=identity)
    svc.refresh(_snapshot(), now_ms=0)

    identity.compare.assert_called_once_with("TLM", SHORT_EX, LONG_EX)


def test_passing_symbol_remains_in_tables() -> None:
    identity = MagicMock(spec=TokenIdentityService)
    identity.compare.return_value = _passing_result()

    svc = _make_service(token_identity=identity)
    tables = svc.refresh(_snapshot(), now_ms=0)
    assert SYM in tables


# ---------------------------------------------------------------------------
# auto-exclusion: conflict writes to exclusions_repo
# ---------------------------------------------------------------------------

def test_conflict_adds_symbol_to_exclusions_repo() -> None:
    identity = MagicMock(spec=TokenIdentityService)
    identity.compare.return_value = _blocked_result()

    exclusions = MagicMock(spec=SymbolExclusionsRepository)
    svc = _make_service(token_identity=identity, exclusions_repo=exclusions)
    svc.refresh(_snapshot(), now_ms=0)

    exclusions.add.assert_called_once_with(SYM)


def test_passing_does_not_write_exclusions() -> None:
    identity = MagicMock(spec=TokenIdentityService)
    identity.compare.return_value = _passing_result()

    exclusions = MagicMock(spec=SymbolExclusionsRepository)
    svc = _make_service(token_identity=identity, exclusions_repo=exclusions)
    svc.refresh(_snapshot(), now_ms=0)

    exclusions.add.assert_not_called()


def test_no_exclusions_repo_injected_conflict_still_filters() -> None:
    """Filtering works even without exclusions_repo — no AttributeError."""
    identity = MagicMock(spec=TokenIdentityService)
    identity.compare.return_value = _blocked_result()

    svc = _make_service(token_identity=identity, exclusions_repo=None)
    tables = svc.refresh(_snapshot(), now_ms=0)
    assert SYM not in tables


# ---------------------------------------------------------------------------
# chain-label ids: "ETH" vs "ERC20" must NOT auto-exclude
# ---------------------------------------------------------------------------

def test_chain_label_mismatch_does_not_exclude() -> None:
    """Regression: 'ETH' vs 'ERC20' as chain-name ids must not block."""
    from arbitrator.domain.universe.token_identity import TokenIdentityComparer

    a = CurrencyNetworkInfo(exchange_id=SHORT_EX, base_code="TLM", network_ids={"ERC20": "ETH"})
    b = CurrencyNetworkInfo(exchange_id=LONG_EX,  base_code="TLM", network_ids={"ERC20": "ERC20"})
    result = TokenIdentityComparer.compare("TLM", a, b)
    assert result.should_block is False

    # Feed real result through service — must not filter
    identity = MagicMock(spec=TokenIdentityService)
    identity.compare.return_value = result
    exclusions = MagicMock(spec=SymbolExclusionsRepository)

    svc = _make_service(token_identity=identity, exclusions_repo=exclusions)
    tables = svc.refresh(_snapshot(), now_ms=0)

    assert SYM in tables
    exclusions.add.assert_not_called()


# ---------------------------------------------------------------------------
# conflict writes to exclusions only once (idempotent across ticks)
# ---------------------------------------------------------------------------

def test_conflict_exclusion_written_on_price_change_only() -> None:
    """add() fires when price changes (symbol enters changed set); same price → no recompute."""
    identity = MagicMock(spec=TokenIdentityService)
    identity.compare.return_value = _blocked_result()
    exclusions = MagicMock(spec=SymbolExclusionsRepository)

    svc = _make_service(token_identity=identity, exclusions_repo=exclusions)
    svc.refresh(_snapshot(short_price=105.0), now_ms=0)   # first tick — price seen → add()
    svc.refresh(_snapshot(short_price=105.0), now_ms=1)   # same price → changed={} → no recompute
    assert exclusions.add.call_count == 1

    svc.refresh(_snapshot(short_price=106.0), now_ms=2)   # price changed → recompute → add() again
    assert exclusions.add.call_count == 2
