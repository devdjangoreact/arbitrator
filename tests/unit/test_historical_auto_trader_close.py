"""T040: Unit tests for HistoricalAutoTrader.close_all_positions."""
from __future__ import annotations

from unittest.mock import MagicMock

from arbitrator.application.trading.historical_auto_trader import HistoricalAutoTrader
from arbitrator.config.settings import Settings


def _make_trader() -> tuple[HistoricalAutoTrader, MagicMock, MagicMock]:
    settings = Settings(enabled_exchanges=["mexc", "bitget"])
    store = MagicMock()
    paper = MagicMock()
    market_cache = MagicMock()
    trader = HistoricalAutoTrader(
        settings=settings,
        store=store,
        paper_gateway=paper,
        market_cache=market_cache,
    )
    return trader, store, paper


def test_close_all_positions_removes_state() -> None:
    """close_all_positions cleans _open_pairs, _live_state, and spread rolling dicts."""
    trader, _store, paper = _make_trader()
    monitor_id = "BTC/USDT:USDT:mexc:bitget"

    trader._open_pairs = {"pair-1": ("BTC/USDT:USDT", "mexc", "bitget")}
    trader._live_state = {monitor_id: {"open_spread_current": 2.0}}
    trader._open_spread_min[monitor_id] = -1.0
    trader._open_spread_max[monitor_id] = 3.0
    trader._close_spread_min[monitor_id] = 0.0
    trader._close_spread_max[monitor_id] = 2.5

    # top_of_book_sync returns None — close proceeds with price=0
    trader._spread_resolver = MagicMock()
    trader._spread_resolver.top_of_book_sync.return_value = None

    # no open sell record → amount=0 → close_pair NOT called
    paper._store.load_all.return_value = []

    trader.close_all_positions(monitor_id)

    # Live state cleaned up
    assert monitor_id not in trader._live_state
    # Open pairs removed
    assert "pair-1" not in trader._open_pairs
    # Rolling dicts cleaned
    assert monitor_id not in trader._open_spread_min
    assert monitor_id not in trader._open_spread_max
    assert monitor_id not in trader._close_spread_min
    assert monitor_id not in trader._close_spread_max


def test_close_all_positions_calls_close_pair_when_amount_known() -> None:
    """close_all_positions calls close_pair when a sell record is found."""
    trader, _store, paper = _make_trader()
    monitor_id = "BTC/USDT:USDT:mexc:bitget"

    trader._open_pairs = {"pair-1": ("BTC/USDT:USDT", "mexc", "bitget")}

    book = MagicMock()
    book.ask = 100.5
    book.bid = 99.5
    trader._spread_resolver = MagicMock()
    trader._spread_resolver.top_of_book_sync.return_value = book

    sell_rec = MagicMock()
    sell_rec.pair_id = "pair-1"
    sell_rec.side = "sell"
    sell_rec.amount = 10.0
    paper._store.load_all.return_value = [sell_rec]

    trader.close_all_positions(monitor_id)

    paper.close_pair.assert_called_once()
    call_kwargs = paper.close_pair.call_args.kwargs
    assert call_kwargs["pair_id"] == "pair-1"
    assert call_kwargs["symbol"] == "BTC/USDT:USDT"
    assert call_kwargs["amount"] == 10.0


def test_close_all_positions_unknown_monitor_is_noop() -> None:
    """close_all_positions with an unregistered monitor_id is a no-op."""
    trader, _store, paper = _make_trader()
    trader._open_pairs = {}

    trader.close_all_positions("UNKNOWN:x:y")

    paper.close_pair.assert_not_called()
