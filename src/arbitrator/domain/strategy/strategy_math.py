from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

_ZERO = Decimal("0")
_HUNDRED = Decimal("100")
_TWO_DP = Decimal("0.01")


class StrategyMath:
    """Shared pure helpers for the strategy calculators.

    Centralizes the project conventions:
    - ``float -> Decimal`` via ``str`` to avoid binary artifacts (C6/FR-025).
    - profit decomposition ``gross - costs`` over a percent spread.
    - deposit ``Σ(notional_leg / leverage_leg)`` with spot legs at 1x (C2/FR-021).
    - net funding cost ``max(paid - received, 0)`` with per-leg direction (C3/FR-022).
    """

    @staticmethod
    def to_decimal(value: float | int | str | Decimal | None) -> Decimal | None:
        if value is None:
            return None
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))

    @staticmethod
    def gross_from_spread(spread_pct: Decimal, volume_usdt: Decimal) -> Decimal:
        return spread_pct / _HUNDRED * volume_usdt

    @staticmethod
    def fee_total(volume_usdt: Decimal, rates: tuple[Decimal, ...]) -> Decimal:
        total = _ZERO
        for rate in rates:
            total += volume_usdt * rate
        return total

    @staticmethod
    def deposit(legs: tuple[tuple[Decimal, int], ...]) -> Decimal:
        """``legs`` = tuples of (notional_usdt, leverage). Spot legs pass leverage=1."""
        total = _ZERO
        for notional, leverage in legs:
            lev = Decimal(leverage) if leverage > 0 else Decimal("1")
            total += notional / lev
        return total

    @staticmethod
    def percent_to_deposit(net_profit_usdt: Decimal, deposit_usdt: Decimal) -> Decimal | None:
        if deposit_usdt == _ZERO:
            return None
        return net_profit_usdt / deposit_usdt * _HUNDRED

    @staticmethod
    def funding_cost(legs: tuple[tuple[str, Decimal, Decimal], ...]) -> Decimal:
        """Net funding cost ``max(paid - received, 0)`` over the legs.

        Each leg = (side, rate, notional). A ``short`` leg pays funding when
        ``rate > 0`` (receives when ``rate < 0``); a ``long`` leg is the mirror.
        """
        paid = _ZERO
        received = _ZERO
        for side, rate, notional in legs:
            if rate == _ZERO:
                continue
            amount = abs(rate) * notional
            pays = (side == "short" and rate > _ZERO) or (side == "long" and rate < _ZERO)
            if pays:
                paid += amount
            else:
                received += amount
        diff = paid - received
        return diff if diff > _ZERO else _ZERO

    @staticmethod
    def costs_breakdown_label(*parts: Decimal) -> str:
        """Human-readable cost parts for UI, e.g. ``1.00 + 0.18``."""
        return " + ".join(
            format(part.quantize(_TWO_DP, rounding=ROUND_HALF_UP), "f") for part in parts
        )
