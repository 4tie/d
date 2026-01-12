import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import { ToastProvider } from "./components/toast";
import { SelectedStrategyProvider } from "./lib/strategy-context";
import App from "./App";
import "./styles.css";

const storedTheme = (() => {
  try {
    return localStorage.getItem("st_theme") || "";
  } catch {
    return "";
  }
})();

if (storedTheme) {
  document.documentElement.dataset.theme = storedTheme;
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <ToastProvider>
          <SelectedStrategyProvider>
            <App />
          </SelectedStrategyProvider>
        </ToastProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>
);
