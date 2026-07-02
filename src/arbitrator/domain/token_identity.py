from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class CurrencyNetworkInfo(BaseModel):
    """Per-network identity data extracted from ccxt fetchCurrencies() for one base code.

    Fields mirror the ccxt unified currency structure:
      currency['networks'][net_key] = {
          'id':      exchange-native network identifier (may be contract address, may be
                     a chain name like "ERC20", may be None — depends heavily on exchange),
          'network': unified ccxt network code (e.g. "ETH", "BSC", "TRX"),
          ...
      }

    'id' is preserved as-is from the exchange — some exchanges return a
    contract address (0x…), others return a chain label ("ERC20", "BEP20"),
    and some return None.  id_is_address logic is left to callers.
    None values are preserved rather than hidden so callers can make informed
    decisions about confidence level.
    """

    model_config = ConfigDict(frozen=True)

    exchange_id: str
    base_code: str
    # net_key -> raw id field from ccxt networks[net]['id'] (may be None)
    network_ids: dict[str, str | None]


MatchType = Literal[
    "network_verified",        # >=1 shared network with matching non-None contract id
    "symbol_only_ccxt_dedup",  # no shared networks or ids absent; ccxt dedup is only guarantee
    "conflict",                # shared network found but ids differ — BLOCK
]


class MatchResult(BaseModel):
    """Result of comparing the same base_code across two exchanges."""

    model_config = ConfigDict(frozen=True)

    base_code: str
    exchange_a: str
    exchange_b: str
    match_type: MatchType
    shared_networks: list[str]
    # net -> (id_a, id_b) for all shared networks
    compared_ids: dict[str, tuple[str | None, str | None]]
    # True when match_type is "conflict" — caller must not open this pair
    should_block: bool
    notes: str


class TokenIdentityComparer:
    """Pure comparison logic.  No I/O — accepts pre-fetched CurrencyNetworkInfo."""

    @staticmethod
    def compare(
        base_code: str,
        info_a: CurrencyNetworkInfo,
        info_b: CurrencyNetworkInfo,
    ) -> MatchResult:
        shared = sorted(set(info_a.network_ids) & set(info_b.network_ids))

        compared_ids: dict[str, tuple[str | None, str | None]] = {}
        conflicting: list[str] = []
        verified: list[str] = []

        for net in shared:
            id_a = info_a.network_ids[net]
            id_b = info_b.network_ids[net]
            compared_ids[net] = (id_a, id_b)

            if id_a is None or id_b is None:
                # Cannot compare — field missing on one/both sides; not a conflict
                continue

            # Normalise: lower-case for 0x addresses, strip whitespace
            norm_a = id_a.strip().lower()
            norm_b = id_b.strip().lower()

            if norm_a == norm_b:
                verified.append(net)
            else:
                conflicting.append(net)

        if conflicting:
            return MatchResult(
                base_code=base_code,
                exchange_a=info_a.exchange_id,
                exchange_b=info_b.exchange_id,
                match_type="conflict",
                shared_networks=shared,
                compared_ids=compared_ids,
                should_block=True,
                notes=(
                    f"Contract id mismatch on networks: {conflicting}. "
                    "These are likely different tokens. BLOCK."
                ),
            )

        if verified:
            return MatchResult(
                base_code=base_code,
                exchange_a=info_a.exchange_id,
                exchange_b=info_b.exchange_id,
                match_type="network_verified",
                shared_networks=shared,
                compared_ids=compared_ids,
                should_block=False,
                notes=f"Contract id matched on networks: {verified}.",
            )

        # No conflict, but no verified match either (no shared networks,
        # or all shared network ids were None on at least one side).
        notes_parts: list[str] = []
        if not shared:
            notes_parts.append("No shared networks between exchanges.")
        else:
            missing = [
                n for n in shared
                if None in (info_a.network_ids.get(n), info_b.network_ids.get(n))
            ]
            notes_parts.append(
                f"Shared networks {shared} but contract ids absent for: {missing}. "
                "Cannot verify — relying on ccxt commonCurrencies only."
            )
        notes_parts.append("Manual review recommended.")

        return MatchResult(
            base_code=base_code,
            exchange_a=info_a.exchange_id,
            exchange_b=info_b.exchange_id,
            match_type="symbol_only_ccxt_dedup",
            shared_networks=shared,
            compared_ids=compared_ids,
            should_block=False,
            notes=" ".join(notes_parts),
        )
