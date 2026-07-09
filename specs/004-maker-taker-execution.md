# Spec 004: Maker-Taker Execution Flow

## Overview
Currently, the `Futures-Futures` strategy executes using a sequential taker-taker approach: it sends a market order for the short leg, waits for the fill, and then sends a market order for the long leg. Due to latency (`desync_ms`), the initial favorable spread often vanishes before execution, resulting in slippage and unprofitable trades.

This feature proposes a **Maker-Taker** execution flow to lock in favorable spreads and reduce fee costs.

## Proposed Flow
1. **Limit Order (Maker) on Leg 1:** Place a Post-Only (or standard limit) order for the first leg at the desired spread price.
2. **Wait for Fill:** Asynchronously monitor the limit order until it is filled (partially or fully).
3. **Market Order (Taker) on Leg 2:** Once the Maker order fills, immediately hedge by sending a Market order for the exact filled amount on the second exchange.
4. **Timeout/Cancel:** If the Maker order does not fill within a specific time window (`maker_timeout_seconds`), cancel it. If partially filled, cancel the remainder and hedge the filled portion.

## Settings to Add
- `maker_taker_enabled: bool` (Default: `False`)
- `maker_timeout_seconds: float` (e.g., `10.0`)

## Architectural Changes
- Modify `HedgedExecutionService._enter()` to support this alternate execution path.
- Requires robust order tracking via WebSocket (`watch_orders` / `watch_my_trades`) or aggressive REST polling to immediately react to Maker fills.
- Handle partial fills gracefully to avoid unhedged exposure.
