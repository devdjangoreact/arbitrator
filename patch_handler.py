import re

with open("src/arbitrator/presentation/ws/historical_screener_ws_handler.py", "r", encoding="utf-8") as f:
    content = f.read()

target = """                "monitors": [c.__dict__ for c in configs],
            },"""

new_target = """                "monitors": [c.__dict__ for c in configs],
                "live_state": self._runtime.historical_auto_trader.get_live_state() if self._runtime.historical_auto_trader else {},
            },"""

if "live_state" not in content:
    content = content.replace(target, new_target)

with open("src/arbitrator/presentation/ws/historical_screener_ws_handler.py", "w", encoding="utf-8") as f:
    f.write(content)
