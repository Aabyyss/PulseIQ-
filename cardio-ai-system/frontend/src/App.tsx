import { Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { AppShell } from "@/components/app/app-shell";
import { LoginPage } from "@/pages/LoginPage";
import { DiagnosePage } from "@/pages/DiagnosePage";
import { HistoryPage } from "@/pages/HistoryPage";
import { HomePage } from "@/pages/HomePage";
import { GuidancePage } from "@/pages/GuidancePage";
import { NotesPage } from "@/pages/NotesPage";
import { PatientsPage } from "@/pages/PatientsPage";
import { SecurityPage } from "@/pages/SecurityPage";
import { LiveConsultationPage } from "@/pages/LiveConsultationPage";
import { ResearchAgentsPage } from "@/pages/ResearchAgentsPage";
import { WorkflowSessionPage } from "@/pages/WorkflowSessionPage";
import { WorkflowStartPage } from "@/pages/WorkflowStartPage";
import { useAuth } from "@/lib/auth";
import { IDLE_LOCK_MS, useIdleAutoLock } from "@/lib/idle-lock";

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user, ready, signOut } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();

  // Auto-lock: after 15 idle minutes, sign out and route to the login page.
  useIdleAutoLock(IDLE_LOCK_MS, Boolean(user && ready), () => {
    void signOut().then(() => navigate("/login", { replace: true, state: { idle: true } }));
  });

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
        path="/guidance"
        element={
          <AppShell>
            <GuidancePage />
          </AppShell>
        }
      />
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
              <Route path="/notes" element={<NotesPage />} />
              <Route path="/patients" element={<PatientsPage />} />
              <Route path="/security" element={<SecurityPage />} />
              <Route path="/agents" element={<ResearchAgentsPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </RequireAuth>
        }
      />
    </Routes>
  );
}
