import { useState } from "react";
import { SettingsPage } from "./pages/SettingsPage";
import { ScreenerPage } from "./pages/ScreenerPage";
import { OpportunityPage } from "./pages/OpportunityPage";
import { OrdersPage } from "./pages/OrdersPage";
import { MonitorsPage } from "./pages/MonitorsPage";

function App() {
  const [currentPage, setCurrentPage] = useState<string>(() => {
    const params = new URLSearchParams(window.location.search);
    return params.get("page") || "screener";
  });

  const navigate = (page: string) => {
    setCurrentPage(page);
    window.history.pushState(null, "", `/?page=${page}`);
  };

  const navItems = [
    { id: "settings", label: "Налаштування" },
    { id: "screener", label: "Скрінер" },
    { id: "monitors", label: "Історія Скрінера" },
    { id: "orders", label: "Ордери" },
    { id: "opportunity", label: "Opportunity" },
  ];

  return (
    <div className="flex h-screen w-full bg-gray-50 font-sans text-gray-900 overflow-hidden m-0 p-0">
      {/* Sidebar Navigation */}
      <nav className="w-64 shrink-0 bg-white border-r border-gray-200 flex flex-col h-full m-0 p-0">
        <div className="p-4 border-b border-gray-200">
          <h2 className="text-xl font-bold text-indigo-600 m-0">Arbitrator</h2>
        </div>
        <div className="flex-1 overflow-y-auto py-2">
          <ul className="space-y-1 px-2 m-0">
            {navItems.map((item) => (
              <li key={item.id}>
                <button
                  onClick={() => navigate(item.id)}
                  className={`w-full text-left px-3 py-2 rounded-md transition-colors ${
                    currentPage === item.id
                      ? "bg-indigo-50 text-indigo-700 font-medium"
                      : "text-gray-700 hover:bg-gray-50"
                  }`}
                >
                  {item.label}
                </button>
              </li>
            ))}
          </ul>
        </div>
      </nav>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col h-full w-full m-0 p-0 overflow-hidden">
        <main className="flex-1 overflow-y-auto w-full m-0 p-0">
          {currentPage === "settings" && <SettingsPage />}
          {currentPage === "screener" && <ScreenerPage />}
          {currentPage === "monitors" && <MonitorsPage />}
          {currentPage === "opportunity" && <OpportunityPage />}
          {currentPage === "orders" && <OrdersPage />}
        </main>
      </div>
    </div>
  );
}

export default App;
