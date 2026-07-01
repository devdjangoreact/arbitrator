from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from arbitrator.config.logger import logger
from arbitrator.config.settings import Settings
from arbitrator.domain.arb_marker_record import ArbMarkerRecord
from arbitrator.domain.arb_markers_repository import ArbMarkersRepository
from arbitrator.domain.spread_snapshot import SpreadSnapshot
from arbitrator.exchanges.factory import Factory


@dataclass(frozen=True, slots=True)
class OpenPairResult:
    pair_id: str
    symbol: str
    short_exchange_id: str
    long_exchange_id: str
    short_order_id: str | None
    long_order_id: str | None
    success: bool
    message: str | None


class ArbitrageOpenService:
    """Opens short+long arbitrage legs with shared marker ids."""

    def __init__(
        self,
        settings: Settings,
        factory: Factory,
        markers: ArbMarkersRepository,
    ) -> None:
        self._settings = settings
        self._factory = factory
        self._markers = markers

    async def open_from_spread(self, snapshot: SpreadSnapshot) -> OpenPairResult:
        return await self._open(
            snapshot,
            self._settings.arb_default_notional_usdt,
        )

    async def open_with_notional(
        self,
        snapshot: SpreadSnapshot,
        notional_usdt: float,
    ) -> OpenPairResult:
        if notional_usdt <= 0.0:
            return OpenPairResult(
                pair_id="",
                symbol=snapshot.symbol,
                short_exchange_id="",
                long_exchange_id="",
                short_order_id=None,
                long_order_id=None,
                success=False,
                message="Notional must be positive",
            )
        return await self._open(snapshot, notional_usdt)

    async def _open(self, snapshot: SpreadSnapshot, notional_usdt: float) -> OpenPairResult:
        if snapshot.high_exchange_id is None or snapshot.low_exchange_id is None:
            return OpenPairResult(
                pair_id="",
                symbol=snapshot.symbol,
                short_exchange_id="",
                long_exchange_id="",
                short_order_id=None,
                long_order_id=None,
                success=False,
                message="Insufficient price data",
            )
        high_price = snapshot.prices_by_exchange.get(snapshot.high_exchange_id)
        low_price = snapshot.prices_by_exchange.get(snapshot.low_exchange_id)
        if high_price is None or low_price is None or low_price <= 0.0:
            return OpenPairResult(
                pair_id="",
                symbol=snapshot.symbol,
                short_exchange_id=snapshot.high_exchange_id,
                long_exchange_id=snapshot.low_exchange_id,
                short_order_id=None,
                long_order_id=None,
                success=False,
                message="Invalid prices for sizing",
            )
        pair_id = uuid.uuid4().hex[:12]
        short_coid = f"ARB-{pair_id}-S"
        long_coid = f"ARB-{pair_id}-L"
        amount = notional_usdt / low_price
        short_gateway = self._factory.create(snapshot.high_exchange_id)
        long_gateway = self._factory.create(snapshot.low_exchange_id)
        short_order_id: str | None = None
        long_order_id: str | None = None
        try:
            short_order_id = await short_gateway.gateway.open_market_position(
                snapshot.symbol,
                "sell",
                amount,
                short_coid,
            )
            long_order_id = await long_gateway.gateway.open_market_position(
                snapshot.symbol,
                "buy",
                amount,
                long_coid,
            )
        except Exception:
            logger.exception(
                "open_from_spread failed | symbol={} pair_id={}",
                snapshot.symbol,
                pair_id,
            )
            return OpenPairResult(
                pair_id=pair_id,
                symbol=snapshot.symbol,
                short_exchange_id=snapshot.high_exchange_id,
                long_exchange_id=snapshot.low_exchange_id,
                short_order_id=short_order_id,
                long_order_id=long_order_id,
                success=False,
                message="Open failed",
            )
        finally:
            await short_gateway.gateway.close()
            await long_gateway.gateway.close()
        record = ArbMarkerRecord(
            pair_id=pair_id,
            symbol=snapshot.symbol,
            short_exchange_id=snapshot.high_exchange_id,
            long_exchange_id=snapshot.low_exchange_id,
            short_client_order_id=short_coid,
            long_client_order_id=long_coid,
            opened_at=datetime.now(UTC),
        )
        self._markers.append(record)
        logger.info(
            "Arbitrage pair opened | pair_id={} symbol={} short_ex={} long_ex={}",
            pair_id,
            snapshot.symbol,
            snapshot.high_exchange_id,
            snapshot.low_exchange_id,
        )
        return OpenPairResult(
            pair_id=pair_id,
            symbol=snapshot.symbol,
            short_exchange_id=snapshot.high_exchange_id,
            long_exchange_id=snapshot.low_exchange_id,
            short_order_id=short_order_id,
            long_order_id=long_order_id,
            success=True,
            message=None,
        )

    def open_with_notional_sync(
        self,
        snapshot: SpreadSnapshot,
        notional_usdt: float,
    ) -> OpenPairResult:
        return asyncio.run(self.open_with_notional(snapshot, notional_usdt))

    def open_from_spread_sync(self, snapshot: SpreadSnapshot) -> OpenPairResult:
        return asyncio.run(self.open_from_spread(snapshot))

    @staticmethod
    def _contracts_for_notional(notional_usdt: float, price: float) -> float:
        if price <= 0.0:
            return 0.0
        return notional_usdt / price
