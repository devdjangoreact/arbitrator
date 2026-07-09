from __future__ import annotations

import asyncio
_API = "https://api.telegram.org/bot{token}/sendMessage"


class TelegramNotifier:
    """Fire-and-forget Telegram push via Bot API (no extra deps — uses aiohttp)."""

    def __init__(self, bot_token: str, chat_id: str) -> None:
        self._token = bot_token
        self._chat_id = chat_id
        self._enabled = bool(bot_token and chat_id)

    def notify(self, text: str) -> None:
        """Schedule a non-blocking send; caller does not await."""
        if not self._enabled:
            return
        asyncio.create_task(self._send(text))

    async def _send(self, text: str) -> None:
        try:
            import aiohttp

            url = _API.format(token=self._token)
            connector = aiohttp.TCPConnector(resolver=aiohttp.ThreadedResolver())
            async with aiohttp.ClientSession(connector=connector) as session:
                await session.post(
                    url,
                    json={"chat_id": self._chat_id, "text": text, "parse_mode": "HTML"},
                    timeout=aiohttp.ClientTimeout(total=10),
                )
        except Exception:
            pass
