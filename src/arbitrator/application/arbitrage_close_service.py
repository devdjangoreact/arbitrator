from __future__ import annotations

import asyncio
from dataclasses import dataclass

from arbitrator.config.logger import logger
from arbitrator.domain.arbitrage_pair import ArbitragePair
from arbitrator.domain.position_leg import PositionLeg
from arbitrator.exchanges.factory import Factory


@dataclass(frozen=True, slots=True)
class CloseLegResult:
    leg: PositionLeg
    success: bool
    order_id: str | None
    message: str | None


@dataclass(frozen=True, slots=True)
class ClosePairResult:
    pair_id: str
    short: CloseLegResult
    long: CloseLegResult

    @property
    def all_success(self) -> bool:
        return self.short.success and self.long.success


class ArbitrageCloseService:
    """Closes arbitrage legs via reduce-only market orders."""

    def __init__(self, factory: Factory) -> None:
        self._factory = factory

    async def close_pair_partial(
        self,
        pair: ArbitragePair,
        close_percent: float,
    ) -> ClosePairResult:
        if close_percent <= 0.0 or close_percent > 100.0:
            short_result = CloseLegResult(
                leg=pair.short_leg,
                success=False,
                order_id=None,
                message="Invalid close percent",
            )
            return ClosePairResult(
                pair_id=pair.pair_id,
                short=short_result,
                long=CloseLegResult(
                    leg=pair.long_leg,
                    success=False,
                    order_id=None,
                    message="Invalid close percent",
                ),
            )
        factor = close_percent / 100.0
        short_partial = pair.short_leg.model_copy(
            update={"contracts": pair.short_leg.contracts * factor},
        )
        long_partial = pair.long_leg.model_copy(
            update={"contracts": pair.long_leg.contracts * factor},
        )
        short_result, long_result = await asyncio.gather(
            self._close_leg(short_partial),
            self._close_leg(long_partial),
        )
        return ClosePairResult(
            pair_id=pair.pair_id,
            short=short_result,
            long=long_result,
        )

    def close_pair_partial_sync(
        self,
        pair: ArbitragePair,
        close_percent: float,
    ) -> ClosePairResult:
        return asyncio.run(self.close_pair_partial(pair, close_percent))

    async def close_pair(self, pair: ArbitragePair) -> ClosePairResult:
        short_result, long_result = await asyncio.gather(
            self._close_leg(pair.short_leg),
            self._close_leg(pair.long_leg),
        )
        return ClosePairResult(
            pair_id=pair.pair_id,
            short=short_result,
            long=long_result,
        )

    async def close_leg(self, leg: PositionLeg) -> CloseLegResult:
        return await self._close_leg(leg)

    def close_pair_sync(self, pair: ArbitragePair) -> ClosePairResult:
        return asyncio.run(self.close_pair(pair))

    def close_leg_sync(self, leg: PositionLeg) -> CloseLegResult:
        return asyncio.run(self.close_leg(leg))

    async def _close_leg(self, leg: PositionLeg) -> CloseLegResult:
        named = self._factory.create(leg.exchange_id)
        try:
            order_id = await named.gateway.close_market_position(leg)
            return CloseLegResult(
                leg=leg,
                success=True,
                order_id=order_id or None,
                message=None,
            )
        except Exception:
            logger.exception(
                "close leg failed | exchange={} symbol={} side={}",
                leg.exchange_id,
                leg.symbol,
                leg.side,
            )
            return CloseLegResult(
                leg=leg,
                success=False,
                order_id=None,
                message="Close failed",
            )
        finally:
            await named.gateway.close()
