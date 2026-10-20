import "@fontsource/cinzel/600.css";
import "@fontsource/inter/400.css";
import "@fontsource/inter/600.css";
import "@fontsource/jetbrains-mono/500.css";
import React from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import { registerSW } from "virtual:pwa-register";
import { App } from "./App";
import { useSession } from "./api";
import "./styles.css";

const updateSW = registerSW({
  onNeedRefresh() {
    useSession.getState().setUpdateReady(true);
  },
});

(window as unknown as { __applyUpdate?: () => void }).__applyUpdate = () => updateSW(true);
window.addEventListener("pwa-update", () => useSession.getState().setUpdateReady(true));

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={new QueryClient()}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
