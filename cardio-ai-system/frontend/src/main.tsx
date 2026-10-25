import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { ErrorBoundary } from "@/components/app/error-boundary";
import { AuthProvider } from "@/lib/auth";
import "./index.css";
import "./light-theme.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <BrowserRouter>
        <AuthProvider>
          <App />
        </AuthProvider>
      </BrowserRouter>
    </ErrorBoundary>
  </React.StrictMode>
);

/**
 * The installed app's offline shell.
 *
 * Production only: a worker caching `/assets/` in `vite dev` would serve a stale
 * module after a hot reload, which looks like a broken edit rather than a cache
 * and is a miserable thing to debug. Registration happens after load so the
 * first paint is never waiting on it, and a failure is non-fatal — the app runs
 * exactly as before without it.
 */
if (import.meta.env.PROD && "serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {
      /* offline support is an enhancement; the app needs no worker to run */
    });
  });
}
