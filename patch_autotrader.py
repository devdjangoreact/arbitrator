import re

with open("src/arbitrator/application/trading/historical_auto_trader.py", "r", encoding="utf-8") as f:
    content = f.read()

# Add _live_state dictionary
if "self._live_state: dict[str, dict] =" not in content:
    init_find = "self._close_tick_counters: dict[str, int] = {}"
    content = content.replace(init_find, init_find + "\n        self._live_state: dict[str, dict] = {}")

if "def get_live_state(self) -> dict:" not in content:
    get_state_fn = """
    def get_live_state(self) -> dict:
        return self._live_state
"""
    content = content.replace("def _restore_open_pairs(self) -> None:", get_state_fn + "\n    def _restore_open_pairs(self) -> None:")

# Replace _tick body to calculate spreads for ALL configs first
tick_find = """    async def _tick(self) -> None:
        configs = self._store.get_all()"""

new_tick_start = """    async def _tick(self) -> None:
        configs = self._store.get_all()

        # 1. Update live state for ALL configs (even stopped) for UI charts
        new_state = {}
        for config in configs:
            try:
                # Figure out active sides
                if config.side == "auto":
                    # For UI display when auto, just pick short=short_ex to show *some* spread, or resolve best
                    active_short = config.short_ex
                    active_long = config.long_ex
                elif config.side == "short":
                    active_short = config.short_ex
                    active_long = config.long_ex
                else:
                    active_short = config.long_ex
                    active_long = config.short_ex

                # Fetch fresh spread once per config for UI
                entry_res = await self._spread_resolver.entry_spread(config.symbol, active_short, active_long, fetch_fresh=True)
                exit_res = await self._spread_resolver.exit_spread(config.symbol, active_short, active_long, fetch_fresh=True)

                entry_pct = entry_res[2] if entry_res else 0.0
                exit_pct = exit_res[2] if exit_res else 0.0

                # Check how many pairs are open
                open_pairs = [(pid, sym, s, l) for pid, (sym, s, l) in self._open_pairs.items() if sym == config.symbol]

                new_state[config.symbol] = {
                    "open_spread": entry_pct,
                    "close_spread": exit_pct,
                    "open_ticks": self._open_tick_counters.get(config.symbol, 0),
                    "close_ticks": max([self._close_tick_counters.get(pid, 0) for pid, _, _, _ in open_pairs]) if open_pairs else 0,
                    "open_orders": len(open_pairs)
                }
            except Exception:
                logger.exception(f"Error resolving state for {config.symbol}")

        self._live_state = new_state
"""

if "# 1. Update live state for ALL configs" not in content:
    content = content.replace(tick_find, new_tick_start)

# We must also ensure we don't double fetch if we don't have to, but since fetch_fresh=True caches within the tick slightly (wait, ExecutableSpreadResolver does not cache across calls if fetch_fresh=True is passed? It does hit cache memory if not expired, but let's just let it be. The UI needs fresh data).

with open("src/arbitrator/application/trading/historical_auto_trader.py", "w", encoding="utf-8") as f:
    f.write(content)
