from __future__ import annotations

from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict


class SymbolMarketInfo(BaseModel):
    """Per-exchange market identity and order size limits for one swap symbol."""

    model_config = ConfigDict(frozen=True)

    unified_symbol: str
    base_asset: str
    native_market_id: str | None
    min_order_volume_usdt: float | None
    max_order_volume_usdt: float | None


class SymbolMarketInfoParser:
    """Builds ``SymbolMarketInfo`` from a ccxt ``load_markets`` entry."""

    @staticmethod
    def from_ccxt_market(
        market: Mapping[str, object],
        *,
        mark_price: float | None = None,
    ) -> SymbolMarketInfo | None:
        unified = market.get("symbol")
        base = market.get("base")
        if not isinstance(unified, str) or not isinstance(base, str):
            return None
        native_raw = market.get("id")
        native_id = str(native_raw) if native_raw is not None else None
        min_usdt, max_usdt = SymbolMarketInfoParser._volume_limits_usdt(market, mark_price)
        return SymbolMarketInfo(
            unified_symbol=unified,
            base_asset=base,
            native_market_id=native_id,
            min_order_volume_usdt=min_usdt,
            max_order_volume_usdt=max_usdt,
        )

    @staticmethod
    def _volume_limits_usdt(
        market: Mapping[str, object],
        mark_price: float | None,
    ) -> tuple[float | None, float | None]:
        limits = market.get("limits")
        if not isinstance(limits, dict):
            return None, None

        min_usdt = SymbolMarketInfoParser._limit_side(limits, "cost", "min")
        max_usdt = SymbolMarketInfoParser._limit_side(limits, "cost", "max")

        if min_usdt is not None and max_usdt is not None:
            return min_usdt, max_usdt

        amount_limits = limits.get("amount")
        if not isinstance(amount_limits, dict):
            return min_usdt, max_usdt
        if mark_price is None or mark_price <= 0.0:
            return min_usdt, max_usdt

        contract_size = SymbolMarketInfoParser._as_float(market.get("contractSize")) or 1.0
        min_amount = SymbolMarketInfoParser._as_float(amount_limits.get("min"))
        max_amount = SymbolMarketInfoParser._as_float(amount_limits.get("max"))
        if min_usdt is None and min_amount is not None:
            min_usdt = min_amount * contract_size * mark_price
        if max_usdt is None and max_amount is not None:
            max_usdt = max_amount * contract_size * mark_price
        return min_usdt, max_usdt

    @staticmethod
    def _limit_side(limits: Mapping[str, object], group: str, side: str) -> float | None:
        bucket = limits.get(group)
        if not isinstance(bucket, dict):
            return None
        return SymbolMarketInfoParser._as_float(bucket.get(side))

    @staticmethod
    def _as_float(value: object) -> float | None:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return None
            try:
                return float(stripped)
            except ValueError:
                return None
        return None
