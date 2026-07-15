import { create } from "zustand";

interface AppState {
  wsConnected: boolean;
  setWsConnected: (connected: boolean) => void;
  // We can add more global state here later, e.g., notifications, theme
}

export const useAppStore = create<AppState>((set) => ({
  wsConnected: false,
  setWsConnected: (connected) => set({ wsConnected: connected }),
}));
