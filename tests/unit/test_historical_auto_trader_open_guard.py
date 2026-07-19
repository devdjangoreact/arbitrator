"""T050 – unit tests for HistoricalAutoTrader open-guard logic.

Guards / behaviours covered
  G1  open_count >= max_orders              → skip open
  G2  actual_notional >= order_size * 0.95  → skip (position full)
  G3  actual_notional > order_size * 1.2    → close_partial (live) / noop (paper)
  G4  order_size < exchange_min             → skip + warn
  G5  happy path – paper                    → open_pair called with full order_size_usdt
  G6  happy path – live                     → live.open called with full order_size_usdt
  G7  open_count display                    → set-based _open_pairs matching, both modes
  G8  _restore_open_pairs                   → per_order = order_size_usdt (never /max_orders)
"""
from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from arbitrator.application.trading.historical_auto_trader import HistoricalAutoTrader
from arbitrator.config.monitor_config_store import MonitorConfig, MonitorConfigStore
from arbitrator.config.settings import Settings
from arbitrator.domain.strategy.execution_outcome import ExecutionOutcome

SYM = "BTC/USDT:USDT"
SHORT_EX = "bitget"
LONG_EX = "gate"
ORDER_SIZE = 100.0


# ── small factories ──────────────────────────────────────────────────────────

def _config(**overrides: Any) -> MonitorConfig:
    defaults: dict[str, Any] = dict(
        symbol=SYM,
        short_exchange=SHORT_EX,
        long_exchange=LONG_EX,
        side="short",          # fixed → no auto-resolution in open loop
        open_spread_pct=1.0,
        close_spread_pct=0.1,
        order_size_usdt=ORDER_SIZE,
        max_orders=2,
        open_ticks=1,
        close_ticks=1,
        is_active=True,
        force_stop=False,
        total_stop=False,
    )
    defaults.update(overrides)
    return MonitorConfig(**defaults)


def _fake_outcome(status: str = "filled", pair_id: str = "live_pair_001") -> MagicMock:
    oc: MagicMock = MagicMock(spec=ExecutionOutcome)
    oc.status = MagicMock()
    oc.status.value = status
    oc.pair_id = pair_id
    return oc


def _spread_resolver(entry_pct: float = 2.0, exit_pct: float = 5.0) -> MagicMock:
    """Return entry spread well above threshold; exit well above (no close trigger)."""
    sr = MagicMock()
    entry_t = (None, None, entry_pct)
    exit_t = (None, None, exit_pct)
    sr.entry_spread_sync.return_value = entry_t
    sr.exit_spread_sync.return_value = exit_t
    sr.entry_spread = AsyncMock(return_value=entry_t)
    sr.exit_spread = AsyncMock(return_value=exit_t)
    book = MagicMock()
    book.bid = 100.0
    book.ask = 101.0
    sr.top_of_book_sync.return_value = book
    return sr


def _market_cache(
    min_short: float | None = None,
    min_long: float | None = None,
) -> MagicMock:
    mc = MagicMock()
    mc.get_funding.return_value = None
    mc.get_order_book.return_value = None
    mc.get_quote.return_value = None
    mc.get_usdt_balance.return_value = 1000.0

    def _info(exchange_id: str, symbol: str) -> MagicMock | None:
        val = min_short if exchange_id == SHORT_EX else min_long if exchange_id == LONG_EX else None
        if val is None:
            return None
        info = MagicMock()
        info.min_order_volume_usdt = val
        info.max_order_volume_usdt = None
        return info

    mc.get_market_info.side_effect = _info
    return mc


def _account_worker(actual_notional: float = 0.0) -> MagicMock:
    """Short leg where abs(contracts)*contract_size*entry_price == actual_notional."""
    leg = MagicMock()
    leg.exchange_id = SHORT_EX
    leg.symbol = SYM
    leg.side = "short"
    leg.contracts = actual_notional   # abs(n)*1.0*1.0 == actual_notional
    leg.contract_size = 1.0
    leg.entry_price = 1.0
    leg.unrealized_pnl = 0.0
    leg.accrued_funding = 0.0
    leg.opening_fee = 0.0
    leg.estimated_close_fee = 0.0
    aw = MagicMock()
    aw.read_positions.return_value = [leg]
    return aw


def _paper_gw() -> MagicMock:
    paper = MagicMock()
    sell_rec = MagicMock()
    sell_rec.pair_id = "paper_pair_001"
    sell_rec.side = "sell"
    sell_rec.symbol = SYM
    sell_rec.action = "open"
    paper._store.load_all.return_value = [sell_rec]
    return paper


def _live_gw(open_status: str = "filled") -> MagicMock:
    live = MagicMock()
    live.open = AsyncMock(return_value=_fake_outcome(open_status))
    live.open_parallel = AsyncMock(return_value=_fake_outcome(open_status))
    live.close_partial = AsyncMock(return_value=_fake_outcome())
    live.close_all = AsyncMock(return_value=_fake_outcome())
    return live


def _build(
    cfg: MonitorConfig,
    *,
    paper: MagicMock | None = None,
    live: MagicMock | None = None,
    aw: MagicMock | None = None,
    min_short: float | None = None,
    min_long: float | None = None,
) -> HistoricalAutoTrader:
    assert paper is not None or live is not None, "need at least one gateway"
    store = MagicMock(spec=MonitorConfigStore)
    store.get_all.return_value = [cfg]
    store.get.return_value = cfg
    trader = HistoricalAutoTrader(
        settings=Settings(enabled_exchanges=[SHORT_EX, LONG_EX]),
        store=store,
        market_cache=_market_cache(min_short=min_short, min_long=min_long),
        paper_gateway=paper,
        live_execution=live,
        account_worker=aw,
    )
    trader._spread_resolver = _spread_resolver()
    return trader


def _tick(trader: HistoricalAutoTrader) -> None:
    with patch.object(trader, "_log_card_tick"):
        asyncio.run(trader._tick())


# ── G1 – open_count guard ────────────────────────────────────────────────────

def test_g1_open_count_at_max_orders_blocks_open() -> None:
    """open_count == max_orders → open_pair never called."""
    cfg = _config(max_orders=2)
    paper = _paper_gw()
    trader = _build(cfg, paper=paper, aw=_account_worker(0.0))
    # seed two existing pairs for this monitor
    trader._open_pairs = {
        "p1": (SYM, SHORT_EX, LONG_EX),
        "p2": (SYM, SHORT_EX, LONG_EX),
    }

    _tick(trader)

    paper.open_pair.assert_not_called()


def test_g1_open_count_below_max_orders_allows_open() -> None:
    """open_count < max_orders → open_pair called."""
    cfg = _config(max_orders=3)
    paper = _paper_gw()
    trader = _build(cfg, paper=paper, aw=_account_worker(0.0))
    trader._open_pairs = {"p1": (SYM, SHORT_EX, LONG_EX)}   # count=1 < 3

    _tick(trader)

    paper.open_pair.assert_called_once()


# ── G2 – position-full guard ─────────────────────────────────────────────────

def test_g2_position_at_95pct_blocks_open() -> None:
    """actual_notional == 95 % of order_size → position full → skip."""
    cfg = _config(order_size_usdt=100.0, max_orders=5)
    paper = _paper_gw()
    trader = _build(cfg, paper=paper, aw=_account_worker(actual_notional=95.0))

    _tick(trader)

    paper.open_pair.assert_not_called()


def test_g2_position_above_95pct_blocks_open() -> None:
    """actual_notional > 95 % of order_size (but < 120 %) → skip, no overflow close."""
    cfg = _config(order_size_usdt=100.0, max_orders=5)
    live = _live_gw()
    trader = _build(cfg, live=live, aw=_account_worker(actual_notional=110.0))

    _tick(trader)

    live.open.assert_not_called()
    live.close_partial.assert_not_called()


def test_g2_position_below_95pct_allows_open() -> None:
    """actual_notional < 95 % → open proceeds."""
    cfg = _config(order_size_usdt=100.0, max_orders=5)
    paper = _paper_gw()
    trader = _build(cfg, paper=paper, aw=_account_worker(actual_notional=50.0))

    _tick(trader)

    paper.open_pair.assert_called_once()


# ── G3 – overflow guard ──────────────────────────────────────────────────────

def test_g3_overflow_live_calls_close_partial() -> None:
    """actual_notional > order_size * 1.2 → close_partial with correct percent."""
    cfg = _config(order_size_usdt=100.0, max_orders=5)
    live = _live_gw()
    actual = 130.0   # 130 > 100 * 1.2
    trader = _build(cfg, live=live, aw=_account_worker(actual_notional=actual))

    _tick(trader)

    live.close_partial.assert_called_once()
    kw = live.close_partial.call_args.kwargs
    assert kw["symbol"] == SYM
    assert kw["short_exchange_id"] == SHORT_EX
    assert kw["long_exchange_id"] == LONG_EX
    expected_pct = Decimal(str((actual - ORDER_SIZE) / actual * 100))
    assert kw["close_percent"] == expected_pct


def test_g3_overflow_live_does_not_open() -> None:
    """After overflow handling live.open must NOT be called (continues out of loop)."""
    cfg = _config(order_size_usdt=100.0, max_orders=5)
    live = _live_gw()
    trader = _build(cfg, live=live, aw=_account_worker(actual_notional=130.0))

    _tick(trader)

    live.open.assert_not_called()


def test_g3_overflow_paper_skips_without_close() -> None:
    """Paper mode has no close_partial; overflow just skips the open."""
    cfg = _config(order_size_usdt=100.0, max_orders=5)
    paper = _paper_gw()
    trader = _build(cfg, paper=paper, aw=_account_worker(actual_notional=130.0))

    _tick(trader)

    paper.open_pair.assert_not_called()
    # paper gateway has no close_partial – no AttributeError either
    assert not hasattr(paper, "close_partial") or not paper.close_partial.called


def test_g3_exactly_at_threshold_is_not_overflow() -> None:
    """actual_notional == order_size * 1.2 is NOT overflow (strictly greater required)."""
    cfg = _config(order_size_usdt=100.0, max_orders=5)
    live = _live_gw()
    trader = _build(cfg, live=live, aw=_account_worker(actual_notional=120.0))

    _tick(trader)

    live.close_partial.assert_not_called()
    # 120.0 >= 95.0 → position-full guard fires → still no open, but no close either
    live.open.assert_not_called()


# ── G4 – exchange minimum order size ────────────────────────────────────────

def test_g4_below_min_short_blocks_open() -> None:
    """order_size_usdt < min_order on short exchange → skip."""
    cfg = _config(order_size_usdt=50.0, max_orders=5)
    paper = _paper_gw()
    # short exchange requires minimum 100 USDT
    trader = _build(cfg, paper=paper, aw=_account_worker(0.0), min_short=100.0)

    _tick(trader)

    paper.open_pair.assert_not_called()


def test_g4_below_min_long_blocks_open() -> None:
    """order_size_usdt < min_order on long exchange → skip."""
    cfg = _config(order_size_usdt=50.0, max_orders=5)
    paper = _paper_gw()
    trader = _build(cfg, paper=paper, aw=_account_worker(0.0), min_long=75.0)

    _tick(trader)

    paper.open_pair.assert_not_called()


def test_g4_no_min_info_does_not_block() -> None:
    """No market info (None) → no minimum check → open proceeds."""
    cfg = _config(order_size_usdt=50.0, max_orders=5)
    paper = _paper_gw()
    trader = _build(cfg, paper=paper, aw=_account_worker(0.0))   # min_short/long = None

    _tick(trader)

    paper.open_pair.assert_called_once()


def test_g4_order_size_equal_to_min_is_allowed() -> None:
    """order_size_usdt == exchange_min is allowed (guard is strictly less-than)."""
    cfg = _config(order_size_usdt=100.0, max_orders=5)
    paper = _paper_gw()
    trader = _build(cfg, paper=paper, aw=_account_worker(0.0), min_short=100.0, min_long=100.0)

    _tick(trader)

    paper.open_pair.assert_called_once()


# ── G5 – happy path paper ────────────────────────────────────────────────────

def test_g5_paper_happy_path_calls_open_pair() -> None:
    """All guards clear → paper.open_pair called once with full order_size_usdt."""
    cfg = _config(order_size_usdt=200.0, max_orders=3)
    paper = _paper_gw()
    trader = _build(cfg, paper=paper, aw=_account_worker(0.0))

    _tick(trader)

    paper.open_pair.assert_called_once()
    kw = paper.open_pair.call_args.kwargs
    assert kw["symbol"] == SYM
    assert kw["short_exchange_id"] == SHORT_EX
    assert kw["long_exchange_id"] == LONG_EX
    assert kw["amount"] == 200.0   # full order_size, NOT 200/3


def test_g5_paper_happy_path_registers_pair_in_open_pairs() -> None:
    """After opening, the pair_id from the paper record appears in _open_pairs."""
    cfg = _config()
    paper = _paper_gw()
    trader = _build(cfg, paper=paper, aw=_account_worker(0.0))

    _tick(trader)

    assert "paper_pair_001" in trader._open_pairs
    assert trader._open_pairs["paper_pair_001"] == (SYM, SHORT_EX, LONG_EX)


# ── G6 – happy path live ─────────────────────────────────────────────────────

def test_g6_live_happy_path_calls_open_parallel_with_full_notional() -> None:
    """live.open_parallel receives notional_usdt = Decimal(order_size_usdt), not divided."""
    cfg = _config(order_size_usdt=300.0, max_orders=5)
    live = _live_gw()
    trader = _build(cfg, live=live, aw=_account_worker(0.0))

    _tick(trader)

    live.open_parallel.assert_called_once()
    kw = live.open_parallel.call_args.kwargs
    assert kw["symbol"] == SYM
    assert kw["short_exchange_id"] == SHORT_EX
    assert kw["long_exchange_id"] == LONG_EX
    assert kw["notional_usdt"] == Decimal("300.0")


def test_g6_live_successful_open_registers_pair() -> None:
    """Successful live.open_parallel → pair_id tracked in _open_pairs."""
    cfg = _config()
    live = _live_gw(open_status="filled")
    trader = _build(cfg, live=live, aw=_account_worker(0.0))

    _tick(trader)

    assert "live_pair_001" in trader._open_pairs


def test_g6_live_failed_open_does_not_register_pair() -> None:
    """Failed live.open_parallel (status='failed') → nothing added to _open_pairs."""
    cfg = _config()
    live = _live_gw(open_status="failed")
    trader = _build(cfg, live=live, aw=_account_worker(0.0))

    _tick(trader)

    assert len(trader._open_pairs) == 0


# ── G7 – open_count display ──────────────────────────────────────────────────

def test_g7_display_open_count_with_account_worker() -> None:
    """short_orders / long_orders in live_state reflect _open_pairs set-based count."""
    cfg = _config()
    paper = _paper_gw()
    trader = _build(cfg, paper=paper, aw=_account_worker(0.0))
    # 2 pairs for this monitor, 1 for another symbol (must not count)
    trader._open_pairs = {
        "p1": (SYM, SHORT_EX, LONG_EX),
        "p2": (SYM, SHORT_EX, LONG_EX),
        "other": ("ETH/USDT:USDT", SHORT_EX, LONG_EX),
    }

    _tick(trader)

    mid = cfg.id
    assert mid in trader._live_state
    state = trader._live_state[mid]
    assert state["short_orders"] == 2
    assert state["long_orders"] == 2


def test_g7_display_open_count_paper_no_account_worker() -> None:
    """Paper mode without account_worker: same set-based count from _open_pairs."""
    cfg = _config()
    paper = _paper_gw()
    # no account_worker passed → paper branch in display section
    trader = _build(cfg, paper=paper, aw=None)
    trader._open_pairs = {
        "p1": (SYM, SHORT_EX, LONG_EX),
        "p2": (SYM, SHORT_EX, LONG_EX),
    }

    _tick(trader)

    mid = cfg.id
    state = trader._live_state[mid]
    assert state["short_orders"] == 2
    assert state["long_orders"] == 2


def test_g7_display_ignores_pairs_from_other_exchanges() -> None:
    """Pairs sharing the symbol but different exchange set must not inflate open_count."""
    cfg = _config()
    paper = _paper_gw()
    trader = _build(cfg, paper=paper, aw=_account_worker(0.0))
    trader._open_pairs = {
        "p_mine": (SYM, SHORT_EX, LONG_EX),
        "p_other_ex": (SYM, "okx", "bybit"),   # different exchange set
    }

    _tick(trader)

    state = trader._live_state[cfg.id]
    assert state["short_orders"] == 1
    assert state["long_orders"] == 1


# ── G8 – _restore_open_pairs ────────────────────────────────────────────────

def test_g8_restore_uses_full_order_size_not_divided_by_max_orders() -> None:
    """n_pairs = round(best_notional / order_size_usdt) — never /max_orders."""
    # best_notional=300, order_size=100 → round(3.0)=3 pairs
    # wrong formula: order_size/max_orders = 100/3 → round(300/33.3) = 9 pairs
    cfg = _config(order_size_usdt=100.0, max_orders=3)
    live = _live_gw()
    aw = _account_worker(actual_notional=300.0)   # contracts=300 on SHORT_EX
    trader = _build(cfg, live=live, aw=aw)

    trader._restore_open_pairs()

    entries = [v for v in trader._open_pairs.values() if v[0] == SYM and {v[1], v[2]} == {SHORT_EX, LONG_EX}]
    assert len(entries) == 3


def test_g8_restore_fractional_notional_rounds_correctly() -> None:
    """best_notional / order_size = 1.5 → round → 2 pairs (Python banker's rounding)."""
    # round(150/100) = round(1.5) = 2 in Python 3
    cfg = _config(order_size_usdt=100.0, max_orders=5)
    live = _live_gw()
    aw = _account_worker(actual_notional=150.0)
    trader = _build(cfg, live=live, aw=aw)

    trader._restore_open_pairs()

    entries = [v for v in trader._open_pairs.values() if v[0] == SYM and {v[1], v[2]} == {SHORT_EX, LONG_EX}]
    assert len(entries) == 2


def test_g8_restore_zero_notional_creates_one_pair() -> None:
    """When no notional is found, fall back to max(len(s_legs), len(l_legs)) = 1."""
    cfg = _config(order_size_usdt=100.0)
    live = _live_gw()
    # contracts=0 → best_notional=0 → fallback path
    aw = _account_worker(actual_notional=0.0)
    trader = _build(cfg, live=live, aw=aw)

    # Account worker returns one short leg even with 0 notional
    # s_legs will be non-empty so the restore block runs; best_notional=0 → fallback
    trader._restore_open_pairs()

    entries = [v for v in trader._open_pairs.values() if v[0] == SYM and {v[1], v[2]} == {SHORT_EX, LONG_EX}]
    assert len(entries) == 1
