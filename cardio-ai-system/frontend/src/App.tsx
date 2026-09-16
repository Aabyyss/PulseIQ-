import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "@/components/app/app-shell";
import { DiagnosePage } from "@/pages/DiagnosePage";
import { HistoryPage } from "@/pages/HistoryPage";
import { HomePage } from "@/pages/HomePage";
import { LiveConsultationPage } from "@/pages/LiveConsultationPage";
import { ResearchAgentsPage } from "@/pages/ResearchAgentsPage";
import { WorkflowSessionPage } from "@/pages/WorkflowSessionPage";
import { WorkflowStartPage } from "@/pages/WorkflowStartPage";

export default function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/diagnose" element={<DiagnosePage />} />
        <Route path="/live" element={<LiveConsultationPage />} />
        <Route path="/workflow/start" element={<WorkflowStartPage />} />
        <Route path="/workflow/session" element={<WorkflowSessionPage />} />
        <Route path="/history" element={<HistoryPage />} />
        <Route path="/agents" element={<ResearchAgentsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AppShell>
  );
}
