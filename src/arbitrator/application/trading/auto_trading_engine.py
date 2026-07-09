from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from arbitrator.application.opportunities.opportunity_session_state import OpportunitySessionState
from arbitrator.application.opportunities.opportunity_stream_worker import OpportunityStreamState


@dataclass(frozen=True, slots=True)
class AutoTradeSignal:
    action: Literal["accumulate", "close_all"]
    volume_usdt: float
    spread_pct: float


class AutoTradingEngine:
    """Pure spread-logic for auto-accumulate and auto-close decisions.

    Uses best bid/ask from the live order book — never mid-price — so
    the spread reflects the actual cost of crossing the book.

    Open:  short sells at short-exchange best bid,
           long  buys  at long-exchange  best ask.
           Entry spread = (short_bid - long_ask) / long_ask * 100.

    Close: buy back short at short-exchange best ask,
           sell long position at long-exchange best bid.
           Exit spread  = (short_ask - long_bid) / long_bid * 100.
    """

    @staticmethod
    def check_accumulate(
        *,
        session: OpportunitySessionState,
        stream_state: OpportunityStreamState,
        short_exchange_id: str,
        long_exchange_id: str,
        accumulated_usdt: float,
    ) -> AutoTradeSignal | None:
        if not session.auto_accumulate_enabled:
            return None
        if accumulated_usdt >= session.target_volume_usdt:
            return None
        short_bid = AutoTradingEngine._best_bid(stream_state, short_exchange_id)
        long_ask = AutoTradingEngine._best_ask(stream_state, long_exchange_id)
        if short_bid is None or long_ask is None or long_ask <= 0.0:
            return None
        spread = (short_bid - long_ask) / long_ask * 100.0
        if spread < session.open_spread_threshold_pct:
            return None
        remaining = session.target_volume_usdt - accumulated_usdt
        volume_usdt = min(session.accumulate_volume_usdt, remaining)
        if volume_usdt <= 0.0:
            return None
        return AutoTradeSignal(
            action="accumulate",
            volume_usdt=round(volume_usdt, 4),
            spread_pct=round(spread, 4),
        )

    @staticmethod
    def check_close(
        *,
        session: OpportunitySessionState,
        stream_state: OpportunityStreamState,
        short_exchange_id: str,
        long_exchange_id: str,
        accumulated_usdt: float,
    ) -> AutoTradeSignal | None:
        if not session.auto_close_enabled:
            return None
        if accumulated_usdt <= 0.0:
            return None
        short_ask = AutoTradingEngine._best_ask(stream_state, short_exchange_id)
        long_bid = AutoTradingEngine._best_bid(stream_state, long_exchange_id)
        if short_ask is None or long_bid is None or long_bid <= 0.0:
            return None
        spread = (short_ask - long_bid) / long_bid * 100.0
        if spread > session.close_spread_threshold_pct:
            return None
        return AutoTradeSignal(
            action="close_all",
            volume_usdt=round(accumulated_usdt, 4),
            spread_pct=round(spread, 4),
        )

    @staticmethod
    def _best_bid(stream_state: OpportunityStreamState, exchange_id: str) -> float | None:
        book = stream_state.books.get(f"{exchange_id}:futures")
        if book is None or not book.bids:
            return None
        return max(level.price for level in book.bids)

    @staticmethod
    def _best_ask(stream_state: OpportunityStreamState, exchange_id: str) -> float | None:
        book = stream_state.books.get(f"{exchange_id}:futures")
        if book is None or not book.asks:
            return None
        return min(level.price for level in book.asks)
