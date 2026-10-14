import { authFetch } from "@/lib/auth";
import type {
  AiInsightsResponse,
  DiagnosisResponse,
  FinalReport,
  LearnedPhrase,
  LearnedSuppression,
  LearnedVocabulary,
  MedicationReview,
  ReportImageAnalysis,
  ResearchAgent,
} from "@/lib/types";

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

// ---------------------------------------------------------------------------
// Report screening (reference ranges) + structured SOAP note
// ---------------------------------------------------------------------------

export type LabFlag = {
  key: string;
  name: string;
  value?: number;
  value_text?: string;
  unit?: string;
  /** How the value's unit reads on screen — says "(computed)" for a derived one. */
  unit_label?: string;
  /** False when a printed unit could not be read; the value was banded as primary. */
  unit_read?: boolean;
  reference?: string;
  status: string;
  severity: "critical" | "abnormal" | "normal";
  matched_text?: string;
  explanation?: string;
  note?: string;
  source?: string;
  /** True for a lipid fraction worked out from the printed values (ADR-023). */
  computed?: boolean;
  /** The arithmetic behind a computed value, in the unit it is stated in. */
  derivation?: string;
  /** The operands as they were subtracted, in the computed value's unit. */
  computed_from?: Record<string, number>;
};

export type ScreenReportResult = {
  values: LabFlag[];
  text_flags: LabFlag[];
  summary: { critical: number; abnormal: number; normal: number; computed: number; parsed: boolean };
  message: string;
};

export async function screenReportText(text: string): Promise<ScreenReportResult> {
  const response = await authFetch("/api/screen-report", {
    method: "POST",
    body: JSON.stringify({ text }),
  });
  if (!response.ok) {
    throw new Error("Report screening failed.");
  }
  return (await response.json()) as ScreenReportResult;
}

export type SoapNote = {
  subjective: string[];
  objective: string[];
  assessment: string[];
  plan: string[];
  entities: {
    medications: { name: string; dose_mg?: string | null; matched: string }[];
    durations: string[];
    risk_factors: string[];
  };
  note: string;
};

export async function fetchSoapNote(input: {
  transcript: { speaker: string; text: string }[];
  symptoms: string[];
  reportText: string;
  riskLevel: string;
}): Promise<SoapNote> {
  const response = await authFetch("/api/soap-note", {
    method: "POST",
    body: JSON.stringify({
      transcript: input.transcript,
      symptoms: input.symptoms,
      report_text: input.reportText,
      risk_level: input.riskLevel,
    }),
  });
  if (!response.ok) {
    throw new Error("SOAP note generation failed.");
  }
  const body = (await response.json()) as { note?: SoapNote; error?: string };
  if (body.error || !body.note) {
    throw new Error(body.error ?? "No note returned.");
  }
  return body.note;
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

// ---------------------------------------------------------------------------
// Medication recommendation & safety review
// ---------------------------------------------------------------------------

export type MedicationReviewInput = {
  /** Narrative / transcript of the encounter. */
  text: string;
  /** Lab report text — parsed into the renal, potassium and troponin gates. */
  reportText: string;
  age: string;
  sex: string;
  /**
   * Race/ethnicity as recorded, because the pooled cohort equations publish a
   * separate model per group. "" leaves it unrecorded, and the review then
   * reports the higher of the two sex-matched models instead of choosing one.
   */
  race: string;
  /** "" leaves the status unknown, which the review reports as a gap. */
  pregnancy: "" | "yes" | "no";
  /** Free text; commas separate entries. */
  conditions: string;
  allergies: string;
  currentMedications: string;
};

function splitList(value: string): string[] {
  return value
    .split(/[,;\n]/)
    .map((entry) => entry.trim())
    .filter(Boolean);
}

export async function reviewMedications(input: MedicationReviewInput): Promise<MedicationReview> {
  const response = await authFetch("/api/medication-review", {
    method: "POST",
    body: JSON.stringify({
      text: input.text,
      report_text: input.reportText,
      age: input.age.trim(),
      sex: input.sex,
      race: input.race.trim() || undefined,
      pregnancy: input.pregnancy === "" ? undefined : input.pregnancy === "yes",
      conditions: splitList(input.conditions),
      allergies: splitList(input.allergies),
      current_medications: splitList(input.currentMedications),
    }),
  });
  if (response.status === 401) {
    throw new Error("Your session has expired. Please sign in again.");
  }
  if (!response.ok) {
    throw new Error("Medication review failed.");
  }
  const body = (await response.json()) as {
    symptoms?: string[];
    diagnosis?: DiagnosisResponse | null;
    medications?: MedicationReview;
    extracted?: { labs_used: Record<string, number> };
    error?: string;
  };
  // The endpoint wraps the review alongside the screening result; the page
  // works with the review itself plus the context that produced it.
  if (body.error || !body.medications) {
    throw new Error(body.error ?? "No medication review returned.");
  }
  return {
    ...body.medications,
    symptoms: body.symptoms ?? [],
    diagnosis: body.diagnosis ?? null,
    extracted: body.extracted,
  };
}

// ---------------------------------------------------------------------------
// Self-learning — per-clinician taught vocabulary
// ---------------------------------------------------------------------------

export async function fetchLearnedVocabulary(): Promise<LearnedVocabulary> {
  const response = await authFetch("/api/learning/vocabulary");
  if (!response.ok) {
    throw new Error("Failed to load learned vocabulary.");
  }
  const payload = (await response.json()) as {
    phrases?: LearnedPhrase[];
    suppressions?: LearnedSuppression[];
    generation?: number;
    valid_concepts?: string[];
  };
  return {
    phrases: payload.phrases ?? [],
    suppressions: payload.suppressions ?? [],
    generation: payload.generation ?? 0,
    valid_concepts: payload.valid_concepts ?? [],
  };
}

export async function teachPhrase(concept: string, phrase: string, origin: "feedback" | "manual" = "manual"): Promise<LearnedVocabulary> {
  const response = await authFetch("/api/learning/teach", {
    method: "POST",
    body: JSON.stringify({ concept, phrase, origin }),
  });
  if (response.status === 422) {
    const body = (await response.json()) as { detail?: string };
    throw new Error(body.detail ?? "PulseIQ could not learn that phrase.");
  }
  if (!response.ok) {
    throw new Error("Teaching failed.");
  }
  return fetchLearnedVocabulary();
}

export async function teachSuppression(pattern: string, note = ""): Promise<LearnedVocabulary> {
  const response = await authFetch("/api/learning/suppress", {
    method: "POST",
    body: JSON.stringify({ pattern, note }),
  });
  if (response.status === 422) {
    const body = (await response.json()) as { detail?: string };
    throw new Error(body.detail ?? "Invalid pattern.");
  }
  if (!response.ok) {
    throw new Error("Teaching the suppression failed.");
  }
  return fetchLearnedVocabulary();
}

async function deleteLearning(path: string): Promise<LearnedVocabulary> {
  const response = await authFetch(path, { method: "DELETE" });
  if (!response.ok) {
    throw new Error("Could not remove that entry.");
  }
  return fetchLearnedVocabulary();
}

export function forgetLearnedPhrase(id: number): Promise<LearnedVocabulary> {
  return deleteLearning(`/api/learning/phrase/${id}`);
}

export function forgetLearnedSuppression(id: number): Promise<LearnedVocabulary> {
  return deleteLearning(`/api/learning/suppression/${id}`);
}

export function clearLearnedVocabulary(): Promise<LearnedVocabulary> {
  return deleteLearning("/api/learning/vocabulary");
}
