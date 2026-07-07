---
name: exchange-read-only-inspect
description: >-
  Read-only exchange API inspection for agents: verify credentials, balances,
  positions, open orders, and public market data. Use when checking exchange
  connectivity or account state. NEVER place, amend, or cancel orders.
---

# Exchange read-only inspect

## Hard rule — no trading

**Категорично заборонено** без явного погодження користувача:

- відкривати або закривати позиції;
- створювати, змінювати або скасовувати ордери;
- змінювати плече, переказувати кошти;
- викликати `open_market_position`, `close_market_position`, `create_order`,
  `cancel_order`, `set_leverage` або будь-які trading MCP tools.

Агенту дозволено **лише читати**: підключення, баланс, позиції, відкриті ордери,
публічні тікери, стакан, список символів.

## Зовнішні MCP (довідка)

Окремі MCP для бірж існують, але багато з них містять trading tools. **Не
підключай їх** для цього проєкту без явного запиту користувача.

| Проєкт | Примітка |
|--------|----------|
| [eliasfire617/crypto-market-data-mcp](https://github.com/eliasfire617/crypto-market-data-mcp) | Публічні дані, без ключів |
| [lev-corrupted/CryptoPortfolioMCPServer](https://github.com/lev-corrupted/CryptoPortfolioMCPServer) | Read-only портфель (Binance, Coinbase, Kraken) |
| [carlosatta/mcp-server-ccxt](https://github.com/carlosatta/mcp-server-ccxt) | CCXT; є SAFE_MODE, але є trading tools |
| [grapewheel/binance-mcp](https://github.com/grapewheel/binance-mcp) | Лише публічний Binance REST |
| [dante1989/mcp-ccxt](https://github.com/dante1989/mcp-ccxt) | CCXT; sandbox за замовчуванням, є trading |
| [bybit-exchange/trading-mcp](https://github.com/bybit-exchange/trading-mcp) | Офіційний Bybit; містить trade tools |

**Рекомендація для цього репозиторію:** використовуй вбудований скрипт
`scripts/inspect_exchanges.py` — він працює з тими ж `.env` ключами і адаптерами,
що й основний застосунок, і не має trading API.

## Передумови

1. Ключі в `.env` (див. `Settings.credentials_for`):
   - `MEXC_API_KEY` / `MEXC_API_SECRET`
   - `BITGET_API_KEY` / `BITGET_API_SECRET` / `BITGET_API_PASSWORD`
   - `GATE_API_KEY` / `GATE_API_SECRET`
   - `BINGX_API_KEY` / `BINGX_API_SECRET`
   - `BINANCE_API_KEY` / `BINANCE_API_SECRET`
2. Список бірж — `enabled_exchanges` у `Settings` / `.env`.
3. Символи — лише USDT-M perpetual: `BASE/USDT:USDT`.

## Команди (з кореня репозиторію)

Завжди додавай `--json` для парсингу агентом. Інтерпретатор — лише з `.venv`
(див. `.cursor/rules/tooling.mdc`).

```bash
# Підтримувані та увімкнені біржі
.venv\Scripts\python.exe scripts/inspect_exchanges.py --json list-exchanges

# Перевірка ключів і USDT-балансу (усі enabled)
.venv\Scripts\python.exe scripts/inspect_exchanges.py --json verify

# Одна біржа
.venv\Scripts\python.exe scripts/inspect_exchanges.py --json verify --exchange mexc

# Повний зріз акаунта: connection + позиції + відкриті ордери
.venv\Scripts\python.exe scripts/inspect_exchanges.py --json account

.venv\Scripts\python.exe scripts/inspect_exchanges.py --json account --exchange bitget

# Публічні дані (ключі не обов'язкові)
.venv\Scripts\python.exe scripts/inspect_exchanges.py --json ticker --exchange mexc --symbol BTC/USDT:USDT
.venv\Scripts\python.exe scripts/inspect_exchanges.py --json orderbook --exchange mexc --symbol BTC/USDT:USDT --limit 5

# Список USDT-M swap символів
.venv\Scripts\python.exe scripts/inspect_exchanges.py --json list-symbols --exchange gate
```

## Інші read-only скрипти для аналізу ситуацій

Див. також `.cursor/rules/exchange-data.mdc` (секція **Agent diagnostics**).

| Ситуація | Скрипт |
| -------- | ------ |
| Відкриті + закриті позиції (як Orders UI) | `scripts/trade_report.py` |
| Аудит paper orders vs OHLCV | `scripts/audit_paper_orders.py` |
| Бектест FF на історичних OHLCV | `scripts/backtest_ff.py` |
| Перевірка contract address токена між біржами | `scripts/check_token_identity.py` |

## Коди виходу

| Код | Значення |
|-----|----------|
| `0` | Успіх (для `verify` — усі біржі з ключами authenticated) |
| `1` | `verify`: хоча б одна біржа з ключами не пройшла перевірку |
| `2` | Помилка аргументів / невідома біржа |

## Поля JSON (`account`)

- `connection.credentials_configured` — чи заповнені ключі в `.env`
- `connection.authenticated` — чи прийняли ключі біржі
- `connection.trading_enabled` — чи є доступ до ф'ючерсної торгівлі (read probe)
- `connection.usdt_balance` — USDT на ф'ючерсному гаманці
- `positions[]` — відкриті USDT-M позиції
- `open_orders[]` — відкриті ордери (read-only `fetch_open_orders`)

## Код (для розширення)

- `ReadOnlyExchangeInspector` — `src/arbitrator/application/read_only_exchange_inspector.py`
- CLI — `scripts/inspect_exchanges.py`
- Низькорівневі read методи — `CcxtBase.probe_connection`, `fetch_open_orders`,
  `fetch_ticker_once`, `fetch_order_book_once`

Не імпортуй `ExchangeGateway` trading методи в агентських скриптах.
