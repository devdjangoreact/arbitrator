from __future__ import annotations

from datetime import UTC, datetime

from arbitrator.application.arb_monitor_lifecycle import ArbMonitorLifecycle
from arbitrator.application.arbitrage_monitor_worker import ArbitrageMonitorWorker
from arbitrator.domain.arbitrage_pair import ArbitragePair
from arbitrator.domain.position_leg import PositionLeg


def _pair(
    *,
    pair_id: str = "p1",
    symbol: str = "BTC/USDT:USDT",
    short_exchange_id: str = "mexc",
    long_exchange_id: str = "bitget",
) -> ArbitragePair:
    short = PositionLeg(
        exchange_id=short_exchange_id,
        display_name=short_exchange_id.upper(),
        symbol=symbol,
        side="short",
        contracts=1.0,
        contract_size=1.0,
        entry_price=100.0,
        mark_price=100.0,
        opened_at=datetime.now(UTC),
        unrealized_pnl=0.0,
        accrued_funding=0.0,
        opening_fee=0.0,
        estimated_close_fee=0.0,
        next_funding_at=None,
        arb_marker_id=pair_id,
        position_id="1",
    )
    long = short.model_copy(
        update={
            "exchange_id": long_exchange_id,
            "display_name": long_exchange_id.upper(),
            "side": "long",
        },
    )
    return ArbitragePair(
        pair_id=pair_id,
        symbol=symbol,
        short_leg=short,
        long_leg=long,
        combined_unrealized_pnl=0.0,
        combined_accrued_funding=0.0,
        projected_net_pnl=None,
        is_complete=True,
    )


class _AliveMonitorStub:
    def __init__(self, pairs: tuple[ArbitragePair, ...]) -> None:
        self._pairs = pairs

    def is_alive(self) -> bool:
        return True

    def monitored_signature(self) -> tuple[tuple[str, str, str, str], ...]:
        return ArbMonitorLifecycle.pair_signature(self._pairs)


class _DeadMonitorStub:
    def is_alive(self) -> bool:
        return False

    def monitored_signature(self) -> tuple[tuple[str, str, str, str], ...]:
        return ()


def test_pair_signature_is_order_independent() -> None:
    first = _pair(pair_id="a")
    second = _pair(pair_id="b", symbol="ETH/USDT:USDT")
    assert ArbMonitorLifecycle.pair_signature((first, second)) == ArbMonitorLifecycle.pair_signature(
        (second, first)
    )


def test_needs_new_worker_when_monitor_missing() -> None:
    pairs = (_pair(),)
    assert ArbMonitorLifecycle.needs_new_worker(None, pairs) is True


def test_needs_new_worker_when_monitor_dead() -> None:
    pairs = (_pair(),)
    assert ArbMonitorLifecycle.needs_new_worker(_DeadMonitorStub(), pairs) is True  # type: ignore[arg-type]


def test_needs_new_worker_when_pairs_unchanged() -> None:
    pairs = (_pair(),)
    worker = _AliveMonitorStub(pairs)
    assert ArbMonitorLifecycle.needs_new_worker(worker, pairs) is False  # type: ignore[arg-type]


def test_needs_new_worker_when_pair_id_changes() -> None:
    worker = _AliveMonitorStub((_pair(pair_id="p1"),))
    updated = (_pair(pair_id="p2"),)
    assert ArbMonitorLifecycle.needs_new_worker(worker, updated) is True  # type: ignore[arg-type]


def test_needs_new_worker_false_for_empty_pairs() -> None:
    worker = _AliveMonitorStub((_pair(),))
    assert ArbMonitorLifecycle.needs_new_worker(worker, ()) is False  # type: ignore[arg-type]


def test_monitor_worker_exposes_monitored_signature() -> None:
    class _CloseService:
        pass

    class _Factory:
        pass

    from arbitrator.config.settings import Settings

    pairs = (_pair(pair_id="live"),)
    worker = ArbitrageMonitorWorker(Settings(), _Factory(), _CloseService(), pairs)  # type: ignore[arg-type]
    assert worker.monitored_signature() == ArbMonitorLifecycle.pair_signature(pairs)
