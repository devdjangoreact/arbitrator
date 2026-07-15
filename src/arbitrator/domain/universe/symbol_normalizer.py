from __future__ import annotations


class SymbolNormalizer:
    """Maps UI display symbols to ccxt USDT-M swap symbols."""

    @staticmethod
    def to_swap_symbol(display_or_swap: str) -> str:
        if ":USDT" in display_or_swap:
            return display_or_swap
        if display_or_swap.endswith("/USDT"):
            return f"{display_or_swap}:USDT"
        return display_or_swap

    @staticmethod
    def to_display_symbol(swap_symbol: str) -> str:
        if swap_symbol.endswith(":USDT"):
            return swap_symbol[: -len(":USDT")]
        return swap_symbol

    @staticmethod
    def base_asset(symbol: str) -> str:
        swap = SymbolNormalizer.to_swap_symbol(symbol)
        return swap.split("/")[0] if "/" in swap else swap
