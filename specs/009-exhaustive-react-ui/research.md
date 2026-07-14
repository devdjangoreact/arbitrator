# Research & Decisions

## Topic: Charting Library for Opportunity Chart

**Decision**: Use `recharts`.

**Rationale**: 
The Opportunity Chart (Section 3.5 of the spec) requires visualizing `Spread`, `Short Exchange Price (Bid/Ask)`, and `Long Exchange Price (Bid/Ask)` over time, updating in real-time via WebSocket. `recharts` is a composable charting library built on React components. It handles dynamic data updates gracefully and offers sufficient customization to replicate the visual style of the legacy `opportunity_chart.js`. It is lightweight enough not to impact the performance of the high-frequency trading UI.

**Alternatives considered**:
- `Chart.js`: Too heavy and not fully React-native (wraps canvas).
- `d3.js`: Overkill for a simple line/area chart tracking a few metrics. Requires manual DOM manipulation which conflicts with React's declarative nature.
- `lightweight-charts` (TradingView): Excellent for financial data, but `recharts` is more flexible for plotting arbitrary overlapping lines (like raw spread vs prices) without needing strict OHLCV candlestick formats.