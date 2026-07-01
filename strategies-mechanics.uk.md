# Механіка арбітражних стратегій

Спільне: дві хеджовані ноги (long + short); перша нога — USDT, друга — `Q` монет з fill першої; futures відкривають short першим.
Обидві ноги завжди для **одного й того самого активу** (той самий `BASE`, напр. `DOGE/USDT` на обох майданчиках/ринках).

### Терміни та конвенція котирувань

| Термін | Значення |
|--------|----------|
| `спред` | Край входу/виходу у %, джерело залежить від типу стратегії (basis, cross-price spread, funding-rate spread). |
| `комісія` | Сума біржових fee за 4 угоди (open+close обох ніг), у USDT. |
| `фандінг` | Чисті **витрати** на funding у USDT: `max(заплатили − отримали, 0)`. |

Для всіх стратегій на **двох біржах** (§2, §3, §4, §5, §7) одна конвенція котирувань:
- **Вхід**: short-нога по **bid**, long-нога по **ask**.
- **Вихід**: short-нога по **ask**, long-нога по **bid**.

### Загальна формула прибутку

```
прибуток = (спред_входу − спред_виходу) × обʼєм − комісія − фандінг
```

| Змінна | Що означає | Звідки |
|--------|------------|--------|
| `спред_входу` | Spread/basis/funding-spread на відкритті, **%** | Розрахунок з цін або rates на entry |
| `спред_виходу` | Те саме на закритті, **%** | Розрахунок на exit |
| `обʼєм` | Notional позиції, **USDT** | Параметр / deposit × leverage |
| `комісія` | Сума за 4 угоди, **USDT** | notional × fee_rate кожної угоди |
| `фандінг` | Чистий funding **витрати** (заплатили − отримали, якщо в минус — 0), **USDT** | notional × rate × periods |

**Приклад відображення:**

```
100 = (6 − 1) × 3000 − 25 − 25
       ↑ gross 150 USDT   ↑      ↑
```

`(6 − 1) × 3000 / 100 = 150` — спред у відсотках, ділимо на 100 при множенні на USDT.

---

## 1. Спот + фʼючерс (одна біржа)

### Опис стратегії

Long **spot** + short **futures** на **одній** біржі. Прибуток — від **зменшення basis** (premium futures над spot). Напрямок монети не важливий.

### Механіка

1. Spot buy (USDT) — купуємо дешевше.
2. Futures short (`Q`) — продаємо дорожче.
3. Чекаємо звуження basis.
4. Close: futures short → spot sell.

### Елементи стратегії

| Елемент | Що це | Звідки |
|---------|--------|--------|
| `спред` (= basis) | `(futures − spot) / spot × 100` | Ціни spot ask, futures bid |
| `обʼєм` | USDT spot buy | Параметр / баланс × leverage |
| `Q` | Монети другої ноги | fill: `обʼєм / spot_price` |
| `комісія` | 4 угоди: spot buy/sell, futures open/close | fee_rate × notional кожної |
| `фандінг` | Тільки futures short leg | API rate × notional × periods |
| `leverage` | Cross max 5x; isolated — за балансом | Параметр |

### Формула (слова)

**Спред** — basis у %: на скільки futures дорожчий за spot.

**Прибуток** = скільки % basis звузився × USDT позиції − комісії за 4 угоди − funding витрати на short.

### Формула (приклад з цифрами)

```
спред_входу = 2.78%     ← futures 1.850 vs spot 1.800
спред_виходу = 0.27%    ← futures 1.825 vs spot 1.820
обʼєм = 5000 USDT

109 = (2.78 − 0.27) × 5000 − 15 − 1
       ↑ 125.5 USDT gross  ↑комісія ↑фандінг
     (2.78 − 0.27) × 5000 / 100 = 125.5
```

### Ризики

| Ризик | Суть |
|-------|------|
| Контрагент | Обидві ноги на одній біржі |
| Basis не сходиться | Premium не зменшується |
| Funding проти | Short платить при rate > 0 |
| Комісії spot | Spot fee зʼїдає малий basis |

---

## 2. Спот + фʼючерс (дві біржі)

### Опис стратегії

Як §1, але spot на біржі **X**, futures short на **Y**. Прибуток — від зменшення basis між X і Y.

### Механіка

1. Spot buy X (USDT).
2. Futures short Y (`Q`).
3. Чекаємо звуження basis.
4. Close: futures Y → spot X.

### Елементи стратегії

| Елемент | Що це | Звідки |
|---------|--------|--------|
| `спред` (= basis) | `(futures_Y − spot_X) / spot_X × 100` | Book X і Y |
| `обʼєм` | USDT spot buy | Параметр |
| `комісія` | 4 угоди на двох біржах | fee_rate X + Y |
| `фандінг` | Futures leg Y | API Y |
| `api_lag` | Похибка fill vs сигнал | Затримка API |

### Формула (слова)

**Спред** — basis між spot X і futures Y у %.

**Прибуток** = (basis на вході − basis на виході) × обʼєм − комісія − фандінг.

### Формула (приклад з цифрами)

```
спред_входу = 3.22%     ← fill: spot_X 1.800, futures_Y 1.858 (сигнал був 3.33%)
спред_виходу = 0.27%    ← spot_X 1.815, futures_Y 1.820
обʼєм = 5000 USDT

137 = (3.22 − 0.27) × 5000 − 10 − 0
       ↑ 147.5 gross     ↑комісія
     (3.22 − 0.27) × 5000 / 100 = 147.5
```

### Ризики

| Ризик | Суть |
|-------|------|
| Усе з §1 | — |
| API lag | Фактичний спред гірший за сигнал |
| Два контрагенти | Подвоєний execution risk |

---

## 3. Фʼючерс–фʼючерс, курсовий спред

### Опис стратегії

Long де **дешевше**, short де **дорожче**. Прибуток — від **зближення** курсового spread між біржами.

### Механіка

1. Short дорога біржа (USDT).
2. Long дешева біржа (`Q`).
3. Exit коли `спред_виходу ≤ target` (`target = спред_входу × convergence_target / 100`).
4. Close: short → long.

### Елементи стратегії

| Елемент | Що це | Звідки |
|---------|--------|--------|
| `спред` | `(price_high − price_low) / price_low × 100` | Ask long-біржі, bid short-біржі |
| `обʼєм` | USDT short leg | Параметр / deposit × leverage |
| `convergence_target_%` | Залишковий spread у % від entry | Параметр |
| `комісія` | 4 угоди futures | fee_rate × notional |
| `фандінг` | Обидві ноги поки відкрита | API; override якщо `\|rate\| > 1%` і платимо |
| min entry | **3%** | Параметр |

### Формула (слова)

**Спред** — різниця цін між біржами у %.

**Прибуток** = (spread на вході − spread на виході) × обʼєм − комісія − фандінг.

### Формула (приклад з цифрами)

```
спред_входу = 4.43%     ← Bybit 1.932 vs Bitget 1.850
спред_виходу = 1.28%    ← Bybit 1.894 vs Bitget 1.870
обʼєм = 5000 USDT

140 = (4.43 − 1.28) × 5000 − 10 − 0
       ↑ 157.5 gross    ↑комісія
     (4.43 − 1.28) × 5000 / 100 = 157.5
```

### Ризики

| Ризик | Суть |
|-------|------|
| Spread росте | Доусереднення або unrealized loss |
| Spread > 20% | Аномалія (лістинг/withdraw) |
| Funding проти | Close до settlement |
| Slippage | Обʼєм > стакан |

---

## 4. Funding — spread ставок

### Опис стратегії

Дві біржі, **один** settlement. **Спред** = різниця `|funding_rate|`. Earn leg на max |rate|, hedge — протилежна. **1 period → close.**

### Механіка

1. За 1–5 хв до settlement: `спред_входу ≥ 1%`.
2. Open earn + hedge (`Q`).
3. 1 settlement.
4. Close обидві ноги.

### Елементи стратегії

| Елемент | Що це | Звідки |
|---------|--------|--------|
| `спред` (= funding_spread) | `\|rate_A\| − \|rate_B\|`, **%** за 1 period | API обох бірж |
| `спред_виходу` | **0** | Закриваємо після 1 period |
| `обʼєм` | USDT на leg | Параметр |
| `комісія` | 4 угоди | fee_rate |
| `фандінг` | Net витрати: hedge платить − earn отримує (якщо net negative для нас) | Settlement |
| min entry | **1%** | Параметр |

### Формула (слова)

**Спред** — різниця модулів funding rate у %.

**Прибуток** = funding_spread × обʼєм − комісія − фандінг_витрати.

### Формула (приклад з цифрами)

```
спред_входу = 1.31%     ← |MEXC −2.0%| − |Gate +0.69%| = 2.0 − 0.69
спред_виходу = 0%       ← 1 period → close
обʼєм = 5000 USDT

55.5 = (1.31 − 0) × 5000 − 10 − 0
        ↑ 65.5 funding gross  ↑комісія
    (1.31 − 0) × 5000 / 100 = 65.5
```

### Ризики

| Ризик | Суть |
|-------|------|
| Rate змінюється | До settlement |
| Price spike | За хвилини до settlement |
| Комісії | 4 угоди vs малий gross |

---

## 5. Funding — різниця часу settlement

### Опис стратегії

Earn на **early** біржі (високий |rate|, settlement скоро). Hedge на **late** (її funding = 0 — не встигає). **1 period early → close.**

### Механіка

1. Earn leg early (long/short за знаком rate).
2. Hedge late.
3. Settlement early.
4. Close обидві (late не чекаємо).

### Елементи стратегії

| Елемент | Що це | Звідки |
|---------|--------|--------|
| `спред` (= |rate_early|) | Ставка early-біржі, **%** | API |
| `спред_виходу` | **0** | Close після 1 period |
| `обʼєм` | USDT на leg | Параметр |
| `комісія` | 4 угоди | fee_rate |
| `фандінг` | **0** на late leg; early — в gross spread | Логіка §5 |

### Формула (слова)

**Спред** — |rate| early-біржі у %.

**Прибуток** = |rate_early| × обʼєм − комісія + price_PnL (хедж неповний — price може дати ±).

### Формула (приклад з цифрами)

```
спред_входу = 2.0%      ← Coin rate −2.0%, long earn
спред_виходу = 0%
обʼєм = 5000 USDT

48 = (2.0 − 0) × 5000 − 10 − 0 − 42
      ↑ 100 funding gross  ↑комісія   ↑price net loss
    (2.0 − 0) × 5000 / 100 = 100
    price: long −170 + short +128 = −42 (не в spread, але в total)
```

### Ризики

| Ризик | Суть |
|-------|------|
| Price >> funding | PnL з price leg, не з funding |
| Rate early змінюється | До settlement |
| Неповний хедж | Різний рух на біржах |

---

## 6. Funding + spot hedge (одна біржа)

### Опис стратегії

**Futures** — заробляюча нога (отримує funding). **Spot** — хедж від руху ціни. Обидві на **одній** біржі.

Прибуток — від **funding payment** на futures. Spot не заробляє — він компенсує price PnL futures. Basis (premium futures vs spot) — **витрата**, якщо змінився за час утримання.

Відмінність від §1: мета — **забрати funding**, не чекати convergence basis. Відмінність від §4: хедж **spot**, не futures на другій біржі.

### Механіка

**Яка нога отримує funding:**

| `funding_rate` | Futures (earn) | Spot (hedge) |
|----------------|----------------|--------------|
| **> 0** | Short | Long (buy) |
| **< 0** | Long | Short (sell) |

**Відкриття (rate > 0, типовий кейс):**
1. Spot buy (USDT).
2. Futures short (`Q`).
3. 1 settlement.
4. Close: futures short → spot sell.

**Відкриття (rate < 0):**
1. Spot sell (`Q` монет — потрібен spot-баланс монет).
2. Futures long (`Q`).
3. 1 settlement.
4. Close: futures long → spot buy.

**1 period → close.**

### Елементи стратегії

| Елемент | Що це | Звідки |
|---------|--------|--------|
| `спред` (= \|rate\|) | Ставка funding за 1 period, **%** | API futures |
| `спред_виходу` | **0** | Close після 1 period |
| `basis_%` | Premium futures над spot | Ціни spot/futures; **витрата** якщо basis виріс |
| `обʼєм` | USDT notional futures leg | Параметр / баланс × leverage |
| `Q` | Монети | Fill першої ноги |
| `комісія` | 4 угоди: spot + futures open/close | fee_rate spot і futures |
| min entry | **\|rate\| ≥ 1%** | Параметр |
| `entry_window` | 1–5 хв до settlement | Параметр |

### Формула (слова)

**Спред** — |funding_rate| futures leg у %: скільки % notional отримаємо за 1 period.

**Прибуток** = |rate| × обʼєм − комісія − втрата від зміни basis (якщо basis погіршився).

Basis-втрата: `(basis_виходу − basis_входу) × обʼєм / 100` — якщо premium виріс при short futures + long spot.

### Формула (приклад з цифрами)

```
rate = +0.80%             ← short futures отримує funding
спред_входу = 0.80%
спред_виходу = 0%
обʼєм = 5000 USDT

Spot buy 5000 @ 1.800 → Q = 2778
Futures short 2778 @ 1.802
basis_входу = (1.802 − 1.800) / 1.800 = 0.11%

Після 1 settlement:
Funding received = +5000 × 0.008 = +40 USDT

basis_виходу = 0.15%      ← premium трохи виріс → втрата на basis

28 = (0.80 − 0) × 5000 − 10 − 2
      ↑ 40 USDT funding    ↑комісія ↑basis drift
    (0.80 − 0) × 5000 / 100 = 40
    basis drift: (0.15 − 0.11) × 5000 / 100 = 2 USDT
```

### Ризики

| Ризик | Суть |
|-------|------|
| Basis проти | Premium зростає — зʼїдає funding profit |
| Rate змінюється | До settlement rate може впасти |
| Spot sell (rate < 0) | Потрібен spot-баланс монет для hedge |
| Контрагент | Обидві ноги на одній біржі |
| Комісії spot | 4 угоди з spot fee — значна частка при малому rate |

---

## 7. Funding + spot hedge (дві біржі)

### Опис стратегії

Як §6: **futures** отримує funding, **spot** хеджує ціну. Але ноги на **різних** біржах: spot на **X**, futures на **Y** (де |rate| ≥ порогу).

Прибуток — funding на Y. Spot на X компенсує price PnL. Додаткова витрата — **cross-basis** між spot X і futures Y + API lag між ногами.

Відмінність від §2: мета — **funding**, не convergence basis; **1 period → close**. Відмінність від §6: два API, два контрагенти, cross-basis замість basis однієї біржі.

### Механіка

**Futures на Y (earn), spot на X (hedge):**

| `rate_Y` | Futures Y | Spot X |
|----------|-----------|--------|
| **> 0** | Short | Long (buy) |
| **< 0** | Long | Short (sell) |

**Відкриття (rate > 0):**
1. Spot buy на X (USDT).
2. Futures short на Y (`Q`).
3. 1 settlement на Y.
4. Close: futures Y → spot sell X.

**Відкриття (rate < 0):**
1. Spot sell на X (`Q` монет).
2. Futures long на Y (`Q`).
3. 1 settlement на Y.
4. Close: futures Y → spot buy X.

**1 period → close.**

### Елементи стратегії

| Елемент | Що це | Звідки |
|---------|--------|--------|
| `спред` (= \|rate_Y\|) | Funding rate на біржі Y, **%** | API Y |
| `спред_виходу` | **0** | Close після 1 period |
| `cross_basis_%` | `(futures_Y − spot_X) / spot_X × 100` | Book X і Y; **витрата** якщо погіршився |
| `обʼєм` | USDT spot buy / futures notional | Параметр |
| `Q` | Монети | Fill spot X |
| `комісія` | 4 угоди на X і Y | fee_rate X + Y |
| `api_lag` | Похибка fill vs сигнал | Затримка між ногами |
| min entry | **\|rate_Y\| ≥ 1%** | Параметр |
| `entry_window` | 1–5 хв до settlement Y | Параметр |

### Формула (слова)

**Спред** — |funding_rate| на біржі Y у %.

**Прибуток** = |rate_Y| × обʼєм − комісія − втрата від зміни cross-basis − slippage від API lag.

Cross-basis втрата: `(cross_basis_виходу − cross_basis_входу) × обʼєм / 100` — якщо premium futures Y над spot X виріс при short Y + long X.

### Формула (приклад з цифрами)

```
rate_Y = +1.0%            ← short futures Y отримує funding
спред_входу = 1.0%
спред_виходу = 0%
обʼєм = 5000 USDT

Spot buy X: 5000 @ 1.800 → Q = 2778
Futures short Y: 2778 @ 1.858 (сигнал 1.860, lag −0.11%)
cross_basis_входу = (1.858 − 1.800) / 1.800 = 3.22%

Після 1 settlement Y:
Funding received = +5000 × 0.01 = +50 USDT

cross_basis_виходу = 3.28%   ← drift +0.06 pp

35 = (1.0 − 0) × 5000 − 12 − 3
      ↑ 50 USDT funding   ↑комісія ↑cross-basis drift
    (1.0 − 0) × 5000 / 100 = 50
    cross-basis drift: (3.28 − 3.22) × 5000 / 100 = 3 USDT
```

### Ризики

| Ризик | Суть |
|-------|------|
| Усе з §6 | — |
| Cross-basis drift | Premium між X і Y погіршився — зʼїдає funding |
| API lag | Гірший cross-basis на fill другої ноги |
| Два контрагенти | Execution failure на одній біржі |
| Різні fee | Spot X + futures Y — різні ставки |

---

## Єдині правила оцінки та форматування

### 1) Основна метрика вибору

`% до депозиту` — чим більше, тим краще для будь-якої стратегії.

```
percent_to_deposit = net_profit_usdt / deposit_usdt × 100
```

де:
- `net_profit_usdt` — чистий результат стратегії в USDT;
- `deposit_usdt` — фактичний депозит/маржа, на яку відкривається позиція.

### 2) Округлення

- Всі значення у **%** показуємо з **2 знаками після коми**.
- Всі значення у **USDT** показуємо з **2 знаками після коми**.

### 3) Міні-чекліст перед входом

1. **same asset** — обидві ноги про один і той самий актив (`BASE/USDT`), без змішування різних `BASE`.
2. **quotes side** — котирування взяті з правильного боку:
   - вхід: short по `bid`, long по `ask`;
   - вихід: short по `ask`, long по `bid`.
3. **fees loaded** — комісії обох бірж/ринків завантажені та підставлені в розрахунок.
4. **funding timestamp valid** — час наступного settlement актуальний і не прострочений; ставка funding відповідає цьому вікну.
