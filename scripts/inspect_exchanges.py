"""Read-only exchange inspector CLI for agents and operators.

Never places, amends, or cancels orders. See .cursor/skills/exchange-read-only-inspect/SKILL.md.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from arbitrator.application.read_only_exchange_inspector import ReadOnlyExchangeInspector
from arbitrator.config.logger import init_logger, logger
from arbitrator.config.settings import Settings
from arbitrator.domain.exchange_account_snapshot import ExchangeAccountSnapshot
from arbitrator.domain.exchange_connection_status import ExchangeConnectionStatus
from arbitrator.domain.order_book_snapshot import OrderBookSnapshot
from arbitrator.domain.ticker import Ticker
from arbitrator.exchanges.factory import Factory


class InspectExchangesCli:
    """Parses CLI arguments and runs read-only exchange inspection commands."""

    def __init__(self, inspector: ReadOnlyExchangeInspector) -> None:
        self._inspector = inspector

    def run(self, argv: list[str] | None = None) -> int:
        parser = self._build_parser()
        args = parser.parse_args(argv)
        try:
            return asyncio.run(self._dispatch(args))
        except KeyboardInterrupt:
            logger.info("inspect_exchanges interrupted")
            return 130
        except ValueError as error:
            self._emit_error(str(error), as_json=bool(args.json))
            return 2

    def _build_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            description="Read-only exchange connection and account inspector.",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Emit machine-readable JSON (recommended for agents).",
        )
        subparsers = parser.add_subparsers(dest="command", required=True)

        list_exchanges = subparsers.add_parser(
            "list-exchanges",
            help="List supported and enabled exchange ids.",
        )
        list_exchanges.set_defaults(handler="list_exchanges")

        verify = subparsers.add_parser(
            "verify",
            help="Verify API credentials and USDT futures access.",
        )
        verify.add_argument(
            "--exchange",
            help="Single exchange id (default: all enabled in Settings).",
        )
        verify.set_defaults(handler="verify")

        account = subparsers.add_parser(
            "account",
            help="Connection status, balance, open positions and orders.",
        )
        account.add_argument(
            "--exchange",
            help="Single exchange id (default: all enabled in Settings).",
        )
        account.add_argument(
            "--symbol-count",
            action="store_true",
            help="Include USDT-M swap symbol count (extra REST call).",
        )
        account.set_defaults(handler="account")

        ticker = subparsers.add_parser("ticker", help="Fetch one public ticker snapshot.")
        ticker.add_argument("--exchange", required=True)
        ticker.add_argument("--symbol", required=True, help="ccxt symbol, e.g. BTC/USDT:USDT")
        ticker.set_defaults(handler="ticker")

        orderbook = subparsers.add_parser("orderbook", help="Fetch one public order book snapshot.")
        orderbook.add_argument("--exchange", required=True)
        orderbook.add_argument("--symbol", required=True, help="ccxt symbol, e.g. BTC/USDT:USDT")
        orderbook.add_argument("--limit", type=int, default=10)
        orderbook.set_defaults(handler="orderbook")

        symbols = subparsers.add_parser(
            "list-symbols",
            help="List USDT-M perpetual swap symbols on an exchange.",
        )
        symbols.add_argument("--exchange", required=True)
        symbols.set_defaults(handler="list_symbols")

        return parser

    async def _dispatch(self, args: argparse.Namespace) -> int:
        handler = str(args.handler)
        if handler == "list_exchanges":
            return self._cmd_list_exchanges(as_json=bool(args.json))
        if handler == "verify":
            return await self._cmd_verify(
                exchange_id=args.exchange,
                as_json=bool(args.json),
            )
        if handler == "account":
            return await self._cmd_account(
                exchange_id=args.exchange,
                include_symbol_count=bool(args.symbol_count),
                as_json=bool(args.json),
            )
        if handler == "ticker":
            return await self._cmd_ticker(
                exchange_id=str(args.exchange),
                symbol=str(args.symbol),
                as_json=bool(args.json),
            )
        if handler == "orderbook":
            return await self._cmd_orderbook(
                exchange_id=str(args.exchange),
                symbol=str(args.symbol),
                limit=int(args.limit),
                as_json=bool(args.json),
            )
        if handler == "list_symbols":
            return await self._cmd_list_symbols(
                exchange_id=str(args.exchange),
                as_json=bool(args.json),
            )
        raise ValueError(f"unknown handler {handler}")

    def _cmd_list_exchanges(self, *, as_json: bool) -> int:
        payload = {
            "supported": list(self._inspector.supported_exchange_ids()),
            "enabled": list(self._inspector.enabled_exchange_ids()),
        }
        if as_json:
            self._print_json(payload)
        else:
            print(f"Supported: {', '.join(payload['supported'])}")
            print(f"Enabled:   {', '.join(payload['enabled'])}")
        return 0

    async def _cmd_verify(self, *, exchange_id: str | None, as_json: bool) -> int:
        if exchange_id:
            statuses = [await self._inspector.verify_exchange(exchange_id)]
        else:
            statuses = await self._inspector.verify_enabled()
        if as_json:
            self._print_json([status.model_dump(mode="json") for status in statuses])
        else:
            for status in statuses:
                self._print_status(status)
        return 0 if all(status.authenticated for status in statuses if status.credentials_configured) else 1

    async def _cmd_account(
        self,
        *,
        exchange_id: str | None,
        include_symbol_count: bool,
        as_json: bool,
    ) -> int:
        if exchange_id:
            snapshots = [
                await self._inspector.account_snapshot(
                    exchange_id,
                    include_symbol_count=include_symbol_count,
                )
            ]
        else:
            snapshots = await self._inspector.account_snapshots_for_enabled(
                include_symbol_count=include_symbol_count,
            )
        if as_json:
            self._print_json([snapshot.model_dump(mode="json") for snapshot in snapshots])
        else:
            for snapshot in snapshots:
                self._print_account(snapshot)
        return 0

    async def _cmd_ticker(self, *, exchange_id: str, symbol: str, as_json: bool) -> int:
        ticker = await self._inspector.fetch_ticker(exchange_id, symbol)
        if ticker is None:
            self._emit_error("ticker unavailable", as_json=as_json)
            return 1
        self._emit_model(ticker, as_json=as_json)
        return 0

    async def _cmd_orderbook(
        self,
        *,
        exchange_id: str,
        symbol: str,
        limit: int,
        as_json: bool,
    ) -> int:
        book = await self._inspector.fetch_order_book(exchange_id, symbol, limit)
        self._emit_model(book, as_json=as_json)
        return 0

    async def _cmd_list_symbols(self, *, exchange_id: str, as_json: bool) -> int:
        symbol_list = await self._inspector.list_swap_symbols(exchange_id)
        if as_json:
            self._print_json({"exchange_id": exchange_id, "symbols": symbol_list})
        else:
            print(f"{exchange_id}: {len(symbol_list)} USDT-M swap symbols")
            for symbol in symbol_list[:50]:
                print(f"  {symbol}")
            if len(symbol_list) > 50:
                print(f"  ... and {len(symbol_list) - 50} more (use --json for full list)")
        return 0

    @staticmethod
    def _print_status(status: ExchangeConnectionStatus) -> None:
        balance = "—" if status.usdt_balance is None else f"{status.usdt_balance:.4f} USDT"
        print(
            f"{status.display_name} ({status.exchange_id}): "
            f"configured={status.credentials_configured} "
            f"auth={status.authenticated} "
            f"trading={status.trading_enabled} "
            f"balance={balance} "
            f"msg={status.message}"
        )

    @staticmethod
    def _print_account(snapshot: ExchangeAccountSnapshot) -> None:
        InspectExchangesCli._print_status(snapshot.connection)
        print(f"  positions: {len(snapshot.positions)}")
        for leg in snapshot.positions:
            print(
                f"    {leg.symbol} {leg.side} contracts={leg.contracts} "
                f"entry={leg.entry_price} uPnL={leg.unrealized_pnl}"
            )
        print(f"  open_orders: {len(snapshot.open_orders)}")
        for order in snapshot.open_orders:
            print(
                f"    {order.symbol} {order.side} {order.order_type} "
                f"amount={order.amount} price={order.price} id={order.order_id}"
            )
        if snapshot.swap_symbols_count is not None:
            print(f"  swap_symbols_count: {snapshot.swap_symbols_count}")

    @staticmethod
    def _emit_model(model: Ticker | OrderBookSnapshot, *, as_json: bool) -> None:
        if as_json:
            InspectExchangesCli._print_json(model.model_dump(mode="json"))
        else:
            print(model.model_dump(mode="json"))

    @staticmethod
    def _print_json(payload: object) -> None:
        print(json.dumps(payload, ensure_ascii=False, indent=2))

    @staticmethod
    def _emit_error(message: str, *, as_json: bool) -> None:
        if as_json:
            InspectExchangesCli._print_json({"error": message})
        else:
            print(message, file=sys.stderr)


def main() -> None:
    settings = Settings()
    init_logger(console_level=settings.log_level)
    inspector = ReadOnlyExchangeInspector(settings=settings, factory=Factory(settings=settings))
    cli = InspectExchangesCli(inspector=inspector)
    raise SystemExit(cli.run())


if __name__ == "__main__":
    main()
