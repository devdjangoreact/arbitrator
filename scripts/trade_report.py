"""Trade report — identical data pipeline to the Orders UI.

Fetches open positions from exchanges (same as AccountStreamWorker) and
closed positions via REST (same as ExchangeOrdersService).  Closed positions
are cached in data/closed_positions_cache.json so restarts are fast.

Usage:
    .venv\\Scripts\\python.exe scripts/trade_report.py [--refresh]

    --refresh   force re-fetch closed positions from exchanges (ignores cache)
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ── project path ──────────────────────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(_ROOT / ".env")

from arbitrator.config.settings import Settings  # noqa: E402
from arbitrator.exchanges.factory import Factory  # noqa: E402
from arbitrator.domain.position_leg import PositionLeg  # noqa: E402
from arbitrator.domain.closed_position_leg import ClosedPositionLeg  # noqa: E402

_CACHE_PATH = _ROOT / "src" / "arbitrator" / "data" / "closed_positions_cache.json"
_SEEN_PATH  = _ROOT / "src" / "arbitrator" / "data" / "seen_symbols.json"
_CACHE_TTL_SEC = 300  # 5 min — re-fetch if older


# ── cache helpers ─────────────────────────────────────────────────────────────

def _load_cache() -> tuple[list[dict], float]:
    try:
        raw = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
        return raw["legs"], raw["fetched_at"]
    except Exception:
        return [], 0.0


def _save_cache(legs: list[ClosedPositionLeg]) -> None:
    data = {
        "fetched_at": time.time(),
        "legs": [leg.model_dump(mode="json") for leg in legs],
    }
    _CACHE_PATH.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


def _load_seen_symbols() -> set[str]:
    try:
        return set(json.loads(_SEEN_PATH.read_text(encoding="utf-8")))
    except Exception:
        return set()


# ── fetch open positions (same as AccountStreamWorker.read_positions) ─────────

async def _fetch_open(settings: Settings, factory: Factory) -> list[PositionLeg]:
    legs: list[PositionLeg] = []
    for eid in settings.enabled_exchanges:
        if settings.credentials_for(eid) is None:
            continue
        named = factory.create(eid)
        try:
            fetched = await named.gateway.fetch_open_positions()
            legs.extend(fetched)
        except Exception as e:
            print(f"  [warn] open positions {eid}: {e}")
        finally:
            try:
                await named.gateway.close()
            except Exception:
                pass
    return legs


# ── fetch closed positions (same as ExchangeOrdersService._async_fetch_closed) ─

async def _fetch_closed(
    settings: Settings,
    factory: Factory,
    since_ms: int,
    known_symbols: list[str],
) -> list[ClosedPositionLeg]:
    legs: list[ClosedPositionLeg] = []
    for eid in settings.enabled_exchanges:
        if settings.credentials_for(eid) is None:
            continue
        named = factory.create(eid)
        try:
            fetched = await named.gateway.fetch_closed_positions(
                since_ms=since_ms, symbols=known_symbols
            )
            legs.extend(fetched)
            print(f"  {eid}: {len(fetched)} closed positions")
        except Exception as e:
            print(f"  [warn] closed positions {eid}: {e}")
        finally:
            try:
                await named.gateway.close()
            except Exception:
                pass
    return legs


# ── grouping (identical to ExchangeOrdersService._group_legs) ────────────────

def _group(
    open_legs: list[PositionLeg],
    closed_legs: list[ClosedPositionLeg],
) -> list[dict]:
    groups: list[dict] = []

    # open pairs
    by_sym: dict[str, list[PositionLeg]] = {}
    for l in open_legs:
        by_sym.setdefault(l.symbol, []).append(l)

    used_open: set[int] = set()
    for sym, legs in by_sym.items():
        shorts = [l for l in legs if l.side == "short"]
        longs  = [l for l in legs if l.side == "long"]
        for s in shorts:
            for lo in longs:
                if s.exchange_id != lo.exchange_id and id(s) not in used_open:
                    used_open.add(id(s)); used_open.add(id(lo))
                    groups.append(_open_pair(s, lo))
        for l in legs:
            if id(l) not in used_open:
                groups.append(_open_single(l))

    # closed pairs — by arb_marker_id first, then by symbol
    by_marker: dict[str, list[ClosedPositionLeg]] = {}
    by_sym_c:  dict[str, list[ClosedPositionLeg]] = {}
    for l in closed_legs:
        if l.arb_marker_id:
            by_marker.setdefault(l.arb_marker_id, []).append(l)
        else:
            by_sym_c.setdefault(l.symbol, []).append(l)

    used_closed: set[int] = set()
    for _, mlegs in by_marker.items():
        ss = [l for l in mlegs if l.side == "short"]
        ll = [l for l in mlegs if l.side == "long"]
        if ss and ll:
            used_closed.add(id(ss[0])); used_closed.add(id(ll[0]))
            groups.append(_closed_pair(ss[0], ll[0]))
        else:
            for l in mlegs:
                if id(l) not in used_closed:
                    used_closed.add(id(l))
                    groups.append(_closed_single(l))

    for _, slegs in by_sym_c.items():
        ss = [l for l in slegs if l.side == "short" and id(l) not in used_closed]
        ll = [l for l in slegs if l.side == "long"  and id(l) not in used_closed]
        for s in list(ss):
            for lo in list(ll):
                if s.exchange_id != lo.exchange_id:
                    used_closed.add(id(s)); used_closed.add(id(lo))
                    ss.remove(s); ll.remove(lo)
                    groups.append(_closed_pair(s, lo))
                    break
        for l in slegs:
            if id(l) not in used_closed:
                groups.append(_closed_single(l))

    return groups


def _open_pair(s: PositionLeg, lo: PositionLeg) -> dict:
    pnl  = (s.unrealized_pnl or 0.0) + (lo.unrealized_pnl or 0.0)
    fees = (s.opening_fee or 0.0) + (s.estimated_close_fee or 0.0) + \
           (lo.opening_fee or 0.0) + (lo.estimated_close_fee or 0.0)
    fund = (s.accrued_funding or 0.0) + (lo.accrued_funding or 0.0)
    notional = (s.contracts * s.contract_size * s.entry_price +
                lo.contracts * lo.contract_size * lo.entry_price)
    s_mark  = s.mark_price  or s.entry_price
    lo_mark = lo.mark_price or lo.entry_price
    spread  = round((s_mark - lo_mark) / lo_mark * 100, 4) if lo_mark else None
    entry_s = s_mark
    entry_l = lo_mark
    entry_spread = round((s.entry_price - lo.entry_price) / lo.entry_price * 100, 4) if lo.entry_price else None
    return {
        "status": "open",
        "symbol": s.symbol,
        "short_ex": s.exchange_id,
        "long_ex": lo.exchange_id,
        "opened_at": min(s.opened_at, lo.opened_at),
        "closed_at": None,
        "notional_usdt": round(notional, 2),
        "entry_spread_pct": entry_spread,
        "current_spread_pct": spread,
        "pnl_usdt": round(pnl, 4),
        "fees_usdt": round(fees, 4),
        "funding_usdt": round(fund, 4),
        "net_pnl_usdt": round(pnl - fees + fund, 4),
        "short_contracts": s.contracts,
        "long_contracts": lo.contracts,
        "short_entry": s.entry_price,
        "long_entry": lo.entry_price,
        "short_mark": s.mark_price,
        "long_mark": lo.mark_price,
    }


def _open_single(l: PositionLeg) -> dict:
    notional = l.contracts * l.contract_size * l.entry_price
    return {
        "status": "open",
        "symbol": l.symbol,
        "short_ex": l.exchange_id if l.side == "short" else None,
        "long_ex":  l.exchange_id if l.side == "long"  else None,
        "opened_at": l.opened_at,
        "closed_at": None,
        "notional_usdt": round(notional, 2),
        "entry_spread_pct": None,
        "current_spread_pct": None,
        "pnl_usdt": round(l.unrealized_pnl or 0.0, 4),
        "fees_usdt": round((l.opening_fee or 0.0) + (l.estimated_close_fee or 0.0), 4),
        "funding_usdt": round(l.accrued_funding or 0.0, 4),
        "net_pnl_usdt": round((l.unrealized_pnl or 0.0) - (l.opening_fee or 0.0) -
                               (l.estimated_close_fee or 0.0) + (l.accrued_funding or 0.0), 4),
        "side": l.side,
        "contracts": l.contracts,
        "entry_price": l.entry_price,
        "mark_price": l.mark_price,
    }


def _closed_pair(s: ClosedPositionLeg, lo: ClosedPositionLeg) -> dict:
    pnl  = (s.realized_pnl or 0.0) + (lo.realized_pnl or 0.0)
    fees = (s.commission or 0.0) + (lo.commission or 0.0)
    fund = (s.funding or 0.0) + (lo.funding or 0.0)
    opened_at = s.opened_at or lo.opened_at
    closed_at = max(s.closed_at, lo.closed_at)
    dur = None
    if opened_at:
        secs = int((closed_at - opened_at).total_seconds())
        dur  = f"{secs//3600}h {(secs%3600)//60}m" if secs >= 3600 else f"{secs//60}m {secs%60}s"
    sx = s.exit_price; lx = lo.exit_price
    exit_spread = round((sx - lx) / lx * 100, 4) if sx and lx and lx > 0 else None
    short_notional = (s.contracts or 0.0) * (sx or s.entry_price or 0.0)
    long_notional  = (lo.contracts or 0.0) * (lx or lo.entry_price or 0.0)
    notional = round(short_notional + long_notional, 2) or None
    return {
        "status": "closed",
        "symbol": s.symbol,
        "short_ex": s.exchange_id,
        "long_ex": lo.exchange_id,
        "opened_at": opened_at,
        "closed_at": closed_at,
        "duration": dur,
        "notional_usdt": notional,
        "exit_spread_pct": exit_spread,
        "pnl_usdt": round(pnl, 4),
        "fees_usdt": round(fees, 4),
        "funding_usdt": round(fund, 4),
        "net_pnl_usdt": round(pnl - fees + fund, 4),
        "short_entry": s.entry_price,
        "long_entry": lo.entry_price,
        "short_exit": s.exit_price,
        "long_exit": lo.exit_price,
        "short_contracts": s.contracts,
        "long_contracts": lo.contracts,
    }


def _closed_single(l: ClosedPositionLeg) -> dict:
    ref = l.exit_price or l.entry_price or 0.0
    notional = round((l.contracts or 0.0) * ref, 2) or None
    opened_at = l.opened_at
    closed_at = l.closed_at
    dur = None
    if opened_at:
        secs = int((closed_at - opened_at).total_seconds())
        dur  = f"{secs//3600}h {(secs%3600)//60}m" if secs >= 3600 else f"{secs//60}m {secs%60}s"
    return {
        "status": "closed",
        "symbol": l.symbol,
        "short_ex": l.exchange_id if l.side == "short" else None,
        "long_ex":  l.exchange_id if l.side == "long"  else None,
        "opened_at": opened_at,
        "closed_at": closed_at,
        "duration": dur,
        "notional_usdt": notional,
        "exit_spread_pct": None,
        "pnl_usdt": round(l.realized_pnl or 0.0, 4),
        "fees_usdt": round(l.commission or 0.0, 4),
        "funding_usdt": round(l.funding or 0.0, 4),
        "net_pnl_usdt": round((l.realized_pnl or 0.0) - (l.commission or 0.0) + (l.funding or 0.0), 4),
        "side": l.side,
        "contracts": l.contracts,
        "entry_price": l.entry_price,
        "exit_price": l.exit_price,
    }


# ── rendering ─────────────────────────────────────────────────────────────────

W = 72

def _fmt(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    local = dt.astimezone() if dt.tzinfo else dt
    return local.strftime("%m/%d %H:%M")


def _render(groups: list[dict]) -> None:
    open_g    = [g for g in groups if g["status"] == "open"]
    closed_g  = [g for g in groups if g["status"] == "closed"]

    total_open_pnl   = sum(g["pnl_usdt"] for g in open_g)
    total_closed_pnl = sum(g["net_pnl_usdt"] for g in closed_g)
    total_fees       = sum(g["fees_usdt"] for g in groups)
    total_funding    = sum(g["funding_usdt"] for g in groups)

    print("=" * W)
    print(f"  TRADE REPORT  --  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * W)
    print(f"  Open positions :  {len(open_g)}")
    print(f"  Closed trades  :  {len(closed_g)}")
    print(f"  Unrealized PnL :  {total_open_pnl:+.4f} USDT")
    print(f"  Realized PnL   :  {total_closed_pnl:+.4f} USDT  (after fees+funding)")
    print(f"  Total fees     :  {total_fees:.4f} USDT")
    print(f"  Total funding  :  {total_funding:+.4f} USDT")
    print("=" * W)

    if open_g:
        print("\n-- OPEN POSITIONS " + "-" * (W - 18))
        for g in open_g:
            sym   = g["symbol"].replace("/USDT:USDT", "")
            s_ex  = g.get("short_ex") or "?"
            l_ex  = g.get("long_ex")  or "?"
            pair  = f"{s_ex}->{l_ex}"
            notio = f"{g['notional_usdt']} USDT" if g["notional_usdt"] else "?"
            sprd  = f"spread={g['current_spread_pct']:+.4f}%" if g.get("current_spread_pct") is not None else ""
            entry = f"entry={g.get('entry_spread_pct'):+.4f}%" if g.get("entry_spread_pct") is not None else ""
            pnl   = g["pnl_usdt"]
            fees  = g["fees_usdt"]
            fund  = g["funding_usdt"]
            net   = g["net_pnl_usdt"]
            since = _fmt(g["opened_at"])
            imb   = ""
            if g.get("short_contracts") and g.get("long_contracts"):
                ratio = g["short_contracts"] / g["long_contracts"]
                if abs(ratio - 1.0) > 0.05:
                    imb = f"  ! imbalance {ratio:.2f}x"
            print(f"\n  {sym:<10} {pair:<22} {notio:<14} since {since}")
            print(f"             {entry:<24} {sprd}")
            print(f"             unrealized={pnl:+.4f}  fees={fees:.4f}  funding={fund:+.4f}  net={net:+.4f} USDT{imb}")
            if g.get("short_contracts"):
                print(f"             short {s_ex}: {g['short_contracts']} @ {g.get('short_entry')}  mark={g.get('short_mark')}")
            if g.get("long_contracts"):
                print(f"             long  {l_ex}: {g['long_contracts']} @ {g.get('long_entry')}  mark={g.get('long_mark')}")

    if closed_g:
        print("\n-- CLOSED TRADES " + "-" * (W - 17))
        for g in closed_g:
            sym  = g["symbol"].replace("/USDT:USDT", "")
            s_ex = g.get("short_ex") or "?"
            l_ex = g.get("long_ex")  or "?"
            pair = f"{s_ex}->{l_ex}"
            dur  = g.get("duration") or "?"
            notio = f"{g['notional_usdt']} USDT" if g["notional_usdt"] else "?"
            sprd = f"exit_spread={g['exit_spread_pct']:+.4f}%" if g.get("exit_spread_pct") is not None else ""
            pnl  = g["pnl_usdt"]
            fees = g["fees_usdt"]
            fund = g["funding_usdt"]
            net  = g["net_pnl_usdt"]
            sign = "+" if net >= 0 else ""
            print(f"\n  {sym:<10} {pair:<22} {notio:<14} dur={dur}")
            print(f"             opened={_fmt(g['opened_at'])}  closed={_fmt(g['closed_at'])}  {sprd}")
            print(f"             realized={pnl:+.4f}  fees={fees:.4f}  funding={fund:+.4f}  NET={sign}{net:.4f} USDT")
            if g.get("short_entry"):
                print(f"             short {s_ex}: entry={g['short_entry']}  exit={g.get('short_exit')}")
            if g.get("long_entry"):
                print(f"             long  {l_ex}: entry={g['long_entry']}  exit={g.get('long_exit')}")

    print("\n" + "=" * W)


# ── main ──────────────────────────────────────────────────────────────────────

async def _main(force_refresh: bool) -> None:
    settings = Settings()  # type: ignore[call-arg]
    factory  = Factory(settings)

    print("Fetching open positions from exchanges...")
    open_legs = await _fetch_open(settings, factory)
    print(f"  total open: {len(open_legs)}")

    open_symbols = {l.symbol for l in open_legs}
    seen_symbols = _load_seen_symbols() | open_symbols
    known_symbols = sorted(seen_symbols)

    cached_legs, fetched_at = _load_cache()
    age = time.time() - fetched_at
    if force_refresh or age > _CACHE_TTL_SEC or not cached_legs:
        print(f"\nFetching closed positions from exchanges (cache age={int(age)}s)...")
        since_ms = int(time.time() * 1000) - 7 * 24 * 3600 * 1000
        closed_legs = await _fetch_closed(settings, factory, since_ms, known_symbols)
        _save_cache(closed_legs)
        print(f"  cached {len(closed_legs)} closed legs to {_CACHE_PATH.name}")
    else:
        print(f"\nUsing cached closed positions (age={int(age)}s, {len(cached_legs)} legs)")
        closed_legs = [ClosedPositionLeg(**r) for r in cached_legs]

    print()
    groups = _group(open_legs, closed_legs)
    _render(groups)


if __name__ == "__main__":
    force = "--refresh" in sys.argv
    asyncio.run(_main(force))
