export type DiagnosisResponse = {
  text: string;
  symptoms: string[];
  features: number[];
  prediction: number;
  probability: number;
  risk_level: "Low" | "Medium" | "High";
  patient_name?: string;
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
  original_transcript?: string;
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
  medical_entities?: {
    medications: { name: string; dose_mg?: string | null; matched: string }[];
    durations: string[];
    risk_factors: string[];
  };
  ai_copilot?: {
    doctor_questions: string[];
    recommended_tests: string[];
    next_steps: string[];
    diagnostic_impression: string[];
    urgency: "low" | "moderate" | "high";
    safety_note: string;
    /** Guideline/reason behind each exact suggestion string. */
    suggestion_sources?: Record<string, string>;
    /** Honest plan-level confidence, including the not-enough-info state. */
    confidence?: {
      confidence: "low" | "moderate" | "high";
      insufficient_information: "true" | "false";
      reason: string;
    };
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

// Self-learning — per-clinician taught vocabulary
export type LearnedPhrase = {
  id: number;
  concept: string;
  phrase: string;
  origin: "feedback" | "manual";
  created_at: string;
};

export type LearnedSuppression = {
  id: number;
  pattern: string;
  note: string;
  created_at: string;
};

export type LearnedVocabulary = {
  phrases: LearnedPhrase[];
  suppressions: LearnedSuppression[];
  generation: number;
  valid_concepts: string[];
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

// Medication recommendation & safety review (POST /medication-review)
export type MedicationRecommendation = {
  drug: string;
  drug_class: string;
  status: "recommended" | "alternative" | "already-documented";
  priority: number;
  indications: string[];
  triggered_by: string[];
  dose_note: string;
  monitoring: string[];
  review_flags: string[];
  evidence: string;
  action: string;
};

export type MedicationBlock = {
  kind: "allergy" | "condition" | "lab";
  severity: "absolute" | "relative";
  trigger: string;
  note: string;
};

export type MedicationContraindication = {
  drug: string;
  drug_class: string;
  status: "contraindicated" | "review-before-use";
  severity: "absolute" | "relative";
  blocks: MedicationBlock[];
  already_documented: boolean;
  note: string;
  evidence: string;
};

export type MedicationAllergyAlert = {
  drug: string;
  drug_class: string;
  matched_terms: string[];
  action: string;
  alternative: string;
};

export type MedicationInteractionAlert = {
  pair: string[];
  drugs: string[];
  severity: "major" | "moderate";
  note: string;
  action: string;
};

export type MedicationReview = {
  pathway: { urgency: "emergency" | "urgent" | "routine"; statement: string; rationale: string[] };
  indications: { name: string; triggered_by: string }[];
  patient_profile: {
    age: number | null;
    sex: string | null;
    conditions: string[];
    condition_text: string[];
    allergies: string[];
    current_medications: string[];
    current_medication_classes: string[];
    /** null = not recorded (which is itself reported under missing_information). */
    pregnancy: boolean | null;
    labs_considered: Record<string, number>;
  };
  recommendations: MedicationRecommendation[];
  contraindicated: MedicationContraindication[];
  allergy_alerts: MedicationAllergyAlert[];
  interaction_alerts: MedicationInteractionAlert[];
  monitoring_plan: string[];
  missing_information: string[];
  summary: string;
  disclaimer: string;
  symptoms?: string[];
  diagnosis?: DiagnosisResponse | null;
  extracted?: { labs_used: Record<string, number> };
  error?: string;
};

export type ReportImageAnalysis = {
  summary: string;
  key_findings: string[];
  possible_diagnosis: string[];
  recommended_tests: string[];
  next_steps: string[];
  red_flags: string[];
};
