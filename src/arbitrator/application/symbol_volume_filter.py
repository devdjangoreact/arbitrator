from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Literal

from arbitrator.domain.ticker import Ticker

SymbolVolumeStatus = Literal["eligible", "pending", "rejected"]


class SymbolVolumeFilter:
    """Decides which symbols qualify for display and streaming by 24h quote volume.

    A symbol is *eligible* when at least one enabled exchange reports
    ``quote_volume_24h >= threshold_usdt``. It is *rejected* when every exchange
    that lists the symbol has reported a volume and the maximum is below the
    threshold. Otherwise it remains *pending* (discovery still in progress).
    """

    @staticmethod
    def classify_symbol(
        symbol: str,
        snapshot: Mapping[tuple[str, str], Ticker],
        exchanges_for_symbol: Sequence[str],
        threshold_usdt: float,
    ) -> SymbolVolumeStatus:
        if threshold_usdt <= 0.0:
            return "eligible"

        reported_volumes: list[float] = []
        for exchange_id in exchanges_for_symbol:
            ticker = snapshot.get((exchange_id, symbol))
            if ticker is None or ticker.quote_volume_24h is None:
                continue
            reported_volumes.append(ticker.quote_volume_24h)

        if any(volume >= threshold_usdt for volume in reported_volumes):
            return "eligible"

        exchanges_with_volume = len(reported_volumes)
        if exchanges_with_volume >= len(exchanges_for_symbol):
            return "rejected"

        return "pending"

    @staticmethod
    def classify_all(
        symbols: Sequence[str],
        symbols_by_exchange: Mapping[str, Sequence[str]],
        snapshot: Mapping[tuple[str, str], Ticker],
        threshold_usdt: float,
    ) -> tuple[list[str], list[str], list[str]]:
        eligible: list[str] = []
        pending: list[str] = []
        rejected: list[str] = []

        exchange_sets = {
            symbol: SymbolVolumeFilter._exchanges_for_symbol(symbol, symbols_by_exchange)
            for symbol in symbols
        }

        for symbol in symbols:
            status = SymbolVolumeFilter.classify_symbol(
                symbol=symbol,
                snapshot=snapshot,
                exchanges_for_symbol=exchange_sets[symbol],
                threshold_usdt=threshold_usdt,
            )
            if status == "eligible":
                eligible.append(symbol)
            elif status == "pending":
                pending.append(symbol)
            else:
                rejected.append(symbol)

        return eligible, pending, rejected

    @staticmethod
    def filter_symbols_by_exchange(
        symbols_by_exchange: Mapping[str, Sequence[str]],
        allowed_symbols: Sequence[str],
    ) -> dict[str, list[str]]:
        allowed = set(allowed_symbols)
        return {
            exchange_id: sorted(symbol for symbol in exchange_symbols if symbol in allowed)
            for exchange_id, exchange_symbols in symbols_by_exchange.items()
        }

    @staticmethod
    def max_volume_usdt(
        symbol: str,
        snapshot: Mapping[tuple[str, str], Ticker],
        exchanges_for_symbol: Sequence[str],
    ) -> float | None:
        volumes: list[float] = []
        for exchange_id in exchanges_for_symbol:
            ticker = snapshot.get((exchange_id, symbol))
            if ticker is None or ticker.quote_volume_24h is None:
                continue
            volumes.append(ticker.quote_volume_24h)
        return max(volumes) if volumes else None

    @staticmethod
    def _exchanges_for_symbol(
        symbol: str,
        symbols_by_exchange: Mapping[str, Sequence[str]],
    ) -> list[str]:
        return sorted(
            exchange_id
            for exchange_id, exchange_symbols in symbols_by_exchange.items()
            if symbol in exchange_symbols
        )
