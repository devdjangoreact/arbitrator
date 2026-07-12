/** @param {string} name @param {HTMLElement | null} navEl */
function showPage(name, navEl) {
  document.querySelectorAll(".page").forEach((page) => page.classList.remove("active"));
  const target = document.getElementById(`page-${name}`);
  if (target) target.classList.add("active");

  document.querySelectorAll(".nav-item").forEach((item) => item.classList.remove("active"));
  const activeNav = navEl || document.querySelector(`.nav-item[data-page="${name}"]`);
  if (activeNav) activeNav.classList.add("active");

  AppState.activePage = name;

  if (name === "opportunity") {
    if (typeof startOpportunityWs === "function") startOpportunityWs();
  } else if (typeof stopOpportunityWs === "function") {
    stopOpportunityWs();
  }

  if (name === "monitors") {
    if (typeof startMonitorsWs === "function") startMonitorsWs();
  } else if (typeof stopMonitorsWs === "function") {
    stopMonitorsWs();
  }
}

function bindNavigation() {
  document.querySelectorAll(".nav-item[data-page]").forEach((item) => {
    item.addEventListener("click", () => {
      const page = item.getAttribute("data-page");
      if (page) showPage(page, item);
    });
  });
}

function updateOrdersNavBadge(openCount) {
  const el = Dom.nav.ordersCount();
  if (!el) return;
  if (openCount === null || openCount === undefined) {
    el.textContent = "—";
    return;
  }
  el.textContent = String(openCount);
}

document.addEventListener("DOMContentLoaded", () => {
  bindNavigation();
  if (typeof initScreener === "function") initScreener();
  if (typeof initOrders === "function") initOrders();
  if (typeof initSettings === "function") initSettings();
  if (typeof initOpportunity === "function") initOpportunity();
  if (typeof initPaperTrades === "function") initPaperTrades();
  if (typeof initMonitors === "function") initMonitors();
});

window.showPage = showPage;
window.updateOrdersNavBadge = updateOrdersNavBadge;
