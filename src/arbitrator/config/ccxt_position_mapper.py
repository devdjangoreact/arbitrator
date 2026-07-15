from __future__ import annotations

from datetime import UTC, datetime

from arbitrator.domain.account.closed_position_leg import ClosedPositionLeg
from arbitrator.domain.account.position_leg import PositionLeg


class CcxtPositionMapper:
    """Maps ccxt unified position/trade dicts into domain models."""

    @staticmethod
    def parse_arb_marker_id(raw: object) -> str | None:
        if not isinstance(raw, str) or not raw.startswith("ARB-"):
            return None
        parts = raw.split("-")
        if len(parts) >= 3:
            return parts[1]
        return None

    @staticmethod
    def map_open_position(
        payload: object,
        *,
        exchange_id: str,
        display_name: str,
        accrued_funding: float | None = None,
        opening_fee: float | None = None,
        estimated_close_fee: float | None = None,
    ) -> PositionLeg | None:
        if not isinstance(payload, dict):
            return None
        symbol = payload.get("symbol")
        side = payload.get("side")
        contracts = CcxtPositionMapper._as_float(payload.get("contracts"))
        if not isinstance(symbol, str) or side not in ("long", "short"):
            return None
        if contracts is None or contracts == 0.0:
            return None
        entry = CcxtPositionMapper._as_float(payload.get("entryPrice"))
        if entry is None:
            return None
        contract_size = CcxtPositionMapper._as_float(payload.get("contractSize")) or 1.0
        opened_at = CcxtPositionMapper._parse_datetime(payload)
        marker = CcxtPositionMapper._extract_marker(payload)
        position_id = CcxtPositionMapper._as_str(payload.get("id"))
        next_funding = CcxtPositionMapper._parse_next_funding(payload)
        return PositionLeg(
            exchange_id=exchange_id,
            display_name=display_name,
            symbol=symbol,
            side=side,
            contracts=abs(contracts),
            contract_size=contract_size,
            entry_price=entry,
            mark_price=CcxtPositionMapper._as_float(payload.get("markPrice")),
            opened_at=opened_at,
            unrealized_pnl=CcxtPositionMapper._as_float(payload.get("unrealizedPnl")),
            accrued_funding=accrued_funding,
            opening_fee=opening_fee,
            estimated_close_fee=estimated_close_fee,
            next_funding_at=next_funding,
            arb_marker_id=marker,
            position_id=position_id,
        )

    @staticmethod
    def map_closed_position(
        payload: object,
        *,
        exchange_id: str,
        display_name: str,
        commission: float | None = None,
        funding: float | None = None,
        contract_size: float | None = None,
    ) -> ClosedPositionLeg | None:
        if not isinstance(payload, dict):
            return None
        if not CcxtPositionMapper._is_executed_closure(payload):
            return None
        symbol = payload.get("symbol")
        side = payload.get("side")
        if not isinstance(symbol, str) or side not in ("long", "short"):
            return None
        closed_at = CcxtPositionMapper._parse_closed_at(payload)
        opened_at = CcxtPositionMapper._parse_opened_at(payload)
        realized = CcxtPositionMapper._extract_realized_pnl(payload)
        effective_commission = commission
        if effective_commission is None:
            effective_commission = CcxtPositionMapper._extract_commission(payload)
        effective_funding = CcxtPositionMapper._extract_funding(payload)
        if effective_funding is None:
            effective_funding = funding
        contracts = CcxtPositionMapper._extract_closed_contracts(payload)
        entry_price = CcxtPositionMapper._extract_entry_price(payload)
        exit_price = CcxtPositionMapper._extract_exit_price(payload)
        size = contract_size
        if size is None or size <= 0.0:
            size = CcxtPositionMapper._as_float(payload.get("contractSize")) or 1.0
        position_id = CcxtPositionMapper._as_str(payload.get("id"))
        if position_id is None:
            info = payload.get("info")
            if isinstance(info, dict):
                position_id = CcxtPositionMapper._as_str(info.get("positionId"))
        return ClosedPositionLeg(
            exchange_id=exchange_id,
            display_name=display_name,
            symbol=symbol,
            side=side,
            realized_pnl=realized,
            commission=effective_commission,
            funding=effective_funding,
            contracts=contracts,
            contract_size=size,
            entry_price=entry_price,
            exit_price=exit_price,
            opened_at=opened_at,
            closed_at=closed_at,
            arb_marker_id=CcxtPositionMapper._extract_marker(payload),
            position_id=position_id,
        )

    _CANCELLED_STATUS_TOKENS: frozenset[str] = frozenset(
        {
            "cancelled",
            "canceled",
            "cancel",
            "expired",
            "rejected",
        }
    )
    _CLOSED_STATUS_TOKENS: frozenset[str] = frozenset(
        {
            "closed",
            "close",
            "filled",
            "done",
        }
    )
    _CLOSE_VOLUME_INFO_KEYS: tuple[str, ...] = (
        "closeVol",
        "closeTotalPos",
        "closedSize",
        "closeAmount",
    )
    _STATUS_INFO_KEYS: tuple[str, ...] = (
        "positionShowStatus",
        "status",
        "orderStatus",
        "state",
        "positionStatus",
    )

    @staticmethod
    def _is_executed_closure(payload: dict[str, object]) -> bool:
        """True for filled/closed positions; false for canceled or still-open rows."""
        if CcxtPositionMapper._payload_has_cancelled_status(payload):
            return False
        info = payload.get("info")
        # Gate position history: has realizedPnl and short_price/long_price — always closed.
        if isinstance(info, dict) and (
            info.get("short_price") is not None or info.get("long_price") is not None
        ):
            return True
        contracts = CcxtPositionMapper._as_float(payload.get("contracts"))
        if contracts is not None and contracts > 0.0:
            # Position history endpoints may report the traded size in contracts
            # while being closed. Only reject if there's no realizedPnl indicating closure.
            rpnl = CcxtPositionMapper._as_float(payload.get("realizedPnl"))
            last_update = payload.get("lastUpdateTimestamp")
            return bool(rpnl is not None and rpnl != 0.0 and last_update is not None)
        if isinstance(info, dict):
            hold_vol = CcxtPositionMapper._as_float(info.get("holdVol"))
            if hold_vol is not None and hold_vol > 0.0:
                return False
            if CcxtPositionMapper._dict_has_close_volume(info):
                return True
            if CcxtPositionMapper._dict_has_closed_status(info):
                return True
            state = info.get("state")
            if state is not None and str(state) == "3":
                return True
        if CcxtPositionMapper._dict_has_close_volume(payload):
            return True
        return bool(CcxtPositionMapper._dict_has_closed_status(payload))

    @staticmethod
    def _extract_realized_pnl(payload: dict[str, object]) -> float | None:
        for key in ("realizedPnl", "realisedPnl"):
            value = CcxtPositionMapper._as_float(payload.get(key))
            if value is not None:
                return value
        info = payload.get("info")
        if isinstance(info, dict):
            for key in (
                "realizedPnl",
                "realised",
                "realisedPnl",
                "closeProfitLoss",
                "cumRealisedPnl",
                "netProfit",
            ):
                value = CcxtPositionMapper._as_float(info.get(key))
                if value is not None:
                    return value
        return None

    @staticmethod
    def _extract_commission(payload: dict[str, object]) -> float | None:
        for key in ("fee", "commission"):
            raw = payload.get(key)
            if isinstance(raw, dict):
                amount = CcxtPositionMapper._as_float(raw.get("cost"))
                if amount is not None:
                    return abs(amount)
            amount = CcxtPositionMapper._as_float(raw)
            if amount is not None:
                return abs(amount)
        info = payload.get("info")
        if isinstance(info, dict):
            open_fee = None
            close_fee = None
            for key in ("openFeeTotal", "openFee", "open_fee"):
                open_fee = CcxtPositionMapper._as_float(info.get(key))
                if open_fee is not None:
                    break
            for key in ("closeFeeTotal", "closeFee", "close_fee"):
                close_fee = CcxtPositionMapper._as_float(info.get(key))
                if close_fee is not None:
                    break
            if open_fee is not None or close_fee is not None:
                return abs(open_fee or 0.0) + abs(close_fee or 0.0)
            for key in ("fee", "commission", "pnl_fee"):
                amount = CcxtPositionMapper._as_float(info.get(key))
                if amount is not None:
                    return abs(amount)
        return None

    @staticmethod
    def _extract_funding(payload: dict[str, object]) -> float | None:
        for key in ("funding", "totalFunding"):
            value = CcxtPositionMapper._as_float(payload.get(key))
            if value is not None:
                return value
        info = payload.get("info")
        if isinstance(info, dict):
            for key in ("holdFee", "totalFunding", "fundingFee", "pnl_fund"):
                value = CcxtPositionMapper._as_float(info.get(key))
                if value is not None:
                    return value
        return None

    @staticmethod
    def _extract_closed_contracts(payload: dict[str, object]) -> float | None:
        info = payload.get("info")
        if isinstance(info, dict):
            for key in CcxtPositionMapper._CLOSE_VOLUME_INFO_KEYS:
                volume = CcxtPositionMapper._as_float(info.get(key))
                if volume is not None and volume > 0.0:
                    return volume
            # Gate position history: accum_size or max_size
            for key in ("accum_size", "max_size"):
                volume = CcxtPositionMapper._as_float(info.get(key))
                if volume is not None and volume > 0.0:
                    return volume
        for key in ("closeVol", "closeTotalPos", "closedSize"):
            volume = CcxtPositionMapper._as_float(payload.get(key))
            if volume is not None and volume > 0.0:
                return volume
        # Fallback: use contracts field (position history may put closed size here)
        contracts = CcxtPositionMapper._as_float(payload.get("contracts"))
        if contracts is not None and contracts > 0.0:
            return contracts
        return None

    @staticmethod
    def _extract_entry_price(payload: dict[str, object]) -> float | None:
        for key in ("entryPrice", "openPrice"):
            value = CcxtPositionMapper._as_float(payload.get(key))
            if value is not None:
                return value
        info = payload.get("info")
        if isinstance(info, dict):
            for key in ("openAvgPrice", "openAvgPriceFullyScale", "newOpenAvgPrice"):
                value = CcxtPositionMapper._as_float(info.get(key))
                if value is not None:
                    return value
            # Gate position history: long_price=entry for long, short_price=entry for short
            side = payload.get("side")
            entry_key = "long_price" if side == "long" else "short_price"
            value = CcxtPositionMapper._as_float(info.get(entry_key))
            if value is not None:
                return value
        return None

    @staticmethod
    def _extract_exit_price(payload: dict[str, object]) -> float | None:
        for key in ("closePrice", "lastPrice"):
            value = CcxtPositionMapper._as_float(payload.get(key))
            if value is not None:
                return value
        info = payload.get("info")
        if isinstance(info, dict):
            for key in ("closeAvgPrice", "closeAvgPriceFullyScale", "newCloseAvgPrice"):
                value = CcxtPositionMapper._as_float(info.get(key))
                if value is not None:
                    return value
            # Gate position history: short_price=exit for long, long_price=exit for short
            side = payload.get("side")
            exit_key = "short_price" if side == "long" else "long_price"
            value = CcxtPositionMapper._as_float(info.get(exit_key))
            if value is not None:
                return value
        return None

    @staticmethod
    def _parse_opened_at(payload: dict[str, object]) -> datetime | None:
        info = payload.get("info")
        if isinstance(info, dict):
            for key in ("createTime", "createdTime", "openTime"):
                ts = CcxtPositionMapper._as_float(info.get(key))
                if ts is not None and ts > 0:
                    return datetime.fromtimestamp(float(ts) / 1000.0, tz=UTC)
            # Gate: first_open_time in UNIX seconds
            fot = CcxtPositionMapper._as_float(info.get("first_open_time"))
            if fot is not None and fot > 1_000_000_000:
                return datetime.fromtimestamp(float(fot), tz=UTC)
        opened_at_raw = payload.get("timestamp")
        if isinstance(opened_at_raw, (int, float)) and opened_at_raw > 0:
            return datetime.fromtimestamp(float(opened_at_raw) / 1000.0, tz=UTC)
        return None

    @classmethod
    def _payload_has_cancelled_status(cls, payload: dict[str, object]) -> bool:
        if cls._dict_has_cancelled_status(payload):
            return True
        info = payload.get("info")
        return bool(isinstance(info, dict) and cls._dict_has_cancelled_status(info))

    @classmethod
    def _dict_has_cancelled_status(cls, data: dict[str, object]) -> bool:
        for key in cls._STATUS_INFO_KEYS:
            raw = data.get(key)
            if isinstance(raw, str) and raw.strip().lower() in cls._CANCELLED_STATUS_TOKENS:
                return True
        return False

    @classmethod
    def _dict_has_closed_status(cls, data: dict[str, object]) -> bool:
        for key in cls._STATUS_INFO_KEYS:
            raw = data.get(key)
            if not isinstance(raw, str):
                continue
            normalized = raw.strip().lower()
            if normalized in cls._CLOSED_STATUS_TOKENS or normalized == "3":
                return True
        return False

    @classmethod
    def _dict_has_close_volume(cls, data: dict[str, object]) -> bool:
        for key in cls._CLOSE_VOLUME_INFO_KEYS:
            volume = CcxtPositionMapper._as_float(data.get(key))
            if volume is not None and volume > 0.0:
                return True
        for key in ("closeVolume", "closedSize"):
            volume = CcxtPositionMapper._as_float(data.get(key))
            if volume is not None and volume > 0.0:
                return True
        return False

    @staticmethod
    def _extract_marker(payload: dict[str, object]) -> str | None:
        info = payload.get("info")
        candidates: list[object] = [
            payload.get("clientOrderId"),
        ]
        if isinstance(info, dict):
            candidates.extend(
                [
                    info.get("clientOrderId"),
                    info.get("clientOid"),
                    info.get("orderLinkId"),
                ]
            )
        for candidate in candidates:
            marker = CcxtPositionMapper.parse_arb_marker_id(candidate)
            if marker is not None:
                return marker
        return None

    @staticmethod
    def _parse_closed_at(payload: dict[str, object]) -> datetime:
        """Parse close timestamp — prefer lastUpdateTimestamp (actual close time)."""
        last_update = payload.get("lastUpdateTimestamp")
        if isinstance(last_update, (int, float)) and last_update > 0:
            return datetime.fromtimestamp(float(last_update) / 1000.0, tz=UTC)
        info = payload.get("info")
        if isinstance(info, dict):
            # Gate: time field in UNIX seconds
            t = CcxtPositionMapper._as_float(info.get("time"))
            if t is not None and t > 1_000_000_000:
                return datetime.fromtimestamp(float(t), tz=UTC)
        return CcxtPositionMapper._parse_datetime(payload)

    @staticmethod
    def _parse_datetime(payload: dict[str, object]) -> datetime:
        ts = payload.get("timestamp")
        if isinstance(ts, (int, float)) and ts > 0:
            return datetime.fromtimestamp(float(ts) / 1000.0, tz=UTC)
        dt = payload.get("datetime")
        if isinstance(dt, str):
            try:
                parsed = datetime.fromisoformat(dt.replace("Z", "+00:00"))
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
            except ValueError:
                pass
        last_update = payload.get("lastUpdateTimestamp")
        if isinstance(last_update, (int, float)) and last_update > 0:
            return datetime.fromtimestamp(float(last_update) / 1000.0, tz=UTC)
        # Return epoch-zero rather than now() — a stable sentinel that won't
        # cause dates to change on every fetch when the exchange omits timestamps.
        return datetime(1970, 1, 1, tzinfo=UTC)

    @staticmethod
    def _parse_next_funding(payload: dict[str, object]) -> datetime | None:
        for key in ("nextFundingTimestamp", "nextFundingTime"):
            raw = payload.get(key)
            if isinstance(raw, (int, float)) and raw > 0:
                return datetime.fromtimestamp(float(raw) / 1000.0, tz=UTC)
        info = payload.get("info")
        if isinstance(info, dict):
            for key in ("nextFundingTime", "nextFundingTimestamp"):
                raw = info.get(key)
                if isinstance(raw, (int, float)) and raw > 0:
                    return datetime.fromtimestamp(float(raw) / 1000.0, tz=UTC)
                if isinstance(raw, str) and raw.isdigit():
                    return datetime.fromtimestamp(float(raw) / 1000.0, tz=UTC)
        return None

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

    @staticmethod
    def _as_str(value: object) -> str | None:
        if isinstance(value, str) and value:
            return value
        if isinstance(value, (int, float)):
            return str(value)
        return None
