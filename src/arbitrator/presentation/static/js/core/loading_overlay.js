/**
 * Toggle a full-area loading overlay (spinner + label).
 * @param {string} elementId
 * @param {boolean} visible
 * @param {string | undefined} message
 */
function setLoadingOverlay(elementId, visible, message) {
  const el = document.getElementById(elementId);
  if (!el) return;
  el.hidden = !visible;
  if (message) {
    const label = el.querySelector(".data-loading-label");
    if (label) label.textContent = message;
  }
}

window.setLoadingOverlay = setLoadingOverlay;
