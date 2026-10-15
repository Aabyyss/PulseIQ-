import { describe, expect, it } from "vitest";
import { buildConsultationPdf, PDF_DISCLAIMER } from "@/lib/pdfReport";
import type { FinalReport } from "@/lib/types";

/**
 * The PDF is the artifact a clinician hands over, and the failure this guards
 * against was invisible: sections drawn past the bottom of the paper stayed in
 * the file and were missing from the page, on a document that looked finished.
 * jsPDF keeps the text of every page in the output stream, so what is drawn and
 * what is on a page can both be asserted here without a viewer.
 */
function report(linesPerSection: number): FinalReport {
  const fill = (label: string) =>
    Array.from({ length: linesPerSection }, (_, index) => `${label} item ${index + 1} — reviewed and documented.`);
  return {
    title: "Cardiology consultation report",
    summary: "Stable exertional chest pain with a moderate-risk screening estimate; plan as documented below.",
    probable_diagnosis: fill("Diagnosis"),
    doctor_advice: fill("Advice"),
    medical_treatment_plan: fill("Treatment"),
    follow_up_plan: fill("Follow-up"),
    red_flags: fill("Red flag")
  };
}

const META = {
  patientName: "Demo Patient",
  patientAge: "58",
  patientGender: "Male",
  visitDate: "2026-10-16",
  doctorName: "Dr. Demo",
  chiefComplaint: "chest pain on exertion"
};

function text(doc: ReturnType<typeof buildConsultationPdf>): string {
  return doc.output() as unknown as string;
}

function occurrences(haystack: string, needle: string): number {
  return haystack.split(needle).length - 1;
}

describe("buildConsultationPdf", () => {
  it("keeps a short report on one page", () => {
    const doc = buildConsultationPdf(report(1), META);
    expect(doc.getNumberOfPages()).toBe(1);
    expect(text(doc)).toContain("Page 1 of 1");
  });

  it("paginates a long report instead of drawing past the paper", () => {
    const doc = buildConsultationPdf(report(12), META);
    expect(doc.getNumberOfPages()).toBeGreaterThan(1);
  });

  it("numbers and foots every page, and keeps the last section", () => {
    const long = report(12);
    const doc = buildConsultationPdf(long, META);
    const pages = doc.getNumberOfPages();
    const output = text(doc);

    for (let page = 1; page <= pages; page += 1) {
      expect(output, `page ${page}`).toContain(`Page ${page} of ${pages}`);
    }
    // One disclaimer per page — a footer on each, not only on the first.
    expect(occurrences(output, PDF_DISCLAIMER)).toBe(pages);
    // The last line of the last section survives the page breaks. Searched
    // without the em dash: non-ASCII characters are octal-escaped in the PDF
    // text stream, so a literal-with-punctuation assertion would be testing the
    // encoder rather than the layout.
    expect(output).toContain(`Red flag item ${long.red_flags.length}`);
  });

  it("survives an empty report without dropping the header or the footer", () => {
    const empty: FinalReport = {
      title: "",
      summary: "",
      probable_diagnosis: [],
      doctor_advice: [],
      medical_treatment_plan: [],
      follow_up_plan: [],
      red_flags: []
    };
    const doc = buildConsultationPdf(empty);
    expect(doc.getNumberOfPages()).toBe(1);
    const output = text(doc);
    expect(output).toContain("Consultation Report");
    expect(output).toContain("No summary available.");
    expect(output).toContain(PDF_DISCLAIMER);
  });
});
