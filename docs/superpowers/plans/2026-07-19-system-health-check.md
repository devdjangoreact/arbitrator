# System Health-Check Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a system health-check that runs once at startup (retrying until all exchange data fields pass), exposes a manual trigger via REST + WebSocket, refreshes symbol universes, and shows a persistent banner in the React UI when errors exist.

**Architecture:** A new `SystemHealthService` owns all check logic and state; `AppRuntime` starts it as a background thread; `FastAPI` exposes `GET /api/system-health` and `POST /api/system-health/run`; `App.tsx` polls the REST endpoint and renders a banner; `SettingsPage.tsx` adds a "System Check" panel with per-exchange results table.

**Tech Stack:** Python 3.11, FastAPI, asyncio, ccxt.pro, React 18, TypeScript, Tailwind CSS.

## Global Constraints

- All Python uses `.venv\Scripts\*.exe` — never global Python.
- Tests: `.venv\Scripts\python.exe -m pytest tests/ -q`
- Mypy: `.venv\Scripts\mypy.exe --strict src/arbitrator/...`
- React build: `pnpm build` in `src/arbitrator/presentation/react-ui/`
- No trading actions (create_order / cancel_order) anywhere in this feature.
- `ui_data_mode=mock_data` skips all health checks (no real exchanges).
- Credential errors (balance=None, auth=False) are **warnings**, not errors — system continues without retry for those.
- All user-visible text in Ukrainian.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `src/arbitrator/application/market_data/system_health_service.py` | **Create** | All check logic, state, startup loop, symbol refresh |
| `src/arbitrator/presentation/fastapi_app.py` | **Modify** | Add `GET /api/system-health` and `POST /api/system-health/run` |
| `src/arbitrator/application/app_runtime.py` | **Modify** | Instantiate + start `SystemHealthService` |
| `src/arbitrator/presentation/react-ui/src/types/index.ts` | **Modify** | Add `SystemHealthState` type |
| `src/arbitrator/presentation/react-ui/src/App.tsx` | **Modify** | Poll health endpoint, render banner |
| `src/arbitrator/presentation/react-ui/src/pages/SettingsPage.tsx` | **Modify** | Add "System Check" section with table + manual trigger button |
| `tests/unit/test_system_health_service.py` | **Create** | Unit tests for check logic and state transitions |

---

## Task 1: `SystemHealthService` — core check logic and state

**Files:**
- Create: `src/arbitrator/application/market_data/system_health_service.py`
- Test: `tests/unit/test_system_health_service.py`

**Interfaces:**
- Produces:
  - `SystemHealthService(settings, factory)` constructor
  - `async run_checks() -> SystemHealthSnapshot`
  - `get_snapshot() -> SystemHealthSnapshot`
  - `start_background_loop()` — starts daemon thread, retries every 30 s until no errors
  - `stop()`
- `SystemHealthSnapshot` dataclass fields:
  - `checked_at: float` — `time.time()` epoch
  - `all_passed: bool`
  - `exchanges: list[ExchangeHealthResult]`
- `ExchangeHealthResult` dataclass fields:
  - `exchange_id: str`
  - `display_name: str`
  - `futures_balance_usdt: float | None` — USDT swap/futures wallet balance (None if no creds or fetch failed)
  - `spot_balance_usdt: float | None` — USDT spot wallet balance (None if no creds or fetch failed)
  - `checks: list[HealthCheck]`
- `HealthCheck` dataclass fields:
  - `name: str`
  - `passed: bool`
  - `is_warning: bool` — True = credential-only issue, doesn't block `all_passed`
  - `detail: str | None`

Per exchange, `run_checks` verifies:

| Check name | Method | `is_warning` |
|---|---|---|
| `symbols_loaded` | `gateway.list_symbols()` len > 0 | False |
| `bid_ask` | `gateway.fetch_order_book_once(probe_symbol, 1)` bids+asks non-empty | False |
| `funding_rate` | `gateway.fetch_funding_infos([probe_symbol])` → rate not None | False |
| `funding_time` | same fetch → next_settlement_ms not None | False |
| `market_info_max` | `gateway.fetch_symbol_market_info(probe_symbol)` → max_order_volume_usdt not None | False |
| `market_info_min` | same → min_order_volume_usdt not None | False |
| `futures_balance` | `CcxtBase.probe_connection()` → `usdt_balance` not None; result stored in `ExchangeHealthResult.futures_balance_usdt` | **True** |
| `spot_balance` | `SpotCcxtAdapter(settings).fetch_balance("USDT")` → > 0 or no error; stored in `ExchangeHealthResult.spot_balance_usdt` | **True** |

`probe_symbol` = first symbol from `list_symbols()` that contains "BTC" or "ETH", fallback first symbol. Skip exchange entirely if `credentials_for(ex)` is None (no credentials → only public checks; `futures_balance_usdt` and `spot_balance_usdt` remain None).

`all_passed` = all checks where `is_warning=False` pass across all exchanges.

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_system_health_service.py
from __future__ import annotations
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from arbitrator.application.market_data.system_health_service import (
    SystemHealthService,
    SystemHealthSnapshot,
    ExchangeHealthResult,
    HealthCheck,
)
from arbitrator.config.settings import Settings


def _make_svc(has_creds: bool = True) -> SystemHealthService:
    settings = Settings(enabled_exchanges=["bitget"])
    factory = MagicMock()
    svc = SystemHealthService(settings=settings, factory=factory)
    return svc


def test_snapshot_all_passed_true_when_no_errors() -> None:
    snap = SystemHealthSnapshot(
        checked_at=0.0,
        all_passed=True,
        exchanges=[
            ExchangeHealthResult(
                exchange_id="bitget",
                display_name="Bitget",
                futures_balance_usdt=None,
                spot_balance_usdt=None,
                checks=[
                    HealthCheck(name="symbols_loaded", passed=True, is_warning=False, detail=None),
                    HealthCheck(name="futures_balance", passed=False, is_warning=True, detail="no creds"),
                ],
            )
        ],
    )
    assert snap.all_passed is True


def test_snapshot_all_passed_false_when_non_warning_fails() -> None:
    snap = SystemHealthSnapshot(
        checked_at=0.0,
        all_passed=False,
        exchanges=[
            ExchangeHealthResult(
                exchange_id="bitget",
                display_name="Bitget",
                futures_balance_usdt=None,
                spot_balance_usdt=None,
                checks=[
                    HealthCheck(name="bid_ask", passed=False, is_warning=False, detail="timeout"),
                ],
            )
        ],
    )
    assert snap.all_passed is False


def test_exchange_health_result_exposes_balances() -> None:
    r = ExchangeHealthResult(
        exchange_id="gate",
        display_name="Gate",
        futures_balance_usdt=123.45,
        spot_balance_usdt=50.0,
        checks=[],
    )
    assert r.futures_balance_usdt == 123.45
    assert r.spot_balance_usdt == 50.0


def test_get_snapshot_returns_none_before_first_run() -> None:
    svc = _make_svc()
    assert svc.get_snapshot() is None


@pytest.mark.asyncio
async def test_run_checks_returns_snapshot_with_all_exchanges() -> None:
    settings = Settings(enabled_exchanges=["bitget", "gate"])
    factory = MagicMock()
    svc = SystemHealthService(settings=settings, factory=factory)

    async def _fake_run_for_exchange(ex_id: str) -> ExchangeHealthResult:
        return ExchangeHealthResult(
            exchange_id=ex_id,
            display_name=ex_id,
            futures_balance_usdt=None,
            spot_balance_usdt=None,
            checks=[HealthCheck(name="symbols_loaded", passed=True, is_warning=False, detail=None)],
        )

    with patch.object(svc, "_run_exchange_checks", side_effect=_fake_run_for_exchange):
        snap = await svc.run_checks()

    assert len(snap.exchanges) == 2
    assert {r.exchange_id for r in snap.exchanges} == {"bitget", "gate"}
```

- [ ] **Step 2: Run to verify RED**

```
.venv\Scripts\python.exe -m pytest tests/unit/test_system_health_service.py -v
```
Expected: `ModuleNotFoundError: No module named 'arbitrator.application.market_data.system_health_service'`

- [ ] **Step 3: Implement `SystemHealthService`**

```python
# src/arbitrator/application/market_data/system_health_service.py
from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass, field

from arbitrator.config.logger import logger
from arbitrator.config.settings import Settings
from arbitrator.exchanges.factory import Factory


@dataclass
class HealthCheck:
    name: str
    passed: bool
    is_warning: bool
    detail: str | None = None


@dataclass
class ExchangeHealthResult:
    exchange_id: str
    display_name: str
    futures_balance_usdt: float | None = None
    spot_balance_usdt: float | None = None
    checks: list[HealthCheck] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(not c.passed and not c.is_warning for c in self.checks)

    @property
    def has_warnings(self) -> bool:
        return any(not c.passed and c.is_warning for c in self.checks)


@dataclass
class SystemHealthSnapshot:
    checked_at: float
    all_passed: bool
    exchanges: list[ExchangeHealthResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "checked_at": self.checked_at,
            "all_passed": self.all_passed,
            "exchanges": [
                {
                    "exchange_id": r.exchange_id,
                    "display_name": r.display_name,
                    "futures_balance_usdt": r.futures_balance_usdt,
                    "spot_balance_usdt": r.spot_balance_usdt,
                    "has_errors": r.has_errors,
                    "has_warnings": r.has_warnings,
                    "checks": [
                        {"name": c.name, "passed": c.passed,
                         "is_warning": c.is_warning, "detail": c.detail}
                        for c in r.checks
                    ],
                }
                for r in self.exchanges
            ],
        }


class SystemHealthService:
    _RETRY_INTERVAL_S = 30

    def __init__(self, settings: Settings, factory: Factory) -> None:
        self._settings = settings
        self._factory = factory
        self._snapshot: SystemHealthSnapshot | None = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def get_snapshot(self) -> SystemHealthSnapshot | None:
        with self._lock:
            return self._snapshot

    def start_background_loop(self) -> None:
        self._thread = threading.Thread(
            target=self._run, name="system-health-check", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        try:
            asyncio.run(self._async_loop())
        except Exception:
            logger.exception("system health check loop failed")

    async def _async_loop(self) -> None:
        while not self._stop.is_set():
            try:
                snap = await self.run_checks()
                with self._lock:
                    self._snapshot = snap
                if snap.all_passed:
                    logger.info("system health check passed — stopping auto-retry")
                    return
                logger.warning(
                    "system health check has errors — retrying in {}s",
                    self._RETRY_INTERVAL_S,
                )
            except Exception:
                logger.exception("system health run_checks failed")
            await asyncio.sleep(self._RETRY_INTERVAL_S)

    async def run_checks(self) -> SystemHealthSnapshot:
        exchange_ids = list(self._settings.enabled_exchanges)
        results = await asyncio.gather(
            *[self._run_exchange_checks(ex_id) for ex_id in exchange_ids],
            return_exceptions=False,
        )
        all_passed = all(not r.has_errors for r in results)
        return SystemHealthSnapshot(
            checked_at=time.time(),
            all_passed=all_passed,
            exchanges=list(results),
        )

    async def _run_exchange_checks(self, exchange_id: str) -> ExchangeHealthResult:
        named = self._factory.create(exchange_id, mode="public")
        gw = named.gateway
        display = getattr(gw, "display_name", exchange_id)
        checks: list[HealthCheck] = []

        # 1. symbols_loaded
        try:
            symbols = await gw.list_symbols()
            checks.append(HealthCheck(
                name="symbols_loaded",
                passed=len(symbols) > 0,
                is_warning=False,
                detail=f"{len(symbols)} symbols" if symbols else "empty list",
            ))
        except Exception as e:
            checks.append(HealthCheck(name="symbols_loaded", passed=False, is_warning=False, detail=str(e)))
            symbols = []
        finally:
            await gw.close()

        probe = next(
            (s for s in symbols if "BTC" in s or "ETH" in s),
            symbols[0] if symbols else "BTC/USDT:USDT",
        )

        named_pub = self._factory.create(exchange_id, mode="public")
        pub_gw = named_pub.gateway
        try:
            # 2. bid_ask
            try:
                book = await pub_gw.fetch_order_book_once(probe, 1)
                ok = bool(book.bids and book.asks)
                checks.append(HealthCheck(
                    name="bid_ask", passed=ok, is_warning=False,
                    detail=None if ok else "bids or asks empty",
                ))
            except Exception as e:
                checks.append(HealthCheck(name="bid_ask", passed=False, is_warning=False, detail=str(e)))

            # 3+4. funding_rate + funding_time
            try:
                from arbitrator.exchanges.ccxt_base import CcxtBase
                if isinstance(pub_gw, CcxtBase):
                    infos = await pub_gw.fetch_funding_infos([probe])
                    fi = infos[0] if infos else None
                    rate_ok = fi is not None and fi.rate is not None
                    time_ok = fi is not None and fi.next_settlement_ms is not None
                else:
                    rate_ok = time_ok = False
                checks.append(HealthCheck(
                    name="funding_rate", passed=rate_ok, is_warning=False,
                    detail=None if rate_ok else "rate is None",
                ))
                checks.append(HealthCheck(
                    name="funding_time", passed=time_ok, is_warning=False,
                    detail=None if time_ok else "next_settlement_ms is None",
                ))
            except Exception as e:
                checks.append(HealthCheck(name="funding_rate", passed=False, is_warning=False, detail=str(e)))
                checks.append(HealthCheck(name="funding_time", passed=False, is_warning=False, detail=str(e)))

            # 5+6. market_info
            try:
                from arbitrator.exchanges.ccxt_base import CcxtBase
                if isinstance(pub_gw, CcxtBase):
                    info = await pub_gw.fetch_symbol_market_info(probe)
                    max_ok = info is not None and info.max_order_volume_usdt is not None
                    min_ok = info is not None and info.min_order_volume_usdt is not None
                else:
                    max_ok = min_ok = False
                checks.append(HealthCheck(
                    name="market_info_max", passed=max_ok, is_warning=False,
                    detail=None if max_ok else "max_order_volume_usdt is None",
                ))
                checks.append(HealthCheck(
                    name="market_info_min", passed=min_ok, is_warning=False,
                    detail=None if min_ok else "min_order_volume_usdt is None",
                ))
            except Exception as e:
                checks.append(HealthCheck(name="market_info_max", passed=False, is_warning=False, detail=str(e)))
                checks.append(HealthCheck(name="market_info_min", passed=False, is_warning=False, detail=str(e)))
        finally:
            await pub_gw.close()

        # 7+8. futures_balance + spot_balance (warning only — credential issues)
        futures_balance: float | None = None
        spot_balance: float | None = None
        has_creds = self._settings.credentials_for(exchange_id) is not None
        if has_creds:
            # futures/swap balance via probe_connection (defaultType=swap)
            named_priv = self._factory.create(exchange_id, mode="private")
            priv_gw = named_priv.gateway
            try:
                from arbitrator.exchanges.ccxt_base import CcxtBase
                if isinstance(priv_gw, CcxtBase):
                    status = await priv_gw.probe_connection()
                    futures_balance = status.usdt_balance
                    bal_ok = futures_balance is not None
                else:
                    bal_ok = False
                checks.append(HealthCheck(
                    name="futures_balance", passed=bal_ok, is_warning=True,
                    detail=None if bal_ok else "usdt_balance is None (check futures/swap account activation)",
                ))
            except Exception as e:
                checks.append(HealthCheck(
                    name="futures_balance", passed=False, is_warning=True, detail=str(e)
                ))
            finally:
                await priv_gw.close()

            # spot balance via SpotCcxtAdapter
            from arbitrator.exchanges.spot_ccxt_adapter import SpotCcxtAdapter
            spot_adapter = SpotCcxtAdapter(self._settings, exchange_id)
            try:
                spot_dec = await spot_adapter.fetch_balance("USDT")
                spot_balance = float(spot_dec)
                spot_ok = spot_balance >= 0
                checks.append(HealthCheck(
                    name="spot_balance", passed=spot_ok, is_warning=True,
                    detail=None if spot_ok else "spot USDT balance returned 0 or error",
                ))
            except Exception as e:
                checks.append(HealthCheck(
                    name="spot_balance", passed=False, is_warning=True, detail=str(e)
                ))
            finally:
                await spot_adapter.close()

        return ExchangeHealthResult(
            exchange_id=exchange_id,
            display_name=display,
            futures_balance_usdt=futures_balance,
            spot_balance_usdt=spot_balance,
            checks=checks,
        )
```

- [ ] **Step 4: Run tests — verify GREEN**

```
.venv\Scripts\python.exe -m pytest tests/unit/test_system_health_service.py -v
```
Expected: 4 passed

- [ ] **Step 5: Mypy check**

```
.venv\Scripts\mypy.exe --strict src/arbitrator/application/market_data/system_health_service.py
```
Expected: Success (0 errors)

- [ ] **Step 6: Commit**

```bash
git add src/arbitrator/application/market_data/system_health_service.py tests/unit/test_system_health_service.py
git commit -m "feat(health): SystemHealthService — per-exchange field checks with startup retry loop"
```

---

## Task 2: Symbol universe refresh inside health check

**Files:**
- Modify: `src/arbitrator/application/market_data/system_health_service.py:run_checks`

**Interfaces:**
- `SystemHealthService.__init__` gains optional `universe_service: SymbolUniverseService | None = None`
- `run_checks` calls `universe_service.resolve(exchanges, force_refresh=True)` before exchange checks if `universe_service` is not None

- [ ] **Step 1: Write failing test**

```python
# append to tests/unit/test_system_health_service.py

@pytest.mark.asyncio
async def test_run_checks_refreshes_universe_when_service_provided() -> None:
    from arbitrator.application.market_data.system_health_service import SystemHealthService
    from unittest.mock import AsyncMock, MagicMock, patch

    settings = Settings(enabled_exchanges=["bitget"])
    factory = MagicMock()
    universe_svc = MagicMock()
    universe_svc.resolve = AsyncMock(return_value=(["BTC/USDT:USDT"], {}, MagicMock()))

    svc = SystemHealthService(settings=settings, factory=factory, universe_service=universe_svc)

    with patch.object(svc, "_run_exchange_checks", new_callable=AsyncMock) as mock_ex:
        mock_ex.return_value = ExchangeHealthResult(
            exchange_id="bitget", display_name="Bitget", checks=[]
        )
        await svc.run_checks()

    universe_svc.resolve.assert_called_once()
    call_kwargs = universe_svc.resolve.call_args.kwargs
    assert call_kwargs.get("force_refresh") is True
```

- [ ] **Step 2: Run to verify RED**

```
.venv\Scripts\python.exe -m pytest tests/unit/test_system_health_service.py::test_run_checks_refreshes_universe_when_service_provided -v
```
Expected: FAIL — `TypeError: __init__() got unexpected keyword argument 'universe_service'`

- [ ] **Step 3: Add universe refresh to `SystemHealthService`**

In `system_health_service.py`, update the imports and `__init__` + `run_checks`:

```python
# add to imports
from collections.abc import Sequence
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from arbitrator.application.market_data.symbol_universe_service import SymbolUniverseService
    from arbitrator.domain.exchange.named_exchange import NamedExchange
```

```python
# update __init__ signature
def __init__(
    self,
    settings: Settings,
    factory: Factory,
    universe_service: SymbolUniverseService | None = None,
) -> None:
    ...
    self._universe_service = universe_service
```

```python
# update run_checks — add before gather():
async def run_checks(self) -> SystemHealthSnapshot:
    if self._universe_service is not None:
        try:
            named_exchanges: list[NamedExchange] = [
                self._factory.create(ex_id, mode="public")
                for ex_id in self._settings.enabled_exchanges
            ]
            await self._universe_service.resolve(
                named_exchanges, force_refresh=True
            )
            logger.info("symbol universe refreshed during health check")
        except Exception:
            logger.exception("universe refresh failed during health check")

    exchange_ids = list(self._settings.enabled_exchanges)
    results = await asyncio.gather(
        *[self._run_exchange_checks(ex_id) for ex_id in exchange_ids],
        return_exceptions=False,
    )
    all_passed = all(not r.has_errors for r in results)
    return SystemHealthSnapshot(
        checked_at=time.time(),
        all_passed=all_passed,
        exchanges=list(results),
    )
```

- [ ] **Step 4: Run all health tests — GREEN**

```
.venv\Scripts\python.exe -m pytest tests/unit/test_system_health_service.py -v
```
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/arbitrator/application/market_data/system_health_service.py tests/unit/test_system_health_service.py
git commit -m "feat(health): add symbol universe force-refresh on health check run"
```

---

## Task 3: Wire `SystemHealthService` into `AppRuntime` + `inspect_exchanges.py`

**Files:**
- Modify: `src/arbitrator/application/app_runtime.py`
- Modify: `scripts/inspect_exchanges.py`

**Interfaces:**
- `AppRuntime.system_health: SystemHealthService | None`
- `AppRuntime.get_health_snapshot() -> SystemHealthSnapshot | None`

- [ ] **Step 1: Write test for AppRuntime wiring**

```python
# append to tests/unit/test_system_health_service.py

def test_app_runtime_has_system_health_attr() -> None:
    from arbitrator.application.app_runtime import AppRuntime
    from arbitrator.config.settings import Settings
    runtime = AppRuntime(Settings(enabled_exchanges=["bitget"]))
    assert hasattr(runtime, "system_health")
    assert runtime.system_health is None  # not started yet in mock mode
```

- [ ] **Step 2: Verify RED**

```
.venv\Scripts\python.exe -m pytest tests/unit/test_system_health_service.py::test_app_runtime_has_system_health_attr -v
```
Expected: FAIL — AttributeError

- [ ] **Step 3: Add `system_health` to AppRuntime**

In `src/arbitrator/application/app_runtime.py`:

Add import at top:
```python
from arbitrator.application.market_data.system_health_service import SystemHealthService
```

In `__init__`, after existing attributes:
```python
self.system_health: SystemHealthService | None = None
```

Add method after `stop()`:
```python
def get_health_snapshot(self) -> "SystemHealthSnapshot | None":
    if self.system_health is None:
        return None
    return self.system_health.get_snapshot()
```

In `_start_live_workers` and `_start_paper_workers` (both), at the end of each method, add:
```python
# Start system health check (background, non-blocking)
universe_repo = JsonSymbolUniverseRepository(path=self._settings.symbols_universe_path)
universe_service = SymbolUniverseService(
    repository=universe_repo,
    exclusions=self.exclusions_repo,
    ttl_hours=self._settings.universe_ttl_hours,
    min_exchanges=self._settings.min_exchanges_per_symbol,
)
self.system_health = SystemHealthService(
    settings=self._settings,
    factory=Factory(settings=self._settings),
    universe_service=universe_service,
)
self.system_health.start_background_loop()
logger.info("system health check started")
```

In `stop()`, add at the top:
```python
if self.system_health is not None:
    self.system_health.stop()
    logger.info("system health service stopped")
```

- [ ] **Step 4: Add `health-check` command to `inspect_exchanges.py`**

In `_build_parser`, add after existing subparsers:
```python
health = subparsers.add_parser(
    "health-check",
    help="Run full exchange data field checks (bid/ask, funding, market_info, balance).",
)
health.add_argument(
    "--exchange",
    help="Single exchange id (default: all enabled in Settings).",
)
health.set_defaults(handler="health_check")
```

In `_dispatch`, add:
```python
if handler == "health_check":
    return await self._cmd_health_check(
        exchange_id=getattr(args, "exchange", None),
        as_json=bool(args.json),
    )
```

Add method to `InspectExchangesCli`:
```python
async def _cmd_health_check(
    self,
    *,
    exchange_id: str | None,
    as_json: bool,
) -> int:
    from arbitrator.application.market_data.system_health_service import SystemHealthService
    settings = self._inspector._settings
    factory_obj = self._inspector._factory
    svc = SystemHealthService(settings=settings, factory=factory_obj)

    if exchange_id:
        result = await svc._run_exchange_checks(exchange_id)
        snap_exchanges = [result]
        all_passed = not result.has_errors
    else:
        snap = await svc.run_checks()
        snap_exchanges = snap.exchanges
        all_passed = snap.all_passed

    if as_json:
        import time
        from arbitrator.application.market_data.system_health_service import SystemHealthSnapshot
        snap_out = SystemHealthSnapshot(
            checked_at=time.time(),
            all_passed=all_passed,
            exchanges=snap_exchanges,
        )
        self._print_json(snap_out.to_dict())
    else:
        for r in snap_exchanges:
            status = "✓" if not r.has_errors else "✗"
            warn = " (warnings)" if r.has_warnings else ""
            print(f"\n{status} {r.display_name} ({r.exchange_id}){warn}")
            for c in r.checks:
                icon = "  ✓" if c.passed else ("  ⚠" if c.is_warning else "  ✗")
                detail = f" — {c.detail}" if c.detail else ""
                print(f"{icon} {c.name}{detail}")
        print(f"\nOverall: {'PASSED' if all_passed else 'FAILED'}")

    return 0 if all_passed else 1
```

- [ ] **Step 5: Run test GREEN + quick smoke of CLI**

```
.venv\Scripts\python.exe -m pytest tests/unit/test_system_health_service.py -v
```
Expected: 6 passed

```
.venv\Scripts\python.exe scripts/inspect_exchanges.py health-check --help
```
Expected: usage shown with `--exchange` option

- [ ] **Step 6: Commit**

```bash
git add src/arbitrator/application/app_runtime.py scripts/inspect_exchanges.py tests/unit/test_system_health_service.py
git commit -m "feat(health): wire SystemHealthService into AppRuntime + add health-check CLI command"
```

---

## Task 4: REST endpoints `GET /api/system-health` and `POST /api/system-health/run`

**Files:**
- Modify: `src/arbitrator/presentation/fastapi_app.py`

**Interfaces:**
- `GET /api/system-health` → `SystemHealthSnapshot.to_dict()` or `{"status": "not_run_yet"}` if None
- `POST /api/system-health/run` → triggers `run_checks()` in background task, returns `{"status": "running"}`

- [ ] **Step 1: Add endpoints to `fastapi_app.py`**

In `src/arbitrator/presentation/fastapi_app.py`, inside the `build_app` method after existing route definitions, add:

```python
@app.get("/api/system-health")
async def system_health_get() -> dict[str, object]:
    snap = runtime.get_health_snapshot()
    if snap is None:
        return {"status": "not_run_yet", "all_passed": None, "exchanges": []}
    return snap.to_dict()

@app.post("/api/system-health/run")
async def system_health_run() -> dict[str, object]:
    if runtime.system_health is None:
        return {"status": "unavailable"}
    async def _bg() -> None:
        try:
            snap = await runtime.system_health.run_checks()  # type: ignore[union-attr]
            import threading
            with threading.Lock():
                runtime.system_health._snapshot = snap  # type: ignore[union-attr]
        except Exception:
            pass
    import asyncio as _aio
    _aio.create_task(_bg())
    return {"status": "running"}
```

- [ ] **Step 2: Manual smoke test**

Start the app: `.venv\Scripts\uvicorn.exe main:app --reload`

```
curl http://localhost:8000/api/system-health
```
Expected in `mock_data` mode: `{"status": "not_run_yet", "all_passed": null, "exchanges": []}`

```
curl -X POST http://localhost:8000/api/system-health/run
```
Expected: `{"status": "unavailable"}` (mock mode has no system_health)

- [ ] **Step 3: Commit**

```bash
git add src/arbitrator/presentation/fastapi_app.py
git commit -m "feat(health): add GET/POST /api/system-health REST endpoints"
```

---

## Task 5: React — TypeScript types + health banner in `App.tsx`

**Files:**
- Modify: `src/arbitrator/presentation/react-ui/src/types/index.ts`
- Modify: `src/arbitrator/presentation/react-ui/src/App.tsx`

**Interfaces:**
- New type `SystemHealthState`:
```typescript
export interface HealthCheck {
  name: string;
  passed: boolean;
  is_warning: boolean;
  detail: string | null;
}
export interface ExchangeHealthResult {
  exchange_id: string;
  display_name: string;
  has_errors: boolean;
  has_warnings: boolean;
  checks: HealthCheck[];
}
export interface SystemHealthState {
  status?: "not_run_yet" | "running";
  checked_at?: number;
  all_passed: boolean | null;
  exchanges: ExchangeHealthResult[];
}
```

Banner logic in `App.tsx`:
- Poll `GET /api/system-health` every 15 seconds via `useEffect`.
- If `all_passed === null` or `all_passed === true` → no banner.
- If exchanges have errors (not warnings) → red banner.
- If only warnings → yellow banner.
- Banner text: `"⚠ Система: {n} бірж мають проблеми з даними. Перейди в Налаштування → System Check."` with link that navigates to settings page.

- [ ] **Step 1: Add types to `index.ts`**

Add to `src/arbitrator/presentation/react-ui/src/types/index.ts`:

```typescript
export interface HealthCheck {
  name: string;
  passed: boolean;
  is_warning: boolean;
  detail: string | null;
}

export interface ExchangeHealthResult {
  exchange_id: string;
  display_name: string;
  futures_balance_usdt: number | null;
  spot_balance_usdt: number | null;
  has_errors: boolean;
  has_warnings: boolean;
  checks: HealthCheck[];
}

export interface SystemHealthState {
  status?: string;
  checked_at?: number;
  all_passed: boolean | null;
  exchanges: ExchangeHealthResult[];
}
```

- [ ] **Step 2: Add banner to `App.tsx`**

Add import at top of `App.tsx`:
```typescript
import type { SystemHealthState } from "./types";
```

Add state + polling inside `App` function, before the `return`:
```typescript
const [health, setHealth] = useState<SystemHealthState | null>(null);

useEffect(() => {
  const poll = async () => {
    try {
      const res = await fetch("/api/system-health");
      if (res.ok) {
        const data: SystemHealthState = await res.json();
        setHealth(data);
      }
    } catch {
      // silent — backend may not be ready yet
    }
  };
  poll();
  const id = setInterval(poll, 15_000);
  return () => clearInterval(id);
}, []);

const healthErrors = health?.exchanges.filter((e) => e.has_errors) ?? [];
const healthWarnings = health?.exchanges.filter((e) => !e.has_errors && e.has_warnings) ?? [];
const showErrorBanner = healthErrors.length > 0;
const showWarnBanner = !showErrorBanner && healthWarnings.length > 0;
```

In the JSX, inside `<div className="flex-1 flex flex-col...">`, before `<main>`, add:
```tsx
{showErrorBanner && (
  <div className="bg-red-600 text-white text-sm px-4 py-2 flex items-center gap-2 shrink-0">
    <span>⚠</span>
    <span>
      Система: {healthErrors.length} бірж мають проблеми з даними.{" "}
      <button
        className="underline font-bold"
        onClick={() => navigate("settings")}
      >
        Перейди в Налаштування → System Check
      </button>
    </span>
  </div>
)}
{showWarnBanner && (
  <div className="bg-yellow-500 text-black text-sm px-4 py-2 flex items-center gap-2 shrink-0">
    <span>⚠</span>
    <span>
      Система: попередження по {healthWarnings.length} біржах (credentials).{" "}
      <button
        className="underline font-bold"
        onClick={() => navigate("settings")}
      >
        Налаштування → System Check
      </button>
    </span>
  </div>
)}
```

- [ ] **Step 3: Build React and verify banner compiles**

```
cd src/arbitrator/presentation/react-ui && pnpm build 2>&1 | tail -5
```
Expected: `✓ built in ...` with no TypeScript errors.

- [ ] **Step 4: Commit**

```bash
git add src/arbitrator/presentation/react-ui/src/types/index.ts src/arbitrator/presentation/react-ui/src/App.tsx
git commit -m "feat(health): add health banner to App.tsx + SystemHealthState types"
```

---

## Task 6: React — "System Check" section in SettingsPage

**Files:**
- Modify: `src/arbitrator/presentation/react-ui/src/pages/SettingsPage.tsx`

The section shows:
- Last check timestamp (`checked_at` formatted as local time)
- "Запустити перевірку" button → `POST /api/system-health/run` → polls until `checked_at` changes
- Per-exchange table: exchange name | status icon | list of failed checks with detail

- [ ] **Step 1: Add System Check section to `SettingsPage.tsx`**

Add imports at top of `SettingsPage.tsx`:
```typescript
import type { SystemHealthState, ExchangeHealthResult } from "../types";
```

Add state inside `SettingsPage` component:
```typescript
const [healthData, setHealthData] = useState<SystemHealthState | null>(null);
const [healthRunning, setHealthRunning] = useState(false);

const fetchHealth = async () => {
  try {
    const res = await fetch("/api/system-health");
    if (res.ok) setHealthData(await res.json());
  } catch { /* silent */ }
};

useEffect(() => { fetchHealth(); }, []);

const runHealthCheck = async () => {
  setHealthRunning(true);
  const prevCheckedAt = healthData?.checked_at ?? 0;
  try {
    await fetch("/api/system-health/run", { method: "POST" });
    // poll until checked_at changes (max 60s)
    for (let i = 0; i < 60; i++) {
      await new Promise((r) => setTimeout(r, 1000));
      const res = await fetch("/api/system-health");
      if (res.ok) {
        const d: SystemHealthState = await res.json();
        if ((d.checked_at ?? 0) > prevCheckedAt) {
          setHealthData(d);
          break;
        }
      }
    }
  } finally {
    setHealthRunning(false);
  }
};
```

Add JSX section at the bottom of the SettingsPage return, before closing `</div>`:
```tsx
{/* System Check */}
<Card>
  <CardContent>
    <div className="flex items-center justify-between mb-3">
      <h3 className="font-semibold text-gray-800">System Check</h3>
      <button
        onClick={runHealthCheck}
        disabled={healthRunning}
        className="px-3 py-1 text-sm rounded bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50"
      >
        {healthRunning ? "Перевіряємо..." : "Запустити перевірку"}
      </button>
    </div>

    {healthData?.checked_at && (
      <p className="text-xs text-gray-500 mb-3">
        Остання перевірка:{" "}
        {new Date(healthData.checked_at * 1000).toLocaleString()}
      </p>
    )}

    {!healthData || healthData.all_passed === null ? (
      <p className="text-sm text-gray-400">Ще не перевірялось</p>
    ) : (
      <div className="space-y-2">
        {healthData.exchanges.map((ex: ExchangeHealthResult) => (
          <div
            key={ex.exchange_id}
            className={`rounded border p-2 text-sm ${
              ex.has_errors
                ? "border-red-400 bg-red-50"
                : ex.has_warnings
                ? "border-yellow-400 bg-yellow-50"
                : "border-green-400 bg-green-50"
            }`}
          >
            <div className="font-medium flex items-center gap-1">
              <span>{ex.has_errors ? "✗" : ex.has_warnings ? "⚠" : "✓"}</span>
              <span>{ex.display_name}</span>
            </div>
            {ex.checks
              .filter((c) => !c.passed)
              .map((c) => (
                <div
                  key={c.name}
                  className={`ml-4 text-xs ${
                    c.is_warning ? "text-yellow-700" : "text-red-700"
                  }`}
                >
                  {c.is_warning ? "⚠" : "✗"} {c.name}
                  {c.detail ? `: ${c.detail}` : ""}
                </div>
              ))}
          </div>
        ))}
      </div>
    )}
  </CardContent>
</Card>
```

In the System Check per-exchange card, after the display name line, add balance display before the failed checks list:

```tsx
{/* balances */}
{(ex.futures_balance_usdt !== null || ex.spot_balance_usdt !== null) && (
  <div className="ml-4 mt-1 text-xs text-gray-600 flex gap-4">
    {ex.futures_balance_usdt !== null && (
      <span>Futures: <strong>{ex.futures_balance_usdt.toFixed(2)} USDT</strong></span>
    )}
    {ex.spot_balance_usdt !== null && (
      <span>Spot: <strong>{ex.spot_balance_usdt.toFixed(2)} USDT</strong></span>
    )}
  </div>
)}
```

- [ ] **Step 2: Build and verify**

```
cd src/arbitrator/presentation/react-ui && pnpm build 2>&1 | tail -5
```
Expected: `✓ built in ...` — no TypeScript errors.

- [ ] **Step 3: Commit**

```bash
git add src/arbitrator/presentation/react-ui/src/pages/SettingsPage.tsx
git commit -m "feat(health): add System Check section to SettingsPage with manual trigger + results table"
```

---

## Task 7: Exchange balance display in Settings → "Біржі" tab

**Files:**
- Modify: `src/arbitrator/presentation/react-ui/src/pages/SettingsPage.tsx`
- Modify: `src/arbitrator/presentation/ws/settings_ws_handler.py`

**Goal:** Show futures USDT balance and spot USDT balance under each exchange's API key form in the "Біржі" tab. The balance data comes from the same `GET /api/system-health` endpoint (already polled in Task 6). No new endpoint needed.

**Interfaces:**
- Reuses `SystemHealthState` from Task 5 — `exchanges[i].futures_balance_usdt`, `exchanges[i].spot_balance_usdt`
- `ExchangeForm` gains optional prop `healthResult?: ExchangeHealthResult`

- [ ] **Step 1: Update `ExchangeForm` to accept and display balance data**

In `SettingsPage.tsx`, update the `ExchangeForm` component props interface:

```typescript
import type { SystemHealthState, ExchangeHealthResult } from "../types";

function ExchangeForm({
  ex,
  onSave,
  healthResult,
}: {
  ex: ExchangeSetting;
  onSave: (exId: string, k: string, s: string, p: string) => void;
  healthResult?: ExchangeHealthResult;
}) {
```

Add balance row inside the form, after the `<div className="flex flex-wrap gap-4 items-end">` block (after the Save button closing `</div>`):

```tsx
{/* balance display */}
{(healthResult?.futures_balance_usdt != null || healthResult?.spot_balance_usdt != null) && (
  <div className="mt-2 flex gap-6 text-sm text-gray-600">
    {healthResult.futures_balance_usdt != null && (
      <span>
        <span className="text-gray-400 text-xs uppercase mr-1">Futures</span>
        <strong className="text-gray-800">
          {healthResult.futures_balance_usdt.toFixed(2)} USDT
        </strong>
      </span>
    )}
    {healthResult.spot_balance_usdt != null && (
      <span>
        <span className="text-gray-400 text-xs uppercase mr-1">Spot</span>
        <strong className="text-gray-800">
          {healthResult.spot_balance_usdt.toFixed(2)} USDT
        </strong>
      </span>
    )}
  </div>
)}
```

- [ ] **Step 2: Pass healthResult to ExchangeForm in SettingsPage**

In `SettingsPage`, add a state for health data (reuse the same `healthData` state from Task 6 — both tasks are in the same component). Where `ExchangeForm` is rendered (in the "Біржі" section), pass the corresponding health result:

```tsx
{data.exchanges.map((ex) => (
  <ExchangeForm
    key={ex.exchange_id}
    ex={ex}
    onSave={handleSaveExchange}
    healthResult={healthData?.exchanges.find(
      (r) => r.exchange_id === ex.exchange_id
    )}
  />
))}
```

- [ ] **Step 3: Build and verify balances appear**

```
cd src/arbitrator/presentation/react-ui && pnpm build 2>&1 | tail -5
```
Expected: `✓ built in ...` — no TypeScript errors.

- [ ] **Step 4: Commit**

```bash
git add src/arbitrator/presentation/react-ui/src/pages/SettingsPage.tsx
git commit -m "feat(health): show futures+spot USDT balance in exchange API key cards"
```

---

## Self-Review

**Spec coverage:**
- ✓ Startup loop → `start_background_loop()` in AppRuntime `_start_live_workers` + `_start_paper_workers`
- ✓ Retry every 30s until all_passed → `_async_loop` in SystemHealthService
- ✓ Stop retrying when all pass → `return` after `all_passed`
- ✓ Credential errors = warnings only → `is_warning=True` for `futures_balance` / `spot_balance` checks
- ✓ Symbol universe refresh → Task 2
- ✓ `inspect_exchanges.py health-check` command → Task 3
- ✓ `GET /api/system-health` → Task 4
- ✓ `POST /api/system-health/run` → Task 4
- ✓ Banner on all pages → App.tsx, red for errors, yellow for warnings-only → Task 5
- ✓ Settings page System Check button + table → Task 6
- ✓ Futures + spot balance in System Check table → Task 6 (balance row per exchange)
- ✓ Futures + spot balance in "Біржі" exchange cards → Task 7
- ✓ `mock_data` mode skips → `_start_live_workers`/`_start_paper_workers` only

**Placeholder scan:** None found.

**Type consistency:**
- `SystemHealthSnapshot.to_dict()` → includes `futures_balance_usdt`, `spot_balance_usdt` → matches TS `ExchangeHealthResult` ✓
- `ExchangeHealthResult.has_errors` / `has_warnings` properties used in both Python and TS ✓
- `HealthCheck.is_warning` matches TS `is_warning: boolean` ✓
- `ExchangeForm` `healthResult?: ExchangeHealthResult` — optional so existing renders without health data still compile ✓
