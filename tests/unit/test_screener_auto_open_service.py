from __future__ import annotations

from arbitrator.application.arbitrage_open_service import OpenPairResult
from arbitrator.application.screener_auto_open_service import ScreenerAutoOpenService
from arbitrator.application.spread_evaluator import SpreadEvaluator
from arbitrator.config.settings import Settings
from arbitrator.domain.named_exchange import NamedExchange
from arbitrator.domain.ticker import Ticker
from tests.conftest import MockGateway


class _RecordingOpenService:
    def __init__(self, *, success: bool) -> None:
        self._success = success
        self.calls: list[str] = []

    def open_from_spread_sync(self, snapshot: object) -> OpenPairResult:
        symbol = getattr(snapshot, "symbol", "")
        self.calls.append(str(symbol))
        return OpenPairResult(
            pair_id="pair-1" if self._success else "",
            symbol=str(symbol),
            short_exchange_id="mexc",
            long_exchange_id="bitget",
            short_order_id="s1" if self._success else None,
            long_order_id="l1" if self._success else None,
            success=self._success,
            message=None if self._success else "rejected",
        )


def _exchanges() -> list[NamedExchange]:
    gateway = MockGateway()
    return [
        NamedExchange(exchange_id="mexc", display_name="MEXC", gateway=gateway),
        NamedExchange(exchange_id="bitget", display_name="Bitget", gateway=gateway),
    ]


def _snapshot() -> dict[tuple[str, str], Ticker]:
    symbol = "BTC/USDT:USDT"
    return {
        ("mexc", symbol): Ticker(
            symbol=symbol,
            last=105.0,
            bid=105.0,
            ask=105.1,
            high_24h=110.0,
            low_24h=100.0,
            base_volume_24h=1.0,
            quote_volume_24h=1_000_000.0,
            timestamp_ms=0,
        ),
        ("bitget", symbol): Ticker(
            symbol=symbol,
            last=100.0,
            bid=99.9,
            ask=100.0,
            high_24h=101.0,
            low_24h=99.0,
            base_volume_24h=1.0,
            quote_volume_24h=1_000_000.0,
            timestamp_ms=0,
        ),
    }


def test_auto_open_skips_when_trading_not_ready() -> None:
    settings = Settings(arb_auto_open_enabled=True, arb_open_spread_threshold_pct=4.0)
    open_service = _RecordingOpenService(success=True)
    service = ScreenerAutoOpenService(settings, open_service, SpreadEvaluator(settings))  # type: ignore[arg-type]
    result = service.run_pass(
        _snapshot(),
        ["BTC/USDT:USDT"],
        _exchanges(),
        set(),
        trading_ready=False,
    )
    assert result == set()
    assert open_service.calls == []


def test_auto_open_skips_when_disabled() -> None:
    settings = Settings(arb_auto_open_enabled=False, arb_open_spread_threshold_pct=4.0)
    open_service = _RecordingOpenService(success=True)
    service = ScreenerAutoOpenService(settings, open_service, SpreadEvaluator(settings))  # type: ignore[arg-type]
    result = service.run_pass(
        _snapshot(),
        ["BTC/USDT:USDT"],
        _exchanges(),
        set(),
        trading_ready=True,
    )
    assert result == set()
    assert open_service.calls == []


def test_auto_open_records_symbol_only_on_success() -> None:
    settings = Settings(arb_auto_open_enabled=True, arb_open_spread_threshold_pct=4.0)
    open_service = _RecordingOpenService(success=True)
    service = ScreenerAutoOpenService(settings, open_service, SpreadEvaluator(settings))  # type: ignore[arg-type]
    symbol = "BTC/USDT:USDT"
    result = service.run_pass(
        _snapshot(),
        [symbol],
        _exchanges(),
        set(),
        trading_ready=True,
    )
    assert result == {symbol}
    assert open_service.calls == [symbol]


def test_auto_open_does_not_record_symbol_on_failure() -> None:
    settings = Settings(arb_auto_open_enabled=True, arb_open_spread_threshold_pct=4.0)
    open_service = _RecordingOpenService(success=False)
    service = ScreenerAutoOpenService(settings, open_service, SpreadEvaluator(settings))  # type: ignore[arg-type]
    symbol = "BTC/USDT:USDT"
    result = service.run_pass(
        _snapshot(),
        [symbol],
        _exchanges(),
        set(),
        trading_ready=True,
    )
    assert result == set()
    assert open_service.calls == [symbol]


def test_auto_open_skips_already_opened_symbol() -> None:
    settings = Settings(arb_auto_open_enabled=True, arb_open_spread_threshold_pct=4.0)
    open_service = _RecordingOpenService(success=True)
    service = ScreenerAutoOpenService(settings, open_service, SpreadEvaluator(settings))  # type: ignore[arg-type]
    symbol = "BTC/USDT:USDT"
    result = service.run_pass(
        _snapshot(),
        [symbol],
        _exchanges(),
        {symbol},
        trading_ready=True,
    )
    assert result == {symbol}
    assert open_service.calls == []
