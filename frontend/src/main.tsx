import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "react-router-dom";

import { AuthProvider } from "./auth/auth-context";
import { router } from "./app/router";
import { AppErrorBoundary } from "./components/AppErrorBoundary";
import { ToastProvider } from "./components/ui";
import "./styles/tokens.css";
import "./styles/global.css";
import "./styles/components.css";
import "./styles/creator.css";
import "./styles/investor.css";
import "./styles/instruments.css";
import "./styles/shell.css";
import "./styles/landing.css";
import "./styles/premium.css";
import "./styles/dashboard.css";
import "./styles/workspace.css";
import "./styles/interaction.css";
import "./styles/landing-motion.css";

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } } });

createRoot(document.getElementById("root")!).render(
  <StrictMode><AppErrorBoundary><QueryClientProvider client={queryClient}><AuthProvider><ToastProvider><RouterProvider router={router} /></ToastProvider></AuthProvider></QueryClientProvider></AppErrorBoundary></StrictMode>,
);
