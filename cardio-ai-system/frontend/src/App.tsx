import { Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { AppShell } from "@/components/app/app-shell";
import { LoginPage } from "@/pages/LoginPage";
import { ConsultationPage } from "@/pages/ConsultationPage";
import { HistoryPage } from "@/pages/HistoryPage";
import { HomePage } from "@/pages/HomePage";
import { GuidancePage } from "@/pages/GuidancePage";
import { NotesPage } from "@/pages/NotesPage";
import { PatientsPage } from "@/pages/PatientsPage";
import { SecurityPage } from "@/pages/SecurityPage";
import { ResearchAgentsPage } from "@/pages/ResearchAgentsPage";
import { NotFoundPage } from "@/pages/NotFoundPage";
import { PrivacyPage } from "@/pages/PrivacyPage";
import { TermsPage } from "@/pages/TermsPage";
import { ThankYouPage } from "@/pages/ThankYouPage";
import { useAuth } from "@/lib/auth";
import { IDLE_LOCK_MS, useIdleAutoLock } from "@/lib/idle-lock";
import { StorageNotice } from "@/components/app/storage-notice";

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

/**
 * Gate for the authed workspace. Unknown paths get the custom 404 regardless
 * of sign-in state (a typo shouldn't bounce you to the login form); known
 * private paths keep the sign-in-or-redirect behaviour.
 */
const PRIVATE_PREFIXES = [
  "/consultation",
  "/diagnose",
  "/live",
  "/workflow",
  "/history",
  "/notes",
  "/patients",
  "/security",
  "/agents",
  "/thank-you"
];

function AuthGate({ children }: { children: React.ReactNode }) {
  const { pathname } = useLocation();
  const known =
    pathname === "/" || PRIVATE_PREFIXES.some((prefix) => pathname.startsWith(prefix));

  if (!known) {
    return (
      <AppShell>
        <NotFoundPage />
      </AppShell>
    );
  }
  return <RequireAuth>{children}</RequireAuth>;
}

export default function App() {
  return (
    <>
      <StorageNotice />
      <Routes>
      <Route path="/login" element={<LoginPage />} />
      {/* Public legal pages — reachable without signing in. */}
      <Route
        path="/privacy"
        element={
          <AppShell>
            <PrivacyPage />
          </AppShell>
        }
      />
      <Route
        path="/terms"
        element={
          <AppShell>
            <TermsPage />
          </AppShell>
        }
      />
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
          <AuthGate>
            <Routes>
              <Route path="/" element={<HomePage />} />
              {/* The consultation workspace: quick (audio-first) and full modes on one screen. */}
              <Route path="/consultation" element={<ConsultationPage />} />
              {/* Previous entry points forward to the merged workspace. */}
              <Route path="/diagnose" element={<Navigate to="/consultation" replace />} />
              <Route path="/live" element={<Navigate to="/consultation" replace />} />
              <Route path="/workflow/start" element={<Navigate to="/consultation" replace />} />
              <Route path="/workflow/session" element={<Navigate to="/consultation" replace />} />
              <Route path="/history" element={<HistoryPage />} />
              <Route path="/notes" element={<NotesPage />} />
              <Route path="/patients" element={<PatientsPage />} />
              <Route path="/security" element={<SecurityPage />} />
              <Route path="/agents" element={<ResearchAgentsPage />} />
              <Route path="/thank-you" element={<ThankYouPage />} />
              {/* Unknown in-app route → custom 404 instead of a silent bounce. */}
              <Route path="*" element={<NotFoundPage />} />
            </Routes>
          </AuthGate>
        }
      />
      </Routes>
    </>
  );
}
