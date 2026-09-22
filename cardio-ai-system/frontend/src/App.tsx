import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { AppShell } from "@/components/app/app-shell";
import { LoginPage } from "@/pages/LoginPage";
import { DiagnosePage } from "@/pages/DiagnosePage";
import { HistoryPage } from "@/pages/HistoryPage";
import { HomePage } from "@/pages/HomePage";
import { LiveConsultationPage } from "@/pages/LiveConsultationPage";
import { ResearchAgentsPage } from "@/pages/ResearchAgentsPage";
import { WorkflowSessionPage } from "@/pages/WorkflowSessionPage";
import { WorkflowStartPage } from "@/pages/WorkflowStartPage";
import { useAuth } from "@/lib/auth";

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user, ready } = useAuth();
  const location = useLocation();

  if (!ready) return <AppShell><LoadingScreen /></AppShell>;

  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  return <AppShell>{children}</AppShell>;
}

function LoadingScreen() {
  return (
    <div className="flex min-h-[60vh] items-center justify-center">
      <div className="flex flex-col items-center gap-3 text-sm text-muted">
        <span className="h-6 w-6 animate-spin rounded-full border-2 border-line border-t-accent" />
        Loading your workspace…
      </div>
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="*"
        element={
          <RequireAuth>
            <Routes>
              <Route path="/" element={<HomePage />} />
              <Route path="/diagnose" element={<DiagnosePage />} />
              <Route path="/live" element={<LiveConsultationPage />} />
              <Route path="/workflow/start" element={<WorkflowStartPage />} />
              <Route path="/workflow/session" element={<WorkflowSessionPage /> } />
              <Route path="/history" element={<HistoryPage />} />
              <Route path="/agents" element={<ResearchAgentsPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </RequireAuth>
        }
      />
    </Routes>
  );
}
