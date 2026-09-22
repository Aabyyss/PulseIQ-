export type DiagnosisResponse = {
  text: string;
  symptoms: string[];
  features: number[];
  prediction: number;
  probability: number;
  risk_level: "Low" | "Medium" | "High";
};

export type DiagnosisHistoryItem = DiagnosisResponse & {
  id?: number;
  createdAt: string;
};

export type AiInsightsResponse = {
  diagnosis?: DiagnosisResponse;
  insights?: string;
  error?: string;
};

export type PainPoint = {
  symptom: string;
  x: number;
  y: number;
  z: number;
  label: string;
};

export type RealtimeConsultationEvent = {
  speaker: "doctor" | "patient";
  transcript: string;
  symptoms: string[];
  diagnosis?: DiagnosisResponse | null;
  pain_points: PainPoint[];
  cardiac_regions: {
    region: string;
    likelihood: "low" | "moderate" | "high";
    clinical_note: string;
    marker: { x: number; y: number; z: number };
  }[];
  doctor_next_questions: string[];
  patient_recommendations: string[];
  ai_copilot?: {
    doctor_questions: string[];
    recommended_tests: string[];
    next_steps: string[];
    diagnostic_impression: string[];
    urgency: "low" | "moderate" | "high";
    safety_note: string;
  };
  uncertainty?: {
    confidence_score: number;
    confidence_bucket: string;
  };
  causal_hypotheses?: string[];
  multimodal_fusion?: Record<string, unknown>;
  guideline_alignment?: string[];
  knowledge_graph_links?: Record<string, string[]>;
  evidence_snippets?: { topic: string; summary: string }[];
  fairness_snapshot?: Record<string, unknown>;
  robustness_checks?: Record<string, unknown>;
  human_feedback_stub?: Record<string, unknown>;
  evaluation_snapshot?: Record<string, unknown>;
  error?: string;
};

export type ResearchAgent = {
  name: string;
  focus: string;
};

export type FinalReport = {
  title: string;
  summary: string;
  probable_diagnosis: string[];
  doctor_advice: string[];
  medical_treatment_plan: string[];
  follow_up_plan: string[];
  red_flags: string[];
};

export type ReportImageAnalysis = {
  summary: string;
  key_findings: string[];
  possible_diagnosis: string[];
  recommended_tests: string[];
  next_steps: string[];
  red_flags: string[];
};
