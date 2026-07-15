# QA Checklist: History Screener & Live Monitors

**Purpose**: Verifying the completion and integration of Feature 005.
**Created**: 2026-07-12
**Feature**: [005-history-screener-monitors/spec.md](spec.md)

## 1. UI Structure & CSS Validation

- [ ] CHK001 - Verify that the "Historical Screener" section is collapsible/expandable via the title header click.
- [ ] CHK002 - Verify that the History Screener table shows exactly 20 rows before an internal scrollbar appears.
- [ ] CHK003 - Check that the main page scrollbar allows scrolling down to view an unlimited number of Live Monitoring Cards.

## 2. History Screener Table (Top)

- [x] CHK004 - Verify that clicking "Start Monitoring" initiates the 5-second updates from the backend.
- [x] CHK005 - Verify that the table sorts rows by spread (descending).
- [x] CHK006 - Verify that applying filters (Time Window, Min Spread %, Min 24h Vol) correctly filters the displayed rows.
- [x] CHK007 - Verify that the "Symbol" column correctly displays the token name and the maximum historical spread.
- [x] CHK008 - Check that "Copy to Form" action clones a new Live Card into the grid without automatically starting real-time data streaming.
- [ ] CHK009 - Check that "Fast Trade" action clones a new Live Card into the grid AND immediately starts real-time data streaming and charting.

## 3. Live Monitoring Card (Bottom) - Pending Integration

- [ ] CHK010 - Verify that each active Live Card successfully connects to the `screener_ws_handler` to receive independent real-time updates.
- [ ] CHK011 - Check that the real-time orderbook data (Ask, Bid, Size) updates rapidly within the card UI.
- [ ] CHK012 - Check that execution statistics (Price, P/L, Realized PNL) update correctly.
- [ ] CHK013 - Verify that the **Live Chart** canvas successfully renders a line chart plotting the "Open spread" and "Close spread" dynamically over time for that specific symbol.
- [ ] CHK014 - Verify that when the current spread meets the Open/Close spread target, the UI shows a visual indicator for the `T` logic (tick confirmation) countdown.
- [ ] CHK015 - Ensure that clicking the "X" button on the card successfully stops its dedicated WebSocket stream and removes the card from the UI.