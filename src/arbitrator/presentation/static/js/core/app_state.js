/** @typedef {{ symbol: string, short_exchange_id: string, long_exchange_id: string } | null} OpportunityFocus */

const AppState = {
  activePage: "screener",
  /** @type {OpportunityFocus} */
  focusOpportunity: null,
  /** @type {OpportunityFocus} */
  defaultOpportunityFocus: null,
  ordersOpenCount: null,
  screenerSnapshot: null,
  screenerWsConnected: false,
  opportunityWsConnected: false,
  /** @type {Map<string, HTMLTableRowElement>} */
  screenerRowElements: new Map(),
  opportunitySnapshot: null,
  ordersSnapshot: null,
  settingsSnapshot: null,
  /** @type {object | null} */
  paperTradesSnapshot: null,
};

window.AppState = AppState;
