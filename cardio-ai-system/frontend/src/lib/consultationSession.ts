import { authFetch } from "@/lib/auth";
import type { RiskLevel } from "@/components/app/risk-pill";
import { exportConsultationPdf } from "@/lib/pdfReport";
import { saveConsultation } from "@/lib/history";
import type { FinalReport } from "@/lib/types";
import type { TranscriptLine } from "@/lib/useConsultationCapture";

export type VisitMeta = {
  patientName: string;
  patientAge: string;
  patientGender: string;
  visitDate: string;
  doctorName: string;
  chiefComplaint: string;
};

export type SaveVisitResult = {
  report: FinalReport;
  saved: boolean;
  savedId?: number;
  pdfExported: boolean;
};

/**
 * One-call end of visit: ask the LLM for the structured report, hand it to
 * the clinician as a PDF download and persist the record to the account.
 * Used by both the live copilot's Save button and the workflow's export, so
 * "finishing a visit" is always one action.
 */
export async function finishConsultation(input: {
  meta: VisitMeta;
  riskLevel: RiskLevel;
  lines: TranscriptLine[];
  symptomNotes: string[];
  doctorQuestions: string[];
  recommendedTests: string[];
  diagnosticImpression: string[];
  nextSteps: string[];
  reportText: string;
  lastHeardText: string;
  /** Capture locale of the encounter, shown in History (e.g. ur-PK). */
  spokenLanguage: string;
}): Promise<SaveVisitResult> {
  // Report generation calls the local LLM (30-90s on CPU), so the request
  // gets a long timeout instead of the default 15s API timeout.
  const response = await authFetch("/api/final-report", {
    method: "POST",
    body: JSON.stringify({
      patient_name: input.meta.patientName,
      patient_age: input.meta.patientAge,
      patient_gender: input.meta.patientGender,
      visit_date: input.meta.visitDate,
      doctor_name: input.meta.doctorName,
      chief_complaint: input.meta.chiefComplaint,
      report_text: input.reportText,
      last_heard_text: input.lastHeardText,
      risk_level: input.riskLevel,
      symptom_notes: input.symptomNotes,
      doctor_questions: input.doctorQuestions,
      recommended_tests: input.recommendedTests,
      diagnostic_impression: input.diagnosticImpression,
      next_steps: input.nextSteps
    }),
    timeoutMs: 150000
  });
  if (!response.ok) {
    throw new Error("Failed to generate final report.");
  }
  const reportBody = (await response.json()) as { report?: FinalReport; error?: string };
  if (reportBody.error || !reportBody.report) {
    throw new Error(reportBody.error ?? "No report returned.");
  }
  const report = reportBody.report;

  let pdfExported = true;
  try {
    exportConsultationPdf(report, {
      patientName: input.meta.patientName,
      patientAge: input.meta.patientAge,
      patientGender: input.meta.patientGender,
      visitDate: input.meta.visitDate,
      doctorName: input.meta.doctorName,
      chiefComplaint: input.meta.chiefComplaint
    });
  } catch {
    pdfExported = false; // popup/PDF failure must not block the save
  }

  let saved = false;
  let savedId: number | undefined;
  try {
    const result = await saveConsultation({
      patient_name: input.meta.patientName,
      patient_age: input.meta.patientAge,
      patient_gender: input.meta.patientGender,
      visit_date: input.meta.visitDate,
      doctor_name: input.meta.doctorName,
      chief_complaint: input.meta.chiefComplaint,
      risk_level: input.riskLevel,
      symptom_notes: input.symptomNotes,
      spoken_language: input.spokenLanguage,
      transcript: input.lines.map((line) => ({ speaker: line.speaker, text: line.text, timestamp: line.timestamp })),
      report,
      created_at: new Date().toISOString()
    });
    saved = Boolean(result);
    savedId = result?.id;
  } catch {
    saved = false; // keep the local PDF; the record can be re-saved
  }

  return { report, saved, savedId, pdfExported };
}
