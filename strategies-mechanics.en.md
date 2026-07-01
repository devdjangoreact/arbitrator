# Arbitrage Strategy Mechanics

Common: two hedged legs (long + short); first leg in USDT, second in `Q` coins from first fill; futures open short first.
Both legs always use the **same asset** (same `BASE`, e.g. `DOGE/USDT` on both venues/markets).

### Terms and quote conventions

| Term | Meaning |
|------|---------|
| `spread` | Entry/exit edge in %, source depends on strategy type (basis, cross-price spread, funding-rate spread). |
| `commission` | Total exchange fees for 4 trades (open+close on both legs), in USDT. |
| `funding` | Net funding **cost** in USDT: `max(paid − received, 0)`. |

For all **two-exchange** strategies (§2, §3, §4, §5, §7), use one quote convention:
- **Entry**: short leg by **bid**, long leg by **ask**.
- **Exit**: short leg by **ask**, long leg by **bid**.

### General profit formula

```
profit = (spread_entry − spread_exit) × volume − commission − funding
```

| Variable | Meaning | Source |
|----------|---------|--------|
| `spread_entry` | Spread/basis/funding-spread at open, **%** | Prices or rates at entry |
| `spread_exit` | Same at close, **%** | Prices or rates at exit |
| `volume` | Position notional, **USDT** | Parameter / deposit × leverage |
| `commission` | Sum of 4 trades, **USDT** | notional × fee_rate per trade |
| `funding` | Net funding **cost** (paid − received; if negative net, use 0), **USDT** | notional × rate × periods |

**Display example:**

```
100 = (6 − 1) × 3000 − 25 − 25
       ↑ gross 150 USDT   ↑      ↑
```

`(6 − 1) × 3000 / 100 = 150` — spread in percent, divide by 100 when multiplying by USDT.

---

## 1. Spot + Futures (Single Exchange)

### Strategy Description

Long **spot** + short **futures** on the **same** exchange. Profit from **basis shrinkage** (futures premium over spot). Coin direction irrelevant.

### Mechanics

1. Spot buy (USDT) — buy cheaper.
2. Futures short (`Q`) — sell dearer.
3. Wait for basis to narrow.
4. Close: futures short → spot sell.

### Strategy Elements

| Element | What it is | Source |
|---------|------------|--------|
| `spread` (= basis) | `(futures − spot) / spot × 100` | Spot ask, futures bid |
| `volume` | USDT spot buy | Parameter / balance × leverage |
| `Q` | Coins for second leg | fill: `volume / spot_price` |
| `commission` | 4 trades: spot buy/sell, futures open/close | fee_rate × notional each |
| `funding` | Futures short leg only | API rate × notional × periods |
| `leverage` | Cross max 5x; isolated per balance | Parameter |

### Formula (words)

**Spread** — basis in %: how much futures is above spot.

**Profit** = basis shrinkage in % × USDT position − 4-trade fees − funding cost on short.

### Formula (numeric example)

```
spread_entry = 2.78%     ← futures 1.850 vs spot 1.800
spread_exit  = 0.27%     ← futures 1.825 vs spot 1.820
volume = 5000 USDT

109 = (2.78 − 0.27) × 5000 − 15 − 1
       ↑ 125.5 USDT gross  ↑comm  ↑fund
     (2.78 − 0.27) × 5000 / 100 = 125.5
```

### Risks

| Risk | Description |
|------|-------------|
| Counterparty | Both legs on one exchange |
| Basis not converging | Premium does not shrink |
| Adverse funding | Short pays when rate > 0 |
| Spot fees | Spot fee eats small basis |

---

## 2. Spot + Futures (Two Exchanges)

### Strategy Description

Same as §1, but spot on **X**, futures short on **Y**. Profit from basis shrinkage between X and Y.

### Mechanics

1. Spot buy X (USDT).
2. Futures short Y (`Q`).
3. Wait for basis to narrow.
4. Close: futures Y → spot X.

### Strategy Elements

| Element | What it is | Source |
|---------|------------|--------|
| `spread` (= basis) | `(futures_Y − spot_X) / spot_X × 100` | Books X and Y |
| `volume` | USDT spot buy | Parameter |
| `commission` | 4 trades on two exchanges | fee_rate X + Y |
| `funding` | Futures leg Y | API Y |
| `api_lag` | Fill vs signal error | API latency |

### Formula (words)

**Spread** — basis between spot X and futures Y in %.

**Profit** = (basis at entry − basis at exit) × volume − commission − funding.

### Formula (numeric example)

```
spread_entry = 3.22%     ← fill: spot_X 1.800, futures_Y 1.858 (signal was 3.33%)
spread_exit  = 0.27%     ← spot_X 1.815, futures_Y 1.820
volume = 5000 USDT

137 = (3.22 − 0.27) × 5000 − 10 − 0
       ↑ 147.5 gross     ↑commission
     (3.22 − 0.27) × 5000 / 100 = 147.5
```

### Risks

| Risk | Description |
|------|-------------|
| All from §1 | — |
| API lag | Actual spread worse than signal |
| Two counterparties | Doubled execution risk |

---

## 3. Futures–Futures Price Spread

### Strategy Description

Long where **cheaper**, short where **dearer**. Profit from **convergence** of cross-exchange price spread.

### Mechanics

1. Short dear exchange (USDT).
2. Long cheap exchange (`Q`).
3. Exit when `spread_exit ≤ target` (`target = spread_entry × convergence_target / 100`).
4. Close: short → long.

### Strategy Elements

| Element | What it is | Source |
|---------|------------|--------|
| `spread` | `(price_high − price_low) / price_low × 100` | Long ask, short bid |
| `volume` | USDT short leg | Parameter / deposit × leverage |
| `convergence_target_%` | Remaining spread as % of entry | Parameter |
| `commission` | 4 futures trades | fee_rate × notional |
| `funding` | Both legs while open | API; override if `\|rate\| > 1%` and we pay |
| min entry | **3%** | Parameter |

### Formula (words)

**Spread** — price difference between exchanges in %.

**Profit** = (spread at entry − spread at exit) × volume − commission − funding.

### Formula (numeric example)

```
spread_entry = 4.43%     ← Bybit 1.932 vs Bitget 1.850
spread_exit  = 1.28%     ← Bybit 1.894 vs Bitget 1.870
volume = 5000 USDT

140 = (4.43 − 1.28) × 5000 − 10 − 0
       ↑ 157.5 gross    ↑commission
     (4.43 − 1.28) × 5000 / 100 = 157.5
```

### Risks

| Risk | Description |
|------|-------------|
| Spread widens | Averaging or unrealized loss |
| Spread > 20% | Anomaly (listing/withdraw) |
| Adverse funding | Close before settlement |
| Slippage | Volume > book depth |

---

## 4. Funding — Rate Spread

### Strategy Description

Two exchanges, **one** settlement. **Spread** = `|funding_rate|` difference. Earn leg on max |rate|, hedge opposite. **1 period → close.**

### Mechanics

1. 1–5 min before settlement: `spread_entry ≥ 1%`.
2. Open earn + hedge (`Q`).
3. 1 settlement.
4. Close both legs.

### Strategy Elements

| Element | What it is | Source |
|---------|------------|--------|
| `spread` (= funding_spread) | `\|rate_A\| − \|rate_B\|`, **%** per period | API both exchanges |
| `spread_exit` | **0** | Close after 1 period |
| `volume` | USDT per leg | Parameter |
| `commission` | 4 trades | fee_rate |
| `funding` | Net cost if hedge pays more than earn receives | Settlement |
| min entry | **1%** | Parameter |

### Formula (words)

**Spread** — difference of absolute funding rates in %.

**Profit** = funding_spread × volume − commission − funding_cost.

### Formula (numeric example)

```
spread_entry = 1.31%     ← |MEXC −2.0%| − |Gate +0.69%| = 2.0 − 0.69
spread_exit  = 0%        ← 1 period → close
volume = 5000 USDT

55.5 = (1.31 − 0) × 5000 − 10 − 0
        ↑ 65.5 funding gross  ↑commission
    (1.31 − 0) × 5000 / 100 = 65.5
```

### Risks

| Risk | Description |
|------|-------------|
| Rate changes | Before settlement |
| Price spike | Minutes before settlement |
| Fees | 4 trades vs small gross |

---

## 5. Funding — Settlement Time Difference

### Strategy Description

Earn on **early** exchange (high |rate|, imminent settlement). Hedge on **late** (its funding = 0 — does not accrue). **1 early period → close.**

### Mechanics

1. Earn leg early (long/short by rate sign).
2. Hedge late.
3. Early settlement.
4. Close both (do not wait for late).

### Strategy Elements

| Element | What it is | Source |
|---------|------------|--------|
| `spread` (= \|rate_early\|) | Early exchange rate, **%** | API |
| `spread_exit` | **0** | Close after 1 period |
| `volume` | USDT per leg | Parameter |
| `commission` | 4 trades | fee_rate |
| `funding` | **0** on late leg; early in gross spread | §5 logic |

### Formula (words)

**Spread** — |rate| of early exchange in %.

**Profit** = |rate_early| × volume − commission + price_PnL (hedge incomplete — price may add ±).

### Formula (numeric example)

```
spread_entry = 2.0%      ← Coin rate −2.0%, long earn
spread_exit  = 0%
volume = 5000 USDT

48 = (2.0 − 0) × 5000 − 10 − 0 − 42
      ↑ 100 funding gross  ↑commission   ↑price net loss
    (2.0 − 0) × 5000 / 100 = 100
    price: long −170 + short +128 = −42
```

### Risks

| Risk | Description |
|------|-------------|
| Price >> funding | PnL from price leg |
| Early rate changes | Before settlement |
| Incomplete hedge | Different moves on exchanges |

---

## 6. Funding + Spot Hedge (Single Exchange)

### Strategy Description

**Futures** — earning leg (receives funding). **Spot** — price hedge. Both on the **same** exchange.

Profit from **funding payment** on futures. Spot does not earn — it offsets futures price PnL. Basis (futures premium over spot) is a **cost** if it changes while held.

Unlike §1: goal is **collect funding**, not wait for basis convergence. Unlike §4: hedge is **spot**, not futures on a second exchange.

### Mechanics

**Which leg receives funding:**

| `funding_rate` | Futures (earn) | Spot (hedge) |
|----------------|----------------|--------------|
| **> 0** | Short | Long (buy) |
| **< 0** | Long | Short (sell) |

**Open (rate > 0, typical case):**
1. Spot buy (USDT).
2. Futures short (`Q`).
3. 1 settlement.
4. Close: futures short → spot sell.

**Open (rate < 0):**
1. Spot sell (`Q` coins — requires spot coin balance).
2. Futures long (`Q`).
3. 1 settlement.
4. Close: futures long → spot buy.

**1 period → close.**

### Strategy Elements

| Element | What it is | Source |
|---------|------------|--------|
| `spread` (= \|rate\|) | Funding rate for 1 period, **%** | Futures API |
| `spread_exit` | **0** | Close after 1 period |
| `basis_%` | Futures premium over spot | Spot/futures prices; **cost** if basis rises |
| `volume` | USDT futures leg notional | Parameter / balance × leverage |
| `Q` | Coins | First leg fill |
| `commission` | 4 trades: spot + futures open/close | spot and futures fee_rate |
| min entry | **\|rate\| ≥ 1%** | Parameter |
| `entry_window` | 1–5 min before settlement | Parameter |

### Formula (words)

**Spread** — |funding_rate| on futures leg in %: how much % of notional we receive for 1 period.

**Profit** = |rate| × volume − commission − basis change loss (if basis worsened).

Basis loss: `(basis_exit − basis_entry) × volume / 100` — when premium rises with short futures + long spot.

### Formula (numeric example)

```
rate = +0.80%             ← short futures receives funding
spread_entry = 0.80%
spread_exit  = 0%
volume = 5000 USDT

Spot buy 5000 @ 1.800 → Q = 2778
Futures short 2778 @ 1.802
basis_entry = (1.802 − 1.800) / 1.800 = 0.11%

After 1 settlement:
Funding received = +5000 × 0.008 = +40 USDT

basis_exit = 0.15%        ← premium rose slightly → basis loss

28 = (0.80 − 0) × 5000 − 10 − 2
      ↑ 40 USDT funding    ↑commission ↑basis drift
    (0.80 − 0) × 5000 / 100 = 40
    basis drift: (0.15 − 0.11) × 5000 / 100 = 2 USDT
```

### Risks

| Risk | Description |
|------|-------------|
| Adverse basis | Premium rises — eats funding profit |
| Rate changes | Rate may drop before settlement |
| Spot sell (rate < 0) | Requires spot coin balance for hedge |
| Counterparty | Both legs on one exchange |
| Spot fees | 4 trades with spot fee — large share at small rate |

---

## 7. Funding + Spot Hedge (Two Exchanges)

### Strategy Description

Same as §6: **futures** receives funding, **spot** hedges price. Legs on **different** exchanges: spot on **X**, futures on **Y** (where |rate| ≥ threshold).

Profit from funding on Y. Spot on X offsets price PnL. Extra cost — **cross-basis** between spot X and futures Y + API lag between legs.

Unlike §2: goal is **funding**, not basis convergence; **1 period → close**. Unlike §6: two APIs, two counterparties, cross-basis instead of single-exchange basis.

### Mechanics

**Futures on Y (earn), spot on X (hedge):**

| `rate_Y` | Futures Y | Spot X |
|----------|-----------|--------|
| **> 0** | Short | Long (buy) |
| **< 0** | Long | Short (sell) |

**Open (rate > 0):**
1. Spot buy on X (USDT).
2. Futures short on Y (`Q`).
3. 1 settlement on Y.
4. Close: futures Y → spot sell X.

**Open (rate < 0):**
1. Spot sell on X (`Q` coins).
2. Futures long on Y (`Q`).
3. 1 settlement on Y.
4. Close: futures Y → spot buy X.

**1 period → close.**

### Strategy Elements

| Element | What it is | Source |
|---------|------------|--------|
| `spread` (= \|rate_Y\|) | Funding rate on exchange Y, **%** | API Y |
| `spread_exit` | **0** | Close after 1 period |
| `cross_basis_%` | `(futures_Y − spot_X) / spot_X × 100` | Books X and Y; **cost** if worsened |
| `volume` | USDT spot buy / futures notional | Parameter |
| `Q` | Coins | Spot X fill |
| `commission` | 4 trades on X and Y | fee_rate X + Y |
| `api_lag` | Fill vs signal error | Lag between legs |
| min entry | **\|rate_Y\| ≥ 1%** | Parameter |
| `entry_window` | 1–5 min before settlement Y | Parameter |

### Formula (words)

**Spread** — |funding_rate| on exchange Y in %.

**Profit** = |rate_Y| × volume − commission − cross-basis change loss − API lag slippage.

Cross-basis loss: `(cross_basis_exit − cross_basis_entry) × volume / 100` — when futures Y premium over spot X rises with short Y + long X.

### Formula (numeric example)

```
rate_Y = +1.0%            ← short futures Y receives funding
spread_entry = 1.0%
spread_exit  = 0%
volume = 5000 USDT

Spot buy X: 5000 @ 1.800 → Q = 2778
Futures short Y: 2778 @ 1.858 (signal 1.860, lag −0.11%)
cross_basis_entry = (1.858 − 1.800) / 1.800 = 3.22%

After 1 settlement Y:
Funding received = +5000 × 0.01 = +50 USDT

cross_basis_exit = 3.28%   ← drift +0.06 pp

35 = (1.0 − 0) × 5000 − 12 − 3
      ↑ 50 USDT funding   ↑commission ↑cross-basis drift
    (1.0 − 0) × 5000 / 100 = 50
    cross-basis drift: (3.28 − 3.22) × 5000 / 100 = 3 USDT
```

### Risks

| Risk | Description |
|------|-------------|
| All from §6 | — |
| Cross-basis drift | Premium between X and Y worsened — eats funding |
| API lag | Worse cross-basis on second leg fill |
| Two counterparties | Execution failure on one exchange |
| Different fees | Spot X + futures Y — different rates |

---

## Unified evaluation and formatting rules

### 1) Primary selection metric

`% to deposit` — higher is better for all strategies.

```
percent_to_deposit = net_profit_usdt / deposit_usdt × 100
```

where:
- `net_profit_usdt` is strategy net result in USDT;
- `deposit_usdt` is actual deposit/margin used for the position.

### 2) Rounding

- All **%** values are displayed with **2 decimal places**.
- All **USDT** values are displayed with **2 decimal places**.

### 3) Pre-entry mini-checklist

1. **same asset** — both legs must be the same asset (`BASE/USDT`), no mixed `BASE`.
2. **quotes side** — quotes are taken from correct side:
   - entry: short at `bid`, long at `ask`;
   - exit: short at `ask`, long at `bid`.
3. **fees loaded** — fees from both venues/markets are loaded and included in calculation.
4. **funding timestamp valid** — next settlement timestamp is current (not stale); funding rate matches that window.
