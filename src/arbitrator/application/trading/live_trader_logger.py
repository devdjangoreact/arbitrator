import time
from dataclasses import dataclass, field

from arbitrator.application.market_data.market_data_cache_memory import MarketDataCacheMemory
from arbitrator.application.trading.auto_trader_base import AutoTraderBase
from arbitrator.application.trading.excel_logger import ExcelTradesLogger
from arbitrator.config.logger import logger
from arbitrator.domain.market.order_book_level import OrderBookLevel

_CACHE_MAX_DESYNC_MS = 1000

class _OpenCheckStageTrace:
    passed: bool = False
    fail_reason: str = ""
    fresh_bid: float | None = None
    fresh_ask: float | None = None
    fresh_spread: float | None = None
    estimated_spread: float | None = None
    notional: float | None = None
    desync_ms: int | None = None
    strategy: str = ""
    strategy_threshold: float | None = None
    short_book: str = ""
    long_book: str = ""


@dataclass
class _OpenCandidateTrace:
    tick_ms: int
    rank: int
    symbol: str
    short_ex: str
    long_ex: str
    threshold_pct: float
    notional_floor: float
    cache_short_bid: float
    cache_long_ask: float
    cache_spread_pct: float
    stages: dict[str, str] = field(default_factory=dict)
    check1: _OpenCheckStageTrace | None = None
    check2: _OpenCheckStageTrace | None = None
    final_outcome: str = "—"
    final_detail: str = ""

    def mark_ok(self, stage: str) -> None:
        self.stages[stage] = "ok"

    def mark_skip(self, stage: str, detail: str = "") -> None:
        self.stages[stage] = f"skip:{detail}" if detail else "skip"

    def reject(self, stage: str, detail: str) -> None:
        self.stages[stage] = "FAIL"
        self.final_outcome = f"REJECT@{stage}"
        self.final_detail = detail


@dataclass(frozen=True, slots=True)
class _OpenCheckResult:
    fresh_bid: float
    fresh_ask: float
    fresh_spread: float
    estimated_spread: float
    notional_float: float
    strategy_kind: str
    strategy_open_threshold: float
    short_recv_ms: int
    long_recv_ms: int


class LiveTraderLogger:
    def __init__(self, market_cache: MarketDataCacheMemory, excel_logger: ExcelTradesLogger):
        self._cache = market_cache
        self._excel_logger = excel_logger

    @staticmethod
    def _format_book_levels(levels: tuple[OrderBookLevel, ...], n: int = 5) -> str:
        return ";".join(f"{lv.price}@{lv.size}" for lv in levels[:n])

    def _book_log_fields(self, exchange_id: str, symbol: str) -> str:
        book = self._cache.get_order_book(exchange_id, symbol)
        if book is None:
            return "book=missing"
        bids = self._format_book_levels(book.bids)
        asks = self._format_book_levels(book.asks)
        ts = book.timestamp_ms if book.timestamp_ms is not None else "n/a"
        return f"ts_ms={ts} bids=[{bids}] asks=[{asks}]"

    def _book_leg_summary(self, exchange_id: str, symbol: str) -> str:
        book = self._cache.get_order_book(exchange_id, symbol)
        if book is None:
            return f"{exchange_id}:no_book"
        top_bid = book.bids[0] if book.bids else None
        top_ask = book.asks[0] if book.asks else None
        bid_dep = (
            AutoTraderBase._side_depth_usdt(book.bids, price_limit_pct=0.004)
            if book.bids
            else 0.0
        )
        ask_dep = (
            AutoTraderBase._side_depth_usdt(book.asks, price_limit_pct=0.004)
            if book.asks
            else 0.0
        )
        bid_s = f"bid={top_bid.price}@{top_bid.size}" if top_bid else "bid=—"
        ask_s = f"ask={top_ask.price}@{top_ask.size}" if top_ask else "ask=—"
        return (
            f"{exchange_id} {bid_s} {ask_s}"
            f" bid_dep={bid_dep:.0f} ask_dep={ask_dep:.0f}USDT"
        )

    def stamp_check_trace(
        self,
        trace: _OpenCheckStageTrace | None,
        *,
        symbol: str,
        short_ex: str,
        long_ex: str,
        fail_reason: str = "",
        passed: bool = False,
        fresh_bid: float | None = None,
        fresh_ask: float | None = None,
        fresh_spread: float | None = None,
        estimated_spread: float | None = None,
        notional: float | None = None,
        desync_ms: int | None = None,
        strategy: str = "",
        strategy_threshold: float | None = None,
    ) -> None:
        if trace is None:
            return
        trace.passed = passed
        trace.fail_reason = fail_reason
        trace.fresh_bid = fresh_bid
        trace.fresh_ask = fresh_ask
        trace.fresh_spread = fresh_spread
        trace.estimated_spread = estimated_spread
        trace.notional = notional
        trace.desync_ms = desync_ms
        trace.strategy = strategy
        trace.strategy_threshold = strategy_threshold
        trace.short_book = self._book_leg_summary(short_ex, symbol)
        trace.long_book = self._book_leg_summary(long_ex, symbol)

    @staticmethod
    def _fmt_pct(value: float | None) -> str:
        return f"{value:6.3f}" if value is not None else "     —"

    def log_open_candidates_header(
        self,
        tick_ms: int,
        *,
        threshold_pct: float,
        notional_floor: float,
        open_count: int,
        max_pos: int,
        candidate_count: int,
    ) -> None:
        pass # Excel logger exclusively

    def log_open_candidate(self, trace: _OpenCandidateTrace) -> None:
        chk = trace.check2 if trace.check2 and not trace.check2.passed else trace.check1
        if chk is None and trace.check1 is not None:
            chk = trace.check1
        self._excel_logger.log_candidate(trace)

    def log_open_candidate_result(
        self, trace: _OpenCandidateTrace, status: str, message: str | None,
    ) -> None:
        trace.final_outcome = f"OPEN_{status.upper()}"
        trace.final_detail = message or ""
        self._excel_logger.log_candidate(trace)

    @staticmethod
    def _explain_check_fail(
        stage: str,
        reason: str,
        threshold_pct: float,
        chk: _OpenCheckStageTrace,
    ) -> str:
        fresh_s = f"{chk.fresh_spread:.3f}%" if chk.fresh_spread is not None else "n/a"
        est_s = f"{chk.estimated_spread:.3f}%" if chk.estimated_spread is not None else "n/a"
        bid_ask = ""
        if chk.fresh_bid is not None and chk.fresh_ask is not None:
            bid_ask = f" short_bid={chk.fresh_bid} long_ask={chk.fresh_ask}"
        notional_s = f" notional={chk.notional:.1f}USDT" if chk.notional else ""
        desync_s = f" desync={chk.desync_ms}ms" if chk.desync_ms is not None else ""
        if reason == "no_executable_bid_ask":
            return f"{stage}: немає executable bid/ask у свіжому стакані{bid_ask}"
        if reason == "cache_timestamp_missing":
            return f"{stage}: немає timestamp кешу стакана/котировки{desync_s}"
        if reason.startswith("cache_desync:"):
            return f"{stage}: розсинхрон кешу ніг {reason.split(':', 1)[-1]}ms > {_CACHE_MAX_DESYNC_MS}ms"
        if reason.startswith("spread_below_threshold:"):
            return (
                f"{stage}: свіжий спред {fresh_s} < поріг {threshold_pct}%"
                f"{bid_ask}{desync_s}"
            )
        if reason.startswith("anomaly_spread:"):
            return f"{stage}: аномальний спред {fresh_s} > max anomaly"
        if reason == "market_info_missing":
            return f"{stage}: не завантажено market_info біржі{notional_s}"
        if reason.startswith("estimated_fill_below_threshold:"):
            return (
                f"{stage}: estimated_fill {est_s} < поріг {threshold_pct}%"
                f" (fresh={fresh_s}{notional_s}) — стакан не тримає обсяг"
            )
        if reason == "estimated_fill_unavailable":
            return f"{stage}: не вистачає глибини стакана для notional{notional_s}"
        if reason.startswith("token_identity_conflict:"):
            return f"{stage}: різні токени на біржах — {reason}"
        if reason.startswith("insufficient_ask_depth:"):
            return f"{stage}: мало ask-глибини — {reason}"
        if reason.startswith("insufficient_bid_depth:"):
            return f"{stage}: мало bid-глибини — {reason}"
        if reason.startswith("no_order_book:"):
            return f"{stage}: немає стакана — {reason}"
        if reason.startswith("below_strategy_threshold:"):
            return f"{stage}: спред нижче порогу стратегії — {reason}"
        if reason.startswith("strategy_not_allowed:"):
            return f"{stage}: стратегія не в whitelist — {reason}"
        return f"{stage}: {reason}{bid_ask} fresh={fresh_s} est={est_s}{notional_s}{desync_s}"

    def explain_open_candidate(self, trace: _OpenCandidateTrace) -> str:
        if trace.final_outcome == "OPEN":
            chk = trace.check2 or trace.check1
            if chk is None:
                return "відправлено на виконання"
            return (
                f"відкриття: fresh={chk.fresh_spread:.3f}% est_fill={chk.estimated_spread:.3f}%"
                f" notional={chk.notional:.1f}USDT strategy={chk.strategy}"
            )
        if trace.final_outcome.startswith("OPEN_"):
            return trace.final_detail or trace.final_outcome
        if trace.final_outcome.startswith("REJECT@"):
            stage = trace.final_outcome.split("@", 1)[-1]
            if stage == "check1" and trace.check1 and trace.check1.fail_reason:
                return self._explain_check_fail(
                    stage, trace.check1.fail_reason, trace.threshold_pct, trace.check1,
                )
            if stage == "check2" and trace.check2 and trace.check2.fail_reason:
                return self._explain_check_fail(
                    stage, trace.check2.fail_reason, trace.threshold_pct, trace.check2,
                )
        if trace.final_detail:
            return trace.final_detail
        return ""

    def log_open_check(
        self,
        check_no: int,
        symbol: str,
        short_ex: str,
        long_ex: str,
        *,
        reason: str,
        candidate_spread: float | None = None,
        open_spread_pct: float | None = None,
        fresh_spread: float | None = None,
        fresh_bid: float | None = None,
        fresh_ask: float | None = None,
        estimated_spread: float | None = None,
        notional: float | None = None,
        strategy: str | None = None,
        strategy_threshold: float | None = None,
        short_recv_ms: int | None = None,
        long_recv_ms: int | None = None,
        desync_ms: int | None = None,
        detail: str | None = None,
    ) -> None:
        now_ms = int(time.time() * 1000)
        short_book = self._book_log_fields(short_ex, symbol)
        long_book = self._book_log_fields(long_ex, symbol)
        msg = (
            f"OPEN_CHECK{check_no} | ts_ms={now_ms} sym={symbol} short={short_ex} long={long_ex}"
            f" result={reason}"
        )
        if candidate_spread is not None:
            msg += f" candidate_spread={candidate_spread:.4f}%"
        if open_spread_pct is not None:
            msg += f" threshold={open_spread_pct}%"
        if fresh_spread is not None:
            msg += f" fresh_spread={fresh_spread:.4f}%"
        if fresh_bid is not None and fresh_ask is not None:
            msg += f" short_bid={fresh_bid} long_ask={fresh_ask}"
        if estimated_spread is not None:
            msg += f" estimated_fill={estimated_spread:.4f}%"
        if notional is not None:
            msg += f" notional={notional:.2f}"
        if strategy is not None:
            msg += f" strategy={strategy}"
        if strategy_threshold is not None:
            msg += f" strategy_threshold={strategy_threshold}%"
        if short_recv_ms is not None and long_recv_ms is not None:
            msg += f" short_recv_ms={short_recv_ms} long_recv_ms={long_recv_ms}"
        if desync_ms is not None:
            msg += f" desync_ms={desync_ms} max_desync_ms={_CACHE_MAX_DESYNC_MS}"
        if detail:
            msg += f" detail={detail}"
        msg += f" | short_book {short_book} | long_book {long_book}"
        log_fn = logger.info if reason == "pass" else logger.debug
        log_fn(msg)

    def log_close_decision(
        self,
        symbol: str,
        short_ex: str,
        long_ex: str,
        exit_spread: float,
        close_threshold: float,
        short_ask: float,
        long_bid: float,
        short_recv_ms: int | None,
        long_recv_ms: int | None,
        desync_ms: int,
        *,
        confirm_count: int,
    ) -> None:
        now_ms = int(time.time() * 1000)
        msg = (
            f"CLOSE_DECISION | ts_ms={now_ms} sym={symbol} short={short_ex} long={long_ex}"
            f" exit_spread={exit_spread:.4f}% threshold={close_threshold}%"
            f" short_ask={short_ask} long_bid={long_bid}"
            f" confirm={confirm_count}/2"
            f" short_recv_ms={short_recv_ms} long_recv_ms={long_recv_ms}"
            f" desync_ms={desync_ms} max_desync_ms={_CACHE_MAX_DESYNC_MS}"
            f" | short_book {self._book_log_fields(short_ex, symbol)}"
            f" | long_book {self._book_log_fields(long_ex, symbol)}"
        )
        logger.info(msg)
