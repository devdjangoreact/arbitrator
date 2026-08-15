from __future__ import annotations

from arbitrator_2.connector.ccxt_pro_venue import CcxtProVenue
from arbitrator_2.connector.ccxt_session_factory import CcxtSessionFactory
from arbitrator_2.connector.connector_settings import ConnectorSettings
from arbitrator_2.connector.venue_capabilities import VenueCapabilities

_DEFAULT_CAPS = VenueCapabilities(min_depth=5, trades=True)

_CAPS: dict[str, VenueCapabilities] = {
    "bitget": VenueCapabilities(min_depth=1, trades=True),
}


def enabled_venues(settings: ConnectorSettings | None = None) -> tuple[str, ...]:
    cfg = settings if settings is not None else ConnectorSettings()
    return tuple(cfg.enabled_exchanges)


def build_default_adapters(settings: ConnectorSettings | None = None) -> list[CcxtProVenue]:
    cfg = settings if settings is not None else ConnectorSettings()
    factory = CcxtSessionFactory(cfg)
    return [
        CcxtProVenue(
            venue_id,
            _CAPS.get(venue_id, _DEFAULT_CAPS),
            factory=factory,
            book_depth=cfg.book_depth,
        )
        for venue_id in enabled_venues(cfg)
    ]
