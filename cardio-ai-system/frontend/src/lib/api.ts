import { authFetch } from "@/lib/auth";
import type { AiInsightsResponse, DiagnosisResponse, FinalReport, ReportImageAnalysis, ResearchAgent } from "@/lib/types";

export async function diagnoseText(text: string, patientName = ""): Promise<DiagnosisResponse> {
  const response = await authFetch("/api/diagnose", {
    method: "POST",
    body: JSON.stringify({ text, patient_name: patientName })
  });

  if (response.status === 401) {
    throw new Error("Your session has expired. Please sign in again.");
  }
  if (!response.ok) {
    throw new Error("Diagnosis request failed.");
  }

  return (await response.json()) as DiagnosisResponse;
}

export async function fetchAiInsights(text: string): Promise<AiInsightsResponse> {
  const response = await authFetch("/api/ai-insights", {
    method: "POST",
    body: JSON.stringify({ text })
  });

  if (!response.ok) {
    throw new Error("AI insights request failed.");
  }

  return (await response.json()) as AiInsightsResponse;
}

export async function fetchResearchAgents(): Promise<ResearchAgent[]> {
  const response = await authFetch("/api/research-agents");
  if (!response.ok) {
    throw new Error("Failed to fetch research agents.");
  }
  const payload = (await response.json()) as { agents?: ResearchAgent[] };
  return payload.agents ?? [];
}

export async function generateFinalReport(payload: Record<string, unknown>): Promise<FinalReport> {
  const response = await authFetch("/api/final-report", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error("Failed to generate final report.");
  }
  const body = (await response.json()) as { report?: FinalReport; error?: string };
  if (body.error || !body.report) {
    throw new Error(body.error ?? "No report returned.");
  }
  return body.report;
}

export async function analyzeReportImage(imageBase64: string, mimeType: string): Promise<ReportImageAnalysis> {
  const response = await authFetch("/api/analyze-report-image", {
    method: "POST",
    body: JSON.stringify({ image_base64: imageBase64, mime_type: mimeType }),
  });
  if (!response.ok) {
    throw new Error("Failed to analyze report image.");
  }
  const body = (await response.json()) as { analysis?: ReportImageAnalysis; error?: string };
  if (body.error || !body.analysis) {
    throw new Error(body.error ?? "No analysis returned.");
  }
  return body.analysis;
}
