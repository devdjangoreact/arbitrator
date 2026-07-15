/**
 * Formatting utilities for exact parity with legacy UI.
 * Rules derived from spec 009.
 */

/**
 * Format standard numbers.
 * @param value Number to format
 * @param digits Decimal places (default 4)
 */
export function fmtNum(value: number | null | undefined, digits = 4): string {
  if (value === null || value === undefined) return "—";
  return Number(value).toFixed(digits);
}

/**
 * Format PnL values with mandatory sign.
 * @param value PnL to format
 */
export function fmtPnl(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const numValue = Number(value);
  const sign = numValue > 0 ? "+" : numValue < 0 ? "−" : ""; // U+2212 for minus
  return `${sign}${Math.abs(numValue).toFixed(2)}`;
}

/**
 * Get CSS class for numerical value.
 * @param value Value to evaluate
 */
export function pnlClass(
  value: number | null | undefined,
): "pos" | "neg" | "na" {
  if (value === null || value === undefined) return "na";
  const numValue = Number(value);
  if (numValue > 0) return "pos";
  if (numValue < 0) return "neg";
  return "na"; // Note: returning 'na' for 0 to match legacy if it was neutral, though legacy format.js returned ""
}

/**
 * Format PnL or return 'N/A'
 * @param value PnL to format
 */
export function fmtPnlOrNa(value: number | null | undefined): string {
  if (value === null || value === undefined) return "N/A";
  return fmtPnl(value);
}

/**
 * Format strategy profit with mandatory '+' for positive.
 * @param value Profit to format
 * @param digits Decimal places (default 2)
 */
export function fmtStrategyProfit(
  value: number | null | undefined,
  digits = 2,
): string {
  if (value === null || value === undefined) return "N/A";
  const numValue = Number(value);
  const sign = numValue > 0 ? "+" : ""; // Legacy logic only added '+', didn't use '−' explicitly here in format.js but let `-` pass through
  return `${sign}${fmtNum(numValue, digits)}`;
}

/**
 * Format percentage deposit with mandatory sign and '%' suffix.
 * @param value Percentage to format
 */
export function fmtPercentDeposit(value: number | null | undefined): string {
  if (value === null || value === undefined) return "N/A";
  const numValue = Number(value);
  const sign = numValue > 0 ? "+" : numValue < 0 ? "−" : "";
  return `${sign}${Math.abs(numValue).toFixed(2)}%`;
}

/**
 * Compact large numbers with K/M suffixes.
 * @param value Number to compact
 */
export function compactK(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const numValue = Number(value);
  if (numValue >= 1_000_000) return `${(numValue / 1_000_000).toFixed(2)}M`;
  if (numValue >= 1000) return `${Math.round(numValue / 1000)}K`;
  return String(Math.round(numValue));
}
