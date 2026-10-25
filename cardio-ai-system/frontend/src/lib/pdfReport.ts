import type { jsPDF } from "jspdf";
import type { FinalReport } from "@/lib/types";

/**
 * A4 geometry, in millimetres, named once so the flow of the document is decided
 * in one place: the writer places sections down the page and moves to a new one
 * when the next block would not fit.
 *
 * It did not always: every section was drawn at an increasing y and nothing
 * checked the bottom of the page, so a report with a long assessment drew its
 * later sections below the paper — the text was in the PDF and invisible on it,
 * and the page still looked complete.
 */
const PAGE_WIDTH = 210;
const PAGE_HEIGHT = 297;
/** A visible page is 297mm; the printable area stops short of the footer. */
const FOOTER_Y = PAGE_HEIGHT - 12;
const CONTENT_BOTTOM = FOOTER_Y - 17;
const CONTENT_TOP = 34;
const MARGIN = 16;
const CONTENT_WIDTH = 178;
const LINE_HEIGHT = 5;

export const PDF_DISCLAIMER =
  "Decision-support output. Final clinical judgment remains with the treating physician.";

/** Draw the page header band on the current page. */
function drawHeader(doc: jsPDF, title: string) {
  doc.setFillColor(15, 23, 42);
  doc.rect(0, 0, PAGE_WIDTH, 24, "F");
  doc.setTextColor(255, 255, 255);
  doc.setFont("helvetica", "bold");
  doc.setFontSize(15);
  doc.text(title || "Consultation Report", MARGIN, 15);
  doc.setFontSize(11);
}

/** Move to a new page when `needed` millimetres would not fit below `y`. */
function ensureSpace(doc: jsPDF, y: number, needed: number): number {
  if (y + needed <= CONTENT_BOTTOM) return y;
  doc.addPage();
  return CONTENT_TOP;
}

function writeParagraph(doc: jsPDF, text: string, y: number): number {
  const lines = doc.splitTextToSize(text, CONTENT_WIDTH) as string[];
  doc.setFont("helvetica", "normal");
  doc.setTextColor(31, 41, 55);
  let cursor = y;
  for (const line of lines) {
    cursor = ensureSpace(doc, cursor, LINE_HEIGHT);
    doc.text(line, MARGIN, cursor);
    cursor += LINE_HEIGHT;
  }
  return cursor;
}

function writeSection(doc: jsPDF, title: string, lines: string[], y: number): number {
  let cursor = ensureSpace(doc, y, 12);
  doc.setFont("helvetica", "bold");
  doc.setTextColor(17, 24, 39);
  doc.text(title, MARGIN, cursor);
  cursor += 6;
  doc.setFont("helvetica", "normal");
  doc.setTextColor(31, 41, 55);
  for (const line of lines) {
    const wrapped = doc.splitTextToSize(`- ${line}`, CONTENT_WIDTH) as string[];
    const height = wrapped.length * LINE_HEIGHT;
    cursor = ensureSpace(doc, cursor, height);
    doc.text(wrapped, MARGIN + 2, cursor);
    cursor += height + 1;
  }
  return cursor + 2;
}

/** Footer and page numbering, stamped after the content so the total is known. */
function stampFooters(doc: jsPDF) {
  const total = doc.getNumberOfPages();
  for (let page = 1; page <= total; page += 1) {
    doc.setPage(page);
    doc.setFont("helvetica", "normal");
    doc.setFontSize(9);
    doc.setTextColor(75, 85, 99);
    doc.text(PDF_DISCLAIMER, MARGIN, FOOTER_Y);
    doc.text(`Page ${page} of ${total}`, PAGE_WIDTH - MARGIN, FOOTER_Y, { align: "right" });
  }
}

export type PdfMeta = {
  patientName?: string;
  patientAge?: string;
  patientGender?: string;
  visitDate?: string;
  doctorName?: string;
  chiefComplaint?: string;
};

/**
 * Build the report document. Separate from the download so the layout can be
 * asserted (page count, every page footed) without opening a browser download.
 *
 * Async because jsPDF is imported on demand: a PDF writer is never needed to
 * read the workspace, and carrying it in the first payload delayed every screen
 * that does not export anything. The type import above is erased at build time,
 * so this module no longer pulls the library into the initial chunk.
 */
export async function buildConsultationPdf(report: FinalReport, meta?: PdfMeta): Promise<jsPDF> {
  const { jsPDF: JsPdf } = await import("jspdf");
  const doc = new JsPdf({ unit: "mm", format: "a4" });
  drawHeader(doc, report.title);

  let y = CONTENT_TOP;
  if (meta) {
    doc.setFont("helvetica", "bold");
    doc.setTextColor(17, 24, 39);
    doc.setFontSize(11);
    doc.text("Patient/Visit Details", MARGIN, y);
    y += 6;
    doc.setFont("helvetica", "normal");
    for (const line of [
      `Patient: ${meta.patientName || "-"}`,
      `Age/Gender: ${meta.patientAge || "-"} / ${meta.patientGender || "-"}`,
      `Visit Date: ${meta.visitDate || "-"}`,
      `Doctor: ${meta.doctorName || "-"}`,
      `Chief Complaint: ${meta.chiefComplaint || "-"}`
    ]) {
      y = writeParagraph(doc, line, y) + 0.5;
    }
    y += 4;
  }

  y = ensureSpace(doc, y, 12);
  doc.setFont("helvetica", "bold");
  doc.setTextColor(17, 24, 39);
  doc.setFontSize(11);
  doc.text("Clinical Summary", MARGIN, y);
  y = writeParagraph(doc, report.summary || "No summary available.", y + 6) + 6;

  y = writeSection(doc, "Probable Diagnosis", report.probable_diagnosis || [], y);
  y = writeSection(doc, "Doctor Advice", report.doctor_advice || [], y);
  y = writeSection(doc, "Medical Treatment", report.medical_treatment_plan || [], y);
  y = writeSection(doc, "Follow-up Plan", report.follow_up_plan || [], y);
  y = writeSection(doc, "Red Flags", report.red_flags || [], y);

  stampFooters(doc);
  return doc;
}

export async function exportConsultationPdf(report: FinalReport, meta?: PdfMeta) {
  const doc = await buildConsultationPdf(report, meta);
  doc.save(`cardio-consult-report-${Date.now()}.pdf`);
}
