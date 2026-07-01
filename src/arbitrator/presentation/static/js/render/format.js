/** @param {number | null | undefined} value @param {number} [digits] */
function fmtNum(value, digits = 4) {
  if (value === null || value === undefined) return "—";
  return Number(value).toFixed(digits);
}

/** @param {number} value */
function fmtPnl(value) {
  const sign = value > 0 ? "+" : value < 0 ? "−" : "";
  return `${sign}${Math.abs(value).toFixed(2)}`;
}

/** @param {number | null | undefined} value */
function pnlClass(value) {
  if (value === null || value === undefined) return "na";
  if (value > 0) return "pos";
  if (value < 0) return "neg";
  return "";
}

/** @param {number | null | undefined} value */
function fmtPnlOrNa(value) {
  if (value === null || value === undefined) return "N/A";
  return fmtPnl(value);
}

/** @param {number | null | undefined} value @param {number} [digits] */
function fmtStrategyProfit(value, digits = 2) {
  if (value === null || value === undefined) return "N/A";
  const sign = value > 0 ? "+" : "";
  return `${sign}${fmtNum(value, digits)}`;
}

/** @param {number | null | undefined} value */
function fmtPercentDeposit(value) {
  if (value === null || value === undefined) return "N/A";
  const sign = value > 0 ? "+" : value < 0 ? "−" : "";
  return `${sign}${Math.abs(value).toFixed(2)}%`;
}

/** @param {number} value */
function compactK(value) {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(2)}M`;
  if (value >= 1000) return `${Math.round(value / 1000)}K`;
  return String(Math.round(value));
}

/** @param {HTMLInputElement | HTMLSelectElement | null | undefined} el @param {string} value */
function setInputIfIdle(el, value) {
  if (!el || document.activeElement === el) return;
  el.value = value;
}

/** @param {HTMLInputElement | null | undefined} el @param {boolean} checked */
function setCheckboxIfIdle(el, checked) {
  if (!el || document.activeElement === el) return;
  el.checked = checked;
}

window.fmtNum = fmtNum;
window.fmtPnl = fmtPnl;
window.pnlClass = pnlClass;
window.fmtPnlOrNa = fmtPnlOrNa;
window.fmtStrategyProfit = fmtStrategyProfit;
window.fmtPercentDeposit = fmtPercentDeposit;
window.compactK = compactK;
window.setInputIfIdle = setInputIfIdle;
window.setCheckboxIfIdle = setCheckboxIfIdle;
