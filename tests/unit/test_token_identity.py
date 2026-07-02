"""Unit tests for token identity comparison logic.

Tests use mocked CurrencyNetworkInfo — no real exchange calls.
"""
from __future__ import annotations

import pytest

from arbitrator.domain.token_identity import (
    CurrencyNetworkInfo,
    MatchResult,
    TokenIdentityComparer,
)


def _info(exchange: str, base: str, network_ids: dict[str, str | None]) -> CurrencyNetworkInfo:
    return CurrencyNetworkInfo(
        exchange_id=exchange,
        base_code=base,
        network_ids=network_ids,
    )


# ── (a) matching contract address ────────────────────────────────────────────

def test_network_verified_when_ids_match() -> None:
    edge_binance = _info("binance", "EDGE", {
        "ETH": "0x3b9BE07d622aCcAEd78f479BC0EDabFd6397E320",
        "BSC": "0x3b9BE07d622aCcAEd78f479BC0EDabFd6397E320",
    })
    edge_mexc = _info("mexc", "EDGE", {
        "ETH": "0x3b9BE07d622aCcAEd78f479BC0EDabFd6397E320",
        "TRX": "TKczPLczhmBWfpFbGsVEJE5BExcBPspZdX",
    })
    result = TokenIdentityComparer.compare("EDGE", edge_binance, edge_mexc)
    assert result.match_type == "network_verified"
    assert result.should_block is False
    assert "ETH" in result.compared_ids
    assert "ETH" in result.shared_networks


def test_network_verified_case_insensitive() -> None:
    """0x addresses must be compared case-insensitively."""
    a = _info("bitget", "TOKEN", {"ETH": "0xABCdef1234567890AbCdEf1234567890AbCdEf12"})
    b = _info("gate", "TOKEN", {"ETH": "0xabcdef1234567890abcdef1234567890abcdef12"})
    result = TokenIdentityComparer.compare("TOKEN", a, b)
    assert result.match_type == "network_verified"
    assert result.should_block is False


# ── (b) conflicting contract address ─────────────────────────────────────────

def test_conflict_when_ids_differ_on_shared_network() -> None:
    """EDGE on BingX points to a different contract than on Bitget — BLOCK."""
    edge_bitget = _info("bitget", "EDGE", {
        "ETH": "0x3b9BE07d622aCcAEd78f479BC0EDabFd6397E320",
    })
    edge_bingx = _info("bingx", "EDGE", {
        "ETH": "0xDEADBEEFdeadbeefdeadbeefdeadbeefdeadbeef",  # different project
    })
    result = TokenIdentityComparer.compare("EDGE", edge_bitget, edge_bingx)
    assert result.match_type == "conflict"
    assert result.should_block is True
    assert "ETH" in result.compared_ids


def test_conflict_blocked_even_when_other_network_matches() -> None:
    """One conflicting network is enough to block, even if another matches."""
    a = _info("binance", "TKN", {
        "ETH": "0xAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        "BSC": "0xSAMESAMESAMESAMESAMESAMESAMESAMESAMESA",
    })
    b = _info("mexc", "TKN", {
        "ETH": "0xBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB",  # conflict
        "BSC": "0xSAMESAMESAMESAMESAMESAMESAMESAMESAMESA",  # match
    })
    result = TokenIdentityComparer.compare("TKN", a, b)
    assert result.match_type == "conflict"
    assert result.should_block is True


# ── no shared networks ────────────────────────────────────────────────────────

def test_symbol_only_when_no_shared_networks() -> None:
    a = _info("binance", "XYZ", {"ETH": "0xAAAA"})
    b = _info("gate", "XYZ", {"TRX": "Tabcdef"})
    result = TokenIdentityComparer.compare("XYZ", a, b)
    assert result.match_type == "symbol_only_ccxt_dedup"
    assert result.should_block is False
    assert result.shared_networks == []


# ── None ids treated as unavailable, not conflict ────────────────────────────

def test_none_ids_do_not_cause_conflict() -> None:
    """When one side has None id on a shared network it is skipped — not a conflict."""
    a = _info("binance", "ABC", {"ETH": None})
    b = _info("mexc", "ABC", {"ETH": "0xSomeAddress"})
    result = TokenIdentityComparer.compare("ABC", a, b)
    assert result.match_type == "symbol_only_ccxt_dedup"
    assert result.should_block is False
    assert result.compared_ids["ETH"] == (None, "0xSomeAddress")


def test_both_none_ids_is_symbol_only() -> None:
    a = _info("binance", "FOO", {"ETH": None})
    b = _info("gate", "FOO", {"ETH": None})
    result = TokenIdentityComparer.compare("FOO", a, b)
    assert result.match_type == "symbol_only_ccxt_dedup"
    assert result.should_block is False


def test_empty_network_ids_both_sides() -> None:
    a = _info("binance", "BAR", {})
    b = _info("mexc", "BAR", {})
    result = TokenIdentityComparer.compare("BAR", a, b)
    assert result.match_type == "symbol_only_ccxt_dedup"
    assert result.shared_networks == []


# ── TokenIdentityService.compare fallback when cache is empty ────────────────

def test_service_returns_symbol_only_when_cache_empty() -> None:
    from arbitrator.application.token_identity_service import TokenIdentityService

    svc = TokenIdentityService()
    result = svc.compare("EDGE", "binance", "mexc")
    assert result.match_type == "symbol_only_ccxt_dedup"
    assert result.should_block is False
    assert "binance" in result.notes or "mexc" in result.notes


# ── commonCurrencies cross-check (EDGE-style collision) ──────────────────────

def test_common_currencies_conflict_blocks_trade() -> None:
    """EDGE on mexc remaps to 'EdgeCoin', on gate to 'Edge Network' — different tokens."""
    from arbitrator.application.token_identity_service import TokenIdentityService

    svc = TokenIdentityService()
    svc._common_currencies["mexc"] = {"EDGE": "EdgeCoin"}
    svc._common_currencies["gate"] = {"EDGE": "Edge Network"}

    result = svc.compare("EDGE", "mexc", "gate")
    assert result.match_type == "conflict"
    assert result.should_block is True
    assert "EdgeCoin" in result.notes
    assert "Edge Network" in result.notes


def test_common_currencies_same_name_does_not_block() -> None:
    """Same canonical name on both exchanges → no conflict from commonCurrencies."""
    from arbitrator.application.token_identity_service import TokenIdentityService

    svc = TokenIdentityService()
    svc._common_currencies["mexc"] = {"BTC": "Bitcoin"}
    svc._common_currencies["gate"] = {"BTC": "Bitcoin"}

    result = svc.compare("BTC", "mexc", "gate")
    # No network data either — should be symbol_only, not conflict
    assert result.match_type == "symbol_only_ccxt_dedup"
    assert result.should_block is False


def test_common_currencies_case_insensitive_match() -> None:
    """Same name with different capitalisation must not trigger a conflict."""
    from arbitrator.application.token_identity_service import TokenIdentityService

    svc = TokenIdentityService()
    svc._common_currencies["mexc"] = {"TOKEN": "My Token"}
    svc._common_currencies["gate"] = {"TOKEN": "my token"}

    result = svc.compare("TOKEN", "mexc", "gate")
    assert result.should_block is False


def test_common_currencies_one_side_no_remap_passes() -> None:
    """If only one exchange has a remapping and the other doesn't
    (token not in its commonCurrencies), base_code is used as canonical name.
    Same string → no conflict."""
    from arbitrator.application.token_identity_service import TokenIdentityService

    svc = TokenIdentityService()
    # mexc has table loaded but EDGE not in it → canonical stays "EDGE"
    svc._common_currencies["mexc"] = {"OTHER": "Something Else"}
    svc._common_currencies["gate"] = {"EDGE": "EDGE"}  # explicitly maps to same base_code

    result = svc.compare("EDGE", "mexc", "gate")
    assert result.should_block is False


def test_common_currencies_skipped_when_neither_table_loaded() -> None:
    """If neither exchange has loaded commonCurrencies yet, skip the check entirely."""
    from arbitrator.application.token_identity_service import TokenIdentityService

    svc = TokenIdentityService()
    # _common_currencies empty → cc_a={}, cc_b={} → neither truthy → step skipped
    result = svc.compare("EDGE", "mexc", "gate")
    assert result.match_type == "symbol_only_ccxt_dedup"
    assert result.should_block is False


def test_network_verified_wins_over_common_currencies_when_both_loaded() -> None:
    """Even if commonCurrencies names match, network contract-id comparison runs
    and produces network_verified when contracts match."""
    from arbitrator.application.token_identity_service import TokenIdentityService

    svc = TokenIdentityService()
    svc._common_currencies["binance"] = {"BTC": "Bitcoin"}
    svc._common_currencies["gate"] = {"BTC": "Bitcoin"}
    svc._cache[("binance", "BTC")] = _info("binance", "BTC", {"ETH": "0xAAA"})
    svc._cache[("gate", "BTC")] = _info("gate", "BTC", {"ETH": "0xAAA"})

    result = svc.compare("BTC", "binance", "gate")
    assert result.match_type == "network_verified"
    assert result.should_block is False


# ── TokenIdentityService.build_report_rows ───────────────────────────────────

def test_build_report_rows_includes_both_exchanges() -> None:
    from arbitrator.application.token_identity_service import TokenIdentityService

    svc = TokenIdentityService()
    svc._cache[("binance", "BTC")] = _info("binance", "BTC", {"ETH": "0xAAA"})
    svc._cache[("mexc", "BTC")] = _info("mexc", "BTC", {"ETH": "0xAAA"})

    rows = svc.build_report_rows([("binance", "mexc")], ["BTC"])
    assert len(rows) == 1
    assert rows[0]["base"] == "BTC"
    assert rows[0]["match_type"] == "network_verified"


def test_build_report_rows_omits_single_exchange_codes() -> None:
    from arbitrator.application.token_identity_service import TokenIdentityService

    svc = TokenIdentityService()
    svc._cache[("binance", "SOLO")] = _info("binance", "SOLO", {"ETH": "0xAAA"})
    # "mexc" has no entry for SOLO

    rows = svc.build_report_rows([("binance", "mexc")], ["SOLO"])
    assert rows == []
