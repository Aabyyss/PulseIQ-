import { jsPDF } from "jspdf";
import type { FinalReport } from "@/lib/types";

function writeSection(doc: jsPDF, title: string, lines: string[], y: number): number {
  doc.setFont("helvetica", "bold");
  doc.setTextColor(17, 24, 39);
  doc.text(title, 16, y);
  let cursor = y + 6;
  doc.setFont("helvetica", "normal");
  doc.setTextColor(31, 41, 55);
  lines.forEach((line) => {
    const wrapped = doc.splitTextToSize(`- ${line}`, 178);
    doc.text(wrapped, 18, cursor);
    cursor += wrapped.length * 5 + 1;
  });
  return cursor + 2;
}

export function exportConsultationPdf(
  report: FinalReport,
  meta?: {
    patientName?: string;
    patientAge?: string;
    patientGender?: string;
    visitDate?: string;
    doctorName?: string;
    chiefComplaint?: string;
  }
) {
  const doc = new jsPDF({ unit: "mm", format: "a4" });
  doc.setFillColor(15, 23, 42);
  doc.rect(0, 0, 210, 24, "F");
  doc.setTextColor(255, 255, 255);
  doc.setFont("helvetica", "bold");
  doc.setFontSize(15);
  doc.text(report.title || "Consultation Report", 16, 15);

  let y = 34;
  if (meta) {
    doc.setFont("helvetica", "bold");
    doc.setTextColor(17, 24, 39);
    doc.text("Patient/Visit Details", 16, y);
    y += 6;
    doc.setFont("helvetica", "normal");
    doc.text(`Patient: ${meta.patientName || "-"}`, 16, y);
    y += 5;
    doc.text(`Age/Gender: ${meta.patientAge || "-"} / ${meta.patientGender || "-"}`, 16, y);
    y += 5;
    doc.text(`Visit Date: ${meta.visitDate || "-"}`, 16, y);
    y += 5;
    doc.text(`Doctor: ${meta.doctorName || "-"}`, 16, y);
    y += 5;
    const complaint = doc.splitTextToSize(`Chief Complaint: ${meta.chiefComplaint || "-"}`, 178);
    doc.text(complaint, 16, y);
    y += complaint.length * 5 + 5;
  }
  doc.setTextColor(17, 24, 39);
  doc.setFontSize(11);
  doc.setFont("helvetica", "bold");
  doc.text("Clinical Summary", 16, y);
  doc.setFont("helvetica", "normal");
  const summary = doc.splitTextToSize(report.summary || "No summary available.", 178);
  doc.text(summary, 16, y + 6);
  y += summary.length * 5 + 12;

  y = writeSection(doc, "Probable Diagnosis", report.probable_diagnosis || [], y);
  y = writeSection(doc, "Doctor Advice", report.doctor_advice || [], y);
  y = writeSection(doc, "Medical Treatment", report.medical_treatment_plan || [], y);
  y = writeSection(doc, "Follow-up Plan", report.follow_up_plan || [], y);
  y = writeSection(doc, "Red Flags", report.red_flags || [], y);

  doc.setFontSize(9);
  doc.setTextColor(75, 85, 99);
  doc.text("Decision-support output. Final clinical judgment remains with the treating physician.", 16, 286);

  doc.save(`cardio-consult-report-${Date.now()}.pdf`);
}
