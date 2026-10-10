import { authFetch } from "@/lib/auth";
import type { FhirExportResult } from "@/lib/types";

/**
 * The visit findings the FHIR export is built from. Deliberately the same
 * fields the consultation screen already holds — nothing is retyped for the
 * export, and the server derives every resource from them.
 */
export type FhirExportInput = {
  patientName: string;
  patientAge: string;
  patientGender: string;
  visitDate: string;
  doctorName: string;
  chiefComplaint: string;
  narrative: string;
  reportText: string;
  riskLevel: string;
  symptoms: string[];
  conditions: string;
  allergies: string;
  currentMedications: string;
  pregnancy?: "" | "yes" | "no";
};

export type FhirExportOutcome = {
  counts: Record<string, number>;
  missing: string[];
  caveats: string[];
  disclaimer: string;
  fileName: string;
};

function splitList(value: string): string[] {
  return value
    .split(/[,;\n]/)
    .map((entry) => entry.trim())
    .filter(Boolean);
}

/**
 * Download a JSON document the way a clinician expects a file export to behave:
 * a Blob handed to the browser's own download, so nothing leaves the device and
 * no library is needed. `application/fhir+json` is the registered media type.
 */
function downloadJson(fileName: string, payload: unknown) {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/fhir+json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = fileName;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

/**
 * Export the captured encounter as a FHIR R4 Bundle and hand it to the browser
 * as a file. The bundle is built server-side (deterministic rules, no LLM), so
 * the page and the endpoint cannot disagree about the same patient.
 */
export async function exportFhirBundle(input: FhirExportInput): Promise<FhirExportOutcome> {
  const response = await authFetch("/api/fhir-export", {
    method: "POST",
    body: JSON.stringify({
      patient_name: input.patientName,
      patient_age: input.patientAge,
      patient_gender: input.patientGender,
      visit_date: input.visitDate,
      doctor_name: input.doctorName,
      chief_complaint: input.chiefComplaint,
      text: input.narrative,
      report_text: input.reportText,
      risk_level: input.riskLevel,
      symptom_notes: input.symptoms,
      conditions: splitList(input.conditions),
      allergies: splitList(input.allergies),
      current_medications: splitList(input.currentMedications),
      pregnancy: input.pregnancy === "yes" ? true : input.pregnancy === "no" ? false : undefined
    })
  });
  if (!response.ok) {
    throw new Error("Failed to build the FHIR export.");
  }
  const result = (await response.json()) as FhirExportResult;
  if (result.error || !result.bundle) {
    throw new Error(result.error ?? "No FHIR bundle returned.");
  }
  const fileName = `cardio-fhir-${new Date().toISOString().slice(0, 10)}.json`;
  downloadJson(fileName, result.bundle);
  return {
    counts: result.resource_counts ?? {},
    missing: result.missing_information ?? [],
    caveats: result.caveats ?? [],
    disclaimer: result.disclaimer,
    fileName
  };
}
