# Tasks: 002-strategy-engine

**Input**: [spec.md](./spec.md) · [plan.md](./plan.md) · [data-model.md](./data-model.md) · [research.md](./research.md) · [contracts/strategy-data-catalog.md](./contracts/strategy-data-catalog.md) · [quickstart.md](./quickstart.md)
**Architecture**: domain pure (`Decimal`, no I/O) → application (cache + workers + services) → presentation (WS only). Live = **exchange-only data**; missing data → `N/A` (no fabrication).
**Tests**: included — FR-019 explicitly requires automated coverage of strategy logic and risk/edge cases.

**Conventions**: one class per file, snake_case filename = class. New code under `src/arbitrator/`, tests under `tests/`. Numbers round to 2 places **only** in serializers.

---

## Phase 1: Setup

- [X] T001 Add strategy `Settings` fields to `src/arbitrator/config/settings.py`: `spot_enabled: bool = False`, `spot_default_type: str = "spot"`, `quote_max_age_seconds: float`, `book_max_age_seconds: float`, `funding_refresh_seconds: float`, `funding_entry_window_seconds: float`, `strategy_decimal_places: int = 2`, `anomaly_max_spread_pct: float`, `slippage_max_pct: float`, `prediction_enabled: bool = False`, `prediction_window_seconds: float`, `deposit_basis: Literal["position_margin","account_balance"] = "position_margin"`, `execution_rollback_enabled: bool = True`, `leg_imbalance_tolerance_pct: float`
- [X] T002 [P] Mirror every new field as `KEY=value` in `.env.example` with documented defaults
- [X] T003 [P] Create package dirs with `__init__.py`: `src/arbitrator/domain/strategy/`, `src/arbitrator/domain/strategy/strategies/`, and `tests/strategy/`

---

## Phase 2: Foundational — Domain core (pure, blocks all user stories)

**Goal**: stateless `Decimal` engine that computes all 6 strategies from a normalized snapshot, with a full `N/A` contract.
**Independent test** (quickstart A/B): `pytest tests/ -k strategy` — each of 6 strategies matches a numeric example from `strategies-mechanics`; risk cases produce `available=False` with the right reason. No exchanges needed.

### Value objects & results (data-model.md)

- [X] T004 [P] Create `StrategyKind` (Literal/Enum of 6 ids) in `src/arbitrator/domain/strategy/strategy_kind.py`
- [X] T005 [P] Create `Quote` (exchange_id, symbol, market_type, bid/ask/last `Decimal|None`, recv_time_ms) in `src/arbitrator/domain/strategy/quote.py`
- [X] T006 [P] Create `FundingInfo` (rate, next_rate, next_settlement_ms, recv_time_ms) in `src/arbitrator/domain/strategy/funding_info.py`
- [X] T007 [P] Create `FeeSchedule` (futures/spot maker/taker `Decimal|None`) in `src/arbitrator/domain/strategy/fee_schedule.py`
- [X] T008 Create `StrategyInputs` (symbol, short/long ex, futures/spot quotes maps, funding map, fees map, target_volume_usdt, leverage map, deposit_usdt, now_ms) in `src/arbitrator/domain/strategy/strategy_inputs.py`
- [X] T009 Create `StrategyResult` (strategy_id, available, unavailable_reason, spread_pct, price_short/long, fees_usdt, funding_usdt, volume_usdt, leverage, gross/costs/net, costs_breakdown, percent_to_deposit) in `src/arbitrator/domain/strategy/strategy_result.py`
- [X] T010 Create `StrategyTable` (symbol, results map, best_strategy_id, updated_at_ms) in `src/arbitrator/domain/strategy/strategy_table.py`

### Calculators & engine

- [X] T011 Define `StrategyCalculator` Protocol `compute(StrategyInputs) -> StrategyResult` in `src/arbitrator/domain/strategy/strategy_calculator.py`
- [X] T012 [P] Implement `futures_futures` (§3) in `src/arbitrator/domain/strategy/strategies/futures_futures_calculator.py`
- [X] T013 [P] Implement `futures_spot_2ex` (§2) in `src/arbitrator/domain/strategy/strategies/futures_spot_2ex_calculator.py`
- [X] T014 [P] Implement `futures_spot_1ex` (§1) in `src/arbitrator/domain/strategy/strategies/futures_spot_1ex_calculator.py`
- [X] T015 [P] Implement `funding_ff` (§4) in `src/arbitrator/domain/strategy/strategies/funding_ff_calculator.py`
- [X] T016 [P] Implement `funding_fs` (§6/§7) in `src/arbitrator/domain/strategy/strategies/funding_fs_calculator.py`
- [X] T017 [P] Implement `funding_diff_dates` (§5) in `src/arbitrator/domain/strategy/strategies/funding_diff_dates_calculator.py`
- [X] T018 Create `StrategyEngine` (inject calculator list, run available ones, compute `percent_to_deposit`, set `best_strategy_id`, return `StrategyTable`) in `src/arbitrator/domain/strategy/strategy_engine.py`

### Unit tests (FR-019, quickstart A/B)

- [X] T019 [P] Numeric-example tests (one per strategy) in `tests/strategy/test_calculators_numeric.py` — assert `net_profit_usdt` and `percent_to_deposit` vs `strategies-mechanics`
- [X] T020 [P] Risk/edge tests in `tests/strategy/test_calculators_edge.py` — no spot → `futures_spot_*`/`funding_fs` `reason=no_spot`; stale `next_settlement_ms` → funding strategies `N/A`; missing fees → `N/A`; stale quotes → `N/A`
- [X] T021 [P] Engine test in `tests/strategy/test_strategy_engine.py` — mixed availability, `best_strategy_id` selection, Decimal precision preserved internally

**Checkpoint**: domain engine green; SC-001/002/005/008 provable without exchanges.

---

## Phase 3: User Story 1 — Live 6-strategy calc on Screener (P1)

**Goal**: Screener live mode fills Ф-Ф … Ф різн. from real data; missing data → `N/A`; incremental recompute.
**Independent test** (quickstart C): live mode → `/ws/screener` columns are real numbers, `N/A` where data missing, no mock; logs show only changed symbols recomputed.

### Data sourcing (shared foundation for live; introduced here as earliest consumer)

- [X] T022 [US1] Add `bid`/`ask` (`float | None = None`) to `Ticker` in `src/arbitrator/domain/ticker.py` and populate them in `_to_ticker` in `src/arbitrator/exchanges/ccxt_base.py` (additive)
- [X] T023 [P] [US1] Define `MarketDataCache` Protocol (read Quote/FundingInfo/FeeSchedule by exchange_id+symbol+market_type) in `src/arbitrator/domain/market_data_cache.py`
- [ ] T024 [P] [US1] Define `SpotGateway` abstraction (spot price/fees/create_order) in `src/arbitrator/domain/spot_gateway.py` (deferred — FF-min: spot not required)
- [X] T025 [US1] Implement `MarketDataCacheMemory` (dict + lock, recv_time) in `src/arbitrator/application/market_data_cache_memory.py`
- [ ] T026 [US1] Create spot ccxt client (`defaultType=spot`, reuse `CcxtBase._base_client_config`) + register in `src/arbitrator/exchanges/factory.py` (market-type aware) (deferred — FF-min)
- [ ] T027 [US1] Implement `SpotStreamWorker` (`watch_ticker` spot → cache bid/ask/last) in `src/arbitrator/application/spot_stream_worker.py` (deferred — FF-min)
- [X] T028 [US1] Implement `FundingRateWorker` (periodic `fetch_funding_rates` → rate + next_settlement_ms → cache) in `src/arbitrator/application/funding_rate_worker.py` (gateway `fetch_funding_infos` on `ExchangeGateway`/`CcxtBase`)
- [X] T029 [US1] Implement `FeeSnapshotService` (`load_markets` maker/taker → `FeeSchedule` → cache) in `src/arbitrator/application/fee_snapshot_service.py` (gateway `fetch_fee_schedule`)
- [X] T030 [US1] Implement `StrategyInputsAssembler` (build `StrategyInputs` from cache + freshness/`N/A` gate using `quote_max_age_seconds`) in `src/arbitrator/application/strategy_inputs_assembler.py`

### Screener live path

- [X] T031 [US1] Implement `StrategyTableService` (incremental recompute of changed symbols → 6 net via `StrategyEngine`) in `src/arbitrator/application/strategy_table_service.py`
- [X] T032 [US1] Create `screener_serializer.py` (StrategyTable → `StrategyProfitsDto`, round at edge, `N/A` mapping) in `src/arbitrator/presentation/serializers/screener_serializer.py`
- [X] T033 [US1] Replace "live serializer not implemented" in `_live_loop` with real serialization + deltas in `src/arbitrator/presentation/ws/screener_ws_handler.py`
- [X] T034 [P] [US1] Integration test (mock cache) `tests/strategy/test_screener_serializer.py` — full data → numbers; partial → `N/A`; incremental recompute touches only changed symbols (SC-003/004)

**Checkpoint (FF-min)**: Screener live path wired — `futures_futures` shows real numbers; spot-dependent strategies degrade to `N/A` until spot sourcing (T024/T026/T027) lands. Live verification by operator (`UI_DATA_MODE=live`).

---

## Phase 4: User Story 2 — Detailed strategy calc on Opportunity (P1)

**Goal**: Opportunity «Розрахунок по стратегіях» full rows from real data; params/leverage changes recompute.
**Independent test** (quickstart D): `/ws/opportunity?symbol=&short=&long=` rows have all fields; `set_params`/`set_leverage` → dependent fields recompute.

- [X] T035 [US2] Implement `OpportunityStrategyService` (full rows for one symbol/pair via `StrategyEngine` + assembler) in `src/arbitrator/application/opportunity_strategy_service.py`
- [X] T036 [US2] Create `opportunity_serializer.py` (StrategyResult rows → `StrategyCalculationRowDto`, round at edge) in `src/arbitrator/presentation/serializers/opportunity_serializer.py`
- [X] T037 [US2] Replace "live mode not implemented" with live snapshot loop in `src/arbitrator/presentation/ws/opportunity_ws_handler.py`
- [~] T038 [US2] Handle `opportunity.set_params` (active_strategy_id, target_volume_usdt, thresholds) and `opportunity.set_leverage` → recompute (DONE); `set_leverage` REST deferred — `ExchangeGateway` has no leverage op yet (session-only update for now) in `src/arbitrator/presentation/ws/opportunity_ws_handler.py`
- [X] T039 [P] [US2] Test `tests/strategy/test_opportunity_serializer.py` — all fields populated; volume/leverage change updates fees/gross/net/`% to deposit` (SC-005)

**Checkpoint**: Opportunity detailed table live and recomputes on operator input.

---

## Phase 5: User Story 3 — Open/close signals + checklist + anomaly guard (P2)

**Goal**: emit `open`/`close` signals by thresholds; pre-entry checklist blocks invalid entries; anomalies block auto-entry.
**Independent test** (quickstart E): spread ≥ open threshold + valid checklist → `open` signal; invalid checklist item → no entry signal, reason logged.

- [X] T040 [P] [US3] Create `ChecklistResult` in `src/arbitrator/domain/strategy/checklist_result.py`
- [X] T041 [P] [US3] Create `TradeSignal` in `src/arbitrator/domain/strategy/trade_signal.py`
- [X] T042 [US3] Implement `ChecklistEvaluator` (same_asset, quotes_side_ok, fees_loaded, funding_ts_valid) in `src/arbitrator/application/checklist_evaluator.py`
- [X] T043 [US3] Implement `AnomalyGuard` (max spread, stale data, depth/balance → block) in `src/arbitrator/application/anomaly_guard.py`
- [X] T044 [US3] Implement `SignalService` (open/close by thresholds, gated by checklist + anomaly guard, structured logging) in `src/arbitrator/application/signal_service.py`
- [X] T045 [P] [US3] Tests `tests/strategy/test_signal_service.py` — open above threshold with valid checklist; blocked on stale funding ts; anomaly blocks auto-entry (FR-008/009/015)

**Checkpoint**: signals reliably gate entries; no signal on invalid checklist.

---

## Phase 6: User Story 4 — Real hedged execution (P2)

**Goal**: real orders for open/accumulate/close (partial+full) on both legs, state from exchange fills, rollback on one-leg failure.
**Independent test** (quickstart F, small volumes): `accumulate` → real fills on both legs from exchange; partial close 25% → both legs ~−25%, imbalance ≤ tolerance; simulated leg failure → `rolled_back`, no unhedged leg.

- [X] T046 [P] [US4] Create `ExecutionOutcome` (+ `ExecutionStatus`, `LegExecution`) in `src/arbitrator/domain/strategy/execution_outcome.py`; narrow `FuturesExecutionGateway` Protocol in `src/arbitrator/domain/strategy/futures_execution_gateway.py`
- [ ] T047 [US4] Implement spot order path in `SpotGateway` impl (ccxt `defaultType=spot` `create_order`, idempotent `clientOrderId`) in `src/arbitrator/exchanges/` + factory wiring (deferred — FF-min: futures-futures hedged execution only; spot legs still `N/A`)
- [X] T048 [US4] Implement `HedgedExecutionService` (open/accumulate/close_partial/close_all both futures legs; via existing `open/close_market_position`; position state from `fetch_open_positions`) in `src/arbitrator/application/hedged_execution_service.py`
- [X] T049 [US4] Add rollback/compensation on one-leg failure (gated by `execution_rollback_enabled`) inside `src/arbitrator/application/hedged_execution_service.py`
- [~] T050 [US4] Wire `opportunity.accumulate`/`close_partial`/`close_all` commands → `HedgedExecutionService` (DONE); auto-accumulate/auto-close on valid signal+checklist still pending (SignalService not yet driven by a live auto-loop) in `src/arbitrator/presentation/ws/opportunity_ws_handler.py`
- [X] T051 [P] [US4] Tests `tests/strategy/test_hedged_execution.py` (fake gateways) — partial close imbalance ≤ tolerance (SC-006); leg failure → rollback, no unhedged exposure (SC-007); actual fills used, not intent (FR-012); dry-run places no orders

**Checkpoint**: real hedged open/accumulate/close with rollback safety.

---

## Phase 7: User Story 5 — Advisory prediction score (P3)

**Goal**: lightweight advisory score (spread trend Δ, stability, time-to-funding); toggleable; never blocks core calc.
**Independent test**: widening spread → higher score; prediction off → calc/signals unaffected.

- [X] T052 [P] [US5] Create `PredictionScore` in `src/arbitrator/domain/strategy/prediction_score.py`
- [X] T053 [US5] Implement `PredictionService` (short-history trend/stability + seconds_to_funding, gated by `prediction_enabled`) in `src/arbitrator/application/prediction_service.py`
- [X] T054 [P] [US5] Tests `tests/strategy/test_prediction_service.py` — widening → higher score; disabled → no effect on calc (FR-016)

---

## Phase 8: Polish & Cross-Cutting

- [~] T055 Wire new workers/services in `src/arbitrator/application/app_runtime.py` and `main.py` — start funding/fee workers **only** when `ui_data_mode=live`; inject cache + engine + services (DONE for FF-min: cache + `StrategyEngine` + `StrategyTableService` + `FundingRateWorker`/`FeeSnapshotService`; spot worker pending T027)
- [ ] T056 [P] Documentation sync — update `.cursor/rules/architecture.mdc` (new `domain/strategy/*`, services, Settings fields) per documentation-sync rule
- [ ] T057 [P] Verify structured logging for signal/decision/execution/failure/data-degradation events per `.cursor/rules/logging.mdc` (FR-017)
- [ ] T058 Run `mypy --strict` + lint on all new modules; fix `Any`/typing gaps
- [ ] T059 Execute quickstart C–F end-to-end on small volumes; confirm SC-001..SC-008

---

## Phase 9: Frontend & FastAPI surfacing + live verification (required for browser acceptance)

**Why**: the operator can only validate this feature from the browser. The current `001` DTOs/JS
render strategy values as plain numbers (`float`) and cannot show `N/A`, the `unavailable_reason`,
data freshness, or `% до депозиту` (the FR-004 main metric). Without this slice SC-002/SC-005 are
not observable in the UI. See handoff prompt for 001 in `specs/001-mockup-ui/spec.md`.

### Contract (DTO) — additive, mock-compatible

- [X] T060 [US1] Make screener net fields nullable in `src/arbitrator/presentation/dto/screener_dto.py` — `StrategyProfitsDto` six fields → `float | None` (None ⇒ `N/A`)
- [X] T061 [US2] Extend `StrategyCalculationRowDto` in `src/arbitrator/presentation/dto/opportunity_dto.py` — add `percent_to_deposit: float | None`, `unavailable_reason: str | None`; make `net_profit_usdt`/`gross_profit_usdt` `float | None`
- [X] T062 [P] Update `MockDataProvider` in `src/arbitrator/presentation/mock/mock_data_provider.py` to populate the new fields (incl. at least one `N/A` example) so mock stays a faithful contract

### FastAPI / serializer

- [X] T063 [US1] In `screener_serializer.py` map unavailable strategies → `None` (never 0); keep deltas working with nullable fields
- [ ] T064 [US2] In `opportunity_serializer.py` populate `percent_to_deposit`, `unavailable_reason`; round at edge only

### Frontend (static JS + HTML partial)

- [X] T065 [US1] Render `N/A` for null strategy profits in `src/arbitrator/presentation/static/js/render/screener.js` (`buildScreenerRow` strategy loop) — no `+/-0`, neutral styling for `N/A`
- [X] T066 [US2] Add `% до депозиту` column + `N/A`/reason tooltip in `src/arbitrator/presentation/static/js/render/opportunity.js` strategy-rows render
- [X] T067 [P] [US2] Add `% до депозиту` header column to `src/arbitrator/presentation/static/partials/opportunity/strategy-table.html` and rebuild via `python scripts/build_ui.py`
- [X] T068 [P] [US1] Surface data-freshness / connection indicator in screener meta (`renderScreenerMeta`) — show stale/disconnected so `N/A` is distinguishable from a bug (reads existing connection state; no new exchange channel)

### Read-only verification script (second check path, no trading)

- [ ] T069 Create `scripts/inspect_strategies.py` (read-only) — warm cache (futures bid/ask + spot + funding + fees), build `StrategyInputs` for a `--symbol --short --long`, run `StrategyEngine`, print per-strategy availability/`unavailable_reason`/net/`percent_to_deposit`. Delegates to a read-only inspector per `.cursor/skills/exchange-read-only-inspect/`; MUST NOT place orders
- [~] T070 [P] [US4] `HedgedExecutionService(dry_run=True)` simulation path (no real orders) implemented + covered by `test_dry_run_places_no_orders`; `quickstart.md` § F doc update still pending

### Plan consistency

- [ ] T071 [P] Reconcile docs — confirm `plan.md`/`data-model.md`/`research.md` no longer claim "DTO не змінюються"; FR-007 in `spec.md` reads as additive contract change

**Checkpoint**: operator opens `/` in live mode and sees real numbers, `N/A` with reason, `% до депозиту`, and a freshness/connection indicator — feature is acceptance-testable from the browser.

---

## Phase 10: Clarification follow-ups (C1–C11 from spec)

Encode the operator decisions. These refine existing phases — schedule each next to its phase.

- [ ] T072 [Phase 2] Encode `deposit_usdt = Σ(notional_leg / leverage_leg)` (spot 1×) and `percent_to_deposit` in `StrategyEngine`/calculators; `float→Decimal` via `str` everywhere (C2, C6)
- [ ] T073 [Phase 2] Encode funding sign rule `funding = max(paid − received, 0)` with per-leg direction (side × rate sign) in every funding-aware calculator; add a dedicated sign test in `tests/strategy/test_funding_sign.py` (C3, FR-022)
- [ ] T074 [Phase 2] Add scenario test `tests/strategy/test_futures_futures_funding_timing.py` — close-before-settlement vs hold, reopen-if-profitable, accounting extra commissions; assert chosen path maximizes net (C9, FR-026)
- [ ] T075 [Phase 3] In `StrategyInputsAssembler` take a single lock-guarded cache read → immutable `StrategyInputs` (no torn reads); freshness gate at assembly (C5, FR-025)
- [ ] T076 [Phase 3/4] Active-strategy selection: default `futures_futures`, pick exchange pair by max cross-price spread; later pick max `percent_to_deposit` among available — in `StrategyTableService`/`OpportunityStrategyService` (C1, FR-020)
- [ ] T077a [Phase 4] Create `PositionGroup` domain model (BASE asset, legs `[{exchange_id, market_type, side, qty/contracts, entry_price, leverage, mark_price, funding_accrued}]`, resolved `strategy_id`, `strategy_class`, `confidence`, `resolved_by`) in `src/arbitrator/domain/strategy/position_group.py` (C7)
- [ ] T077b [Phase 4] Implement `PositionGroupBuilder` — reconstruct groups from exchange state (`watch_positions`/`fetch_positions` + spot balances + `fetch_my_trades`/`fetch_funding_history`), pair legs by `BASE`+opposite side+`Q` tolerance+exchange/market pair, never from memory/markers in `src/arbitrator/application/position_group_builder.py` (C7, FR-023)
- [ ] T077c [Phase 4] Implement `StrategyClassifier` — leg topology → class (`2x_futures` / `fut_spot_1ex` / `fut_spot_2ex`); resolve exact strategy via settlement-time delta, `|funding_rate|`/window, `arb_markers` hint, operator selection (priority); default to basis strategy on ambiguity; emit `confidence`/`resolved_by` in `src/arbitrator/application/strategy_classifier.py` (C7)
- [ ] T077d [Phase 4] Implement `StrategyReconciliationService` — on startup/reconnect build groups + classify + compute live metrics (net, `% до депозиту`) from exchange state; expose for Opportunity reopen and Orders section in `src/arbitrator/application/strategy_reconciliation_service.py` (C7, FR-023)
- [ ] T077e [P] [Phase 4] Tests `tests/strategy/test_strategy_reconciliation.py` — group matching by BASE/Q/side; class detection; ambiguous class → default + operator override wins; metrics from exchange state, not memory (FR-023)
- [ ] T078 [Phase 2/6] Resolve `funding_fs` §6/§7 branch in `funding_fs_calculator.py` — §6 if spot on earn-exchange else §7 (cross-basis); if both available pick better `percent_to_deposit`; tests for both branches (C11)
- [ ] T079 [Phase 3] Rate-limit mitigation + optional proxy: batch `fetch_funding_rates`/fees, honor ccxt `rateLimit`, wire `exchange_proxies`/`public_ws_proxy_url` from `Settings` into ccxt client config in `src/arbitrator/exchanges/ccxt_base.py` (C8, FR-024)
- [ ] T080 [Phase 6] No-keys / private-data verification: when credentials absent → `deposit`/execution degrade to `N/A`/disabled; document read-only check via `.cursor/skills/exchange-read-only-inspect/` + `scripts/inspect_exchanges.py` (C10)

---

## Dependencies & Execution Order

- **Phase 1 (Setup)** → blocks everything.
- **Phase 2 (Foundational domain)** → blocks US1–US4 (engine + models are shared).
- **US1 (Phase 3)** introduces data sourcing → prerequisite for US2, US3, US4.
- **US2 (Phase 4)** depends on US1 data sourcing + assembler.
- **US3 (Phase 5)** depends on US1 inputs/engine; independent of US2 UI.
- **US4 (Phase 6)** depends on US3 signals (auto modes) + US1 sourcing.
- **US5 (Phase 7)** depends only on spread history from US1; independent of US2–US4.
- **Phase 9 (Frontend/FastAPI surfacing)**: DTO/serializer tasks (T060–T064) gate the JS tasks
  (T065–T068); they belong to US1/US2 acceptance and should land **with** Phase 3/4, not after.
  T069 (verification script) depends on Phase 2 engine + Phase 3 sourcing. T070 depends on US4.
- **Phase 8 (Polish)** last.

## Parallel Opportunities

- Phase 1: T002, T003 in parallel after T001.
- Phase 2 value objects: T004–T007 parallel; calculators T012–T017 parallel after T011; tests T019–T021 parallel after engine.
- Phase 3: T023, T024 parallel; serializer test T034 parallel with later wiring.
- Cross-story: once Phase 3 data sourcing lands, US3 (signals) and US5 (prediction) can proceed in parallel with US2.

## Implementation Strategy (MVP first)

1. **MVP** = Phase 1 + Phase 2 + Phase 3 (US1) **+ Phase 9 US1 slice** (T060, T062, T063, T065, T068):
   live 6-strategy Screener from real data, observable in the browser with `N/A`/freshness — delivers
   core value and is acceptance-testable (SC-001/002/003/004/005/008). Use T069 as a no-UI check path.
2. Add **US2** + Phase 9 US2 slice (T061, T064, T066, T067) for operator decision detail + `% до депозиту`.
3. Add **US3 + US4** for signals and real hedged execution (verify execution with T070 `--dry-run` first).
4. **US5** advisory and **Phase 8** polish last.
