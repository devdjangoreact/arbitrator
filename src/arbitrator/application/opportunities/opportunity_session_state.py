from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from arbitrator.config.settings import Settings
from arbitrator.domain.universe.symbol_market_info import SymbolMarketInfo
from arbitrator.presentation.dto.opportunity_dto import OpportunityParamsDto


@dataclass(frozen=True, slots=True)
class ExchangeMarketInfoPair:
    """Futures and optional spot market metadata for one exchange leg."""

    futures: SymbolMarketInfo | None
    spot: SymbolMarketInfo | None

_VOLUME_PCT_PRESETS: tuple[float, ...] = (10.0, 25.0, 50.0, 100.0)


class OpportunitySessionState:
    """Mutable WS-session trading params for one opportunity connection."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self.active_strategy_id = "futures_futures"
        self.target_volume_usdt = settings.opp_default_max_notional_usdt
        self.open_spread_threshold_pct = settings.arb_open_spread_threshold_pct
        self.close_spread_threshold_pct = settings.arb_close_spread_threshold_pct
        self.accumulate_volume_usdt = settings.opp_accumulate_step_usdt
        self.accumulate_volume_pct = 10.0
        self.close_volume_usdt = settings.opp_accumulate_step_usdt
        self.close_volume_pct = 10.0
        self.auto_accumulate_enabled = settings.arb_auto_open_enabled
        self.auto_close_enabled = settings.arb_auto_close_enabled
        self.leverage: dict[str, int] = {}
        self._market_info: dict[str, ExchangeMarketInfoPair] = {}

    def leverage_for(self, exchange_id: str) -> int:
        return self.leverage.get(exchange_id, self._settings.opp_default_leverage)

    def apply_params(self, payload: Mapping[str, object]) -> None:
        if "active_strategy_id" in payload:
            self.active_strategy_id = str(payload["active_strategy_id"])
        for key, attr in (
            ("target_volume_usdt", "target_volume_usdt"),
            ("open_spread_threshold_pct", "open_spread_threshold_pct"),
            ("close_spread_threshold_pct", "close_spread_threshold_pct"),
            ("accumulate_volume_usdt", "accumulate_volume_usdt"),
            ("accumulate_volume_pct", "accumulate_volume_pct"),
            ("close_volume_usdt", "close_volume_usdt"),
            ("close_volume_pct", "close_volume_pct"),
        ):
            if key in payload:
                value = payload[key]
                if isinstance(value, (int, float, str)):
                    setattr(self, attr, float(value))
        if "auto_accumulate_enabled" in payload:
            self.auto_accumulate_enabled = bool(payload["auto_accumulate_enabled"])
        if "auto_close_enabled" in payload:
            self.auto_close_enabled = bool(payload["auto_close_enabled"])

    def set_leverage(self, exchange_id: str, leverage: int) -> None:
        self.leverage[exchange_id] = leverage

    def set_market_info(
        self,
        exchange_id: str,
        *,
        futures: SymbolMarketInfo | None,
        spot: SymbolMarketInfo | None,
    ) -> None:
        self._market_info[exchange_id] = ExchangeMarketInfoPair(futures=futures, spot=spot)

    def market_info_for(self, exchange_id: str) -> ExchangeMarketInfoPair | None:
        return self._market_info.get(exchange_id)

    def to_dto(self, accumulated_volume_usdt: float) -> OpportunityParamsDto:
        return OpportunityParamsDto(
            active_strategy_id=self.active_strategy_id,
            accumulated_volume_usdt=round(accumulated_volume_usdt, 2),
            target_volume_usdt=round(self.target_volume_usdt, 2),
            open_spread_threshold_pct=round(self.open_spread_threshold_pct, 2),
            close_spread_threshold_pct=round(self.close_spread_threshold_pct, 2),
            accumulate_volume_usdt=round(self.accumulate_volume_usdt, 2),
            accumulate_volume_pct=round(self.accumulate_volume_pct, 2),
            close_volume_usdt=round(self.close_volume_usdt, 2),
            close_volume_pct=round(self.close_volume_pct, 2),
            auto_accumulate_enabled=self.auto_accumulate_enabled,
            auto_close_enabled=self.auto_close_enabled,
            volume_pct_presets=list(_VOLUME_PCT_PRESETS),
        )
