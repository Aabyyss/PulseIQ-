import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Download,
  FileText,
  HeartPulse,
  ImageUp,
  ListChecks,
  LoaderCircle,
  Mic,
  MicOff,
  Radio,
  ScanLine,
  Send,
  Stethoscope,
  User
} from "lucide-react";
import { PageHeader } from "@/components/app/page-header";
import { EmptyState } from "@/components/app/empty-state";
import { RiskPill, type RiskLevel } from "@/components/app/risk-pill";
import { BodyPainDiagram } from "@/components/BodyPainDiagram";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { analyzeReportImage, generateFinalReport } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { deriveLocalClinicalGuidance, inferBodyPainInsights, type BodyPainInsight } from "@/lib/bodyPain";
import { exportConsultationPdf } from "@/lib/pdfReport";
import { getConsultationSocketCandidates } from "@/lib/realtime";
import { saveConsultation } from "@/lib/history";
import type { RealtimeConsultationEvent, ReportImageAnalysis } from "@/lib/types";
import { cn } from "@/lib/utils";

const DISEASE_TERMS = [
  "chest pain",
  "shortness of breath",
  "palpitations",
  "dizziness",
  "fatigue",
  "left arm pain",
  "back pain",
  "troponin",
  "st elevation"
];

const LANGUAGE_OPTIONS = [
  { label: "English", code: "en-US" },
  { label: "Urdu", code: "ur-PK" },
  { label: "Hindi", code: "hi-IN" },
  { label: "Arabic", code: "ar-SA" },
  { label: "French", code: "fr-FR" },
  { label: "Spanish", code: "es-ES" },
  { label: "German", code: "de-DE" },
  { label: "Chinese (Mandarin)", code: "zh-CN" }
];

const inputClass =
  "h-9 w-full rounded-lg border border-line bg-inset px-3 text-sm text-fg shadow-[inset_0_1px_2px_rgba(0,0,0,0.35)] transition-colors placeholder:text-faint hover:border-line2 focus:border-accent/45";

function Field({
  label,
  className,
  children
}: {
  label: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <label className={cn("block", className)}>
      <span className="label mb-1.5 block">{label}</span>
      {children}
    </label>
  );
}

export function WorkflowSessionPage() {
  const [speaker, setSpeaker] = useState<"doctor" | "patient">("patient");
  const [selectedLanguage, setSelectedLanguage] = useState("en-US");
  const [isListening, setIsListening] = useState(false);
  const [socketConnected, setSocketConnected] = useState(false);
  const [error, setError] = useState("");
  const [draftText, setDraftText] = useState("");
  const [reportText, setReportText] = useState("");
  const [lastHeardText, setLastHeardText] = useState("");
  const [doctorQuestions, setDoctorQuestions] = useState<string[]>([]);
  const [recommendedTests, setRecommendedTests] = useState<string[]>([]);
  const [diagnosticImpression, setDiagnosticImpression] = useState<string[]>([]);
  const [nextSteps, setNextSteps] = useState<string[]>([]);
  const [bodyInsights, setBodyInsights] = useState<BodyPainInsight[]>([]);
  const [symptomNotes, setSymptomNotes] = useState<string[]>([]);
  const [riskLevel, setRiskLevel] = useState<RiskLevel>("Low");
  const [generatingPdf, setGeneratingPdf] = useState(false);
  const [awaitingCopilot, setAwaitingCopilot] = useState(false);
  const [reportImageFile, setReportImageFile] = useState<File | null>(null);
  const [reportImageAnalysis, setReportImageAnalysis] = useState<ReportImageAnalysis | null>(null);
  const [analyzingImage, setAnalyzingImage] = useState(false);
  const [patientName, setPatientName] = useState("");
  const [patientAge, setPatientAge] = useState("");
  const [patientGender, setPatientGender] = useState("");
  const [visitDate, setVisitDate] = useState(new Date().toISOString().slice(0, 10));
  const [doctorName, setDoctorName] = useState("");
  const [chiefComplaint, setChiefComplaint] = useState("");

  const wsRef = useRef<WebSocket | null>(null);
  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const keepListeningRef = useRef(false);
  const restartTimerRef = useRef<number | null>(null);
  const speechSupported = useMemo(() => Boolean(window.SpeechRecognition || window.webkitSpeechRecognition), []);

  useEffect(() => {
    let cancelled = false;
    let activeSocket: WebSocket | null = null;

    const onMessage = (event: MessageEvent) => {
      let payload: RealtimeConsultationEvent;
      try {
        payload = JSON.parse(event.data) as RealtimeConsultationEvent;
      } catch {
        return;
      }
      setAwaitingCopilot(false);
      if (payload.error) {
        setError(payload.error);
        return;
      }
      setDoctorQuestions(payload.ai_copilot?.doctor_questions ?? payload.doctor_next_questions ?? []);
      setRecommendedTests(payload.ai_copilot?.recommended_tests ?? []);
      setDiagnosticImpression(payload.ai_copilot?.diagnostic_impression ?? []);
      setNextSteps(payload.ai_copilot?.next_steps ?? payload.patient_recommendations ?? []);
      setRiskLevel(payload.diagnosis?.risk_level ?? "Low");
      const insights = inferBodyPainInsights(payload.transcript ?? "", reportText);
      setBodyInsights(insights);
      collectSymptomNotes(payload.transcript ?? "", payload.symptoms ?? []);
    };

    const tryConnect = (candidates: string[]) => {
      if (cancelled || candidates.length === 0) {
        setSocketConnected(false);
        setError("Realtime engine offline — local guidance stays active. Start the PulseIQ backend on port 8000.");
        return;
      }

      const token = getToken();
      const nextUrl = candidates[0] + (token ? `?token=${encodeURIComponent(token)}` : "");
      const ws = new WebSocket(nextUrl);
      let opened = false;

      ws.onopen = () => {
        if (cancelled) {
          ws.close();
          return;
        }
        opened = true;
        activeSocket = ws;
        wsRef.current = ws;
        setSocketConnected(true);
        setError("");
        ws.onmessage = onMessage;
      };

      ws.onerror = () => {
        if (opened || cancelled) return;
        ws.close();
        tryConnect(candidates.slice(1));
      };

      ws.onclose = () => {
        if (cancelled) return;
        if (!opened) return;
        setSocketConnected(false);
      };
    };

    tryConnect(getConsultationSocketCandidates());

    return () => {
      cancelled = true;
      if (activeSocket) activeSocket.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function collectSymptomNotes(transcript: string, extracted: string[]) {
    const found = new Set<string>(extracted.map((s) => s.toLowerCase()));
    const low = transcript.toLowerCase();
    DISEASE_TERMS.forEach((term) => {
      if (low.includes(term)) found.add(term);
    });
    if (found.size === 0) return;
    setSymptomNotes((prev) => Array.from(new Set([...prev, ...Array.from(found)])));
  }

  function sendEntry(text: string) {
    const trimmed = text.trim();
    if (!trimmed) return;
    setLastHeardText(trimmed);
    const localInsights = inferBodyPainInsights(trimmed, reportText);
    setBodyInsights(localInsights);
    collectSymptomNotes(trimmed, []);
    const local = deriveLocalClinicalGuidance(localInsights);
    setDoctorQuestions(local.doctorQuestions);
    setRecommendedTests(local.recommendedTests);
    setNextSteps(local.nextSteps);
    setDiagnosticImpression(["Local guidance active while the copilot refines output…"]);
    if (!socketConnected || !wsRef.current) {
      setError("Realtime engine offline — local guidance is active.");
      return;
    }
    setAwaitingCopilot(true);
    wsRef.current.send(
      JSON.stringify({ speaker, text: trimmed, report_text: reportText, language_code: selectedLanguage })
    );
  }

  function startListening() {
    if (!speechSupported) {
      setError("Speech recognition unsupported. Use Edge or Chrome.");
      return;
    }
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) return;
    const recognition = new SR();
    recognition.continuous = true;
    recognition.interimResults = false;
    recognition.lang = selectedLanguage;
    recognition.onresult = (event) => {
      const latest = event.results[event.results.length - 1];
      const transcript = latest[0].transcript.trim();
      if (transcript) sendEntry(transcript);
    };
    recognition.onerror = (event) => {
      const errorName = (event as Event & { error?: string }).error;
      if (errorName === "not-allowed" || errorName === "service-not-allowed") {
        setError("Microphone permission denied. Allow microphone access.");
        setIsListening(false);
        keepListeningRef.current = false;
        return;
      }
      if (keepListeningRef.current) return;
      setError("Microphone error. Check permissions.");
      setIsListening(false);
    };
    recognition.onend = () => {
      if (keepListeningRef.current) {
        if (restartTimerRef.current) window.clearTimeout(restartTimerRef.current);
        restartTimerRef.current = window.setTimeout(() => {
          try {
            recognition.start();
          } catch {
            setIsListening(false);
          }
        }, 250);
        return;
      }
      setIsListening(false);
    };
    recognition.start();
    recognitionRef.current = recognition;
    setIsListening(true);
    keepListeningRef.current = true;
  }

  function stopListening() {
    if (restartTimerRef.current) {
      window.clearTimeout(restartTimerRef.current);
      restartTimerRef.current = null;
    }
    recognitionRef.current?.stop();
    setIsListening(false);
    keepListeningRef.current = false;
  }

  function onManualSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    sendEntry(draftText);
    setDraftText("");
  }

  async function fileToBase64(file: File): Promise<string> {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const result = typeof reader.result === "string" ? reader.result : "";
        const base64 = result.split(",")[1] ?? "";
        resolve(base64);
      };
      reader.onerror = () => reject(new Error("Failed to read file."));
      reader.readAsDataURL(file);
    });
  }

  async function onAnalyzeReportImage() {
    if (!reportImageFile) {
      setError("Select a report image first.");
      return;
    }
    setAnalyzingImage(true);
    try {
      const base64 = await fileToBase64(reportImageFile);
      const analysis = await analyzeReportImage(base64, reportImageFile.type || "image/png");
      setReportImageAnalysis(analysis);
      setRecommendedTests((prev) => Array.from(new Set([...prev, ...(analysis.recommended_tests || [])])));
      setDiagnosticImpression((prev) => Array.from(new Set([...prev, ...(analysis.possible_diagnosis || [])])));
      setNextSteps((prev) => Array.from(new Set([...prev, ...(analysis.next_steps || [])])));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Image analysis failed.");
    } finally {
      setAnalyzingImage(false);
    }
  }

  async function onGenerateReport() {
    if (!patientName.trim() || !patientAge.trim() || !doctorName.trim()) {
      setError("Fill in patient name, age and doctor name before generating the final report.");
      return;
    }
    setGeneratingPdf(true);
    try {
      const report = await generateFinalReport({
        patient_name: patientName,
        patient_age: patientAge,
        patient_gender: patientGender,
        visit_date: visitDate,
        doctor_name: doctorName,
        chief_complaint: chiefComplaint,
        report_text: reportText,
        last_heard_text: lastHeardText,
        risk_level: riskLevel,
        symptom_notes: symptomNotes,
        doctor_questions: doctorQuestions,
        recommended_tests: recommendedTests,
        diagnostic_impression: diagnosticImpression,
        next_steps: nextSteps
      });
      exportConsultationPdf(report, {
        patientName,
        patientAge,
        patientGender,
        visitDate,
        doctorName,
        chiefComplaint
      });

      // Persist the visit record to the signed-in clinician's account.
      await saveConsultation({
        patient_name: patientName,
        patient_age: patientAge,
        patient_gender: patientGender,
        visit_date: visitDate,
        doctor_name: doctorName,
        chief_complaint: chiefComplaint,
        risk_level: riskLevel,
        symptom_notes: symptomNotes,
        report,
        created_at: new Date().toISOString()
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate report.");
    } finally {
      setGeneratingPdf(false);
    }
  }

  const guidanceSections = [
    { title: "Follow-up questions", icon: Stethoscope, items: doctorQuestions, empty: "Start voice or submit a transcript." },
    { title: "Recommended tests", icon: ListChecks, items: recommendedTests, empty: "No tests suggested yet." },
    { title: "Diagnostic direction", icon: HeartPulse, items: diagnosticImpression, empty: "No direction recorded yet." },
    { title: "Next steps", icon: CheckCircle2, items: nextSteps, empty: "No next steps yet." }
  ];

  return (
    <div>
      <PageHeader
        eyebrow="Records"
        icon={Stethoscope}
        title="Consultation session"
        description="Capture the encounter, let the copilot structure it, then export a finished visit record."
        actions={
          <>
            <Badge variant={socketConnected ? "ok" : "destructive"} dot>
              {socketConnected ? "Realtime connected" : "Offline"}
            </Badge>
            <RiskPill level={riskLevel} />
          </>
        }
      />

      <div className="space-y-5">
        {/* Visit details */}
        <Card>
          <CardHeader>
            <CardTitle>Visit details</CardTitle>
            <CardDescription>Used to head the exported report.</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <Field label="Patient name">
                <input
                  value={patientName}
                  onChange={(e) => setPatientName(e.target.value)}
                  placeholder="Full name or initials"
                  className={inputClass}
                />
              </Field>
              <Field label="Age">
                <input
                  value={patientAge}
                  onChange={(e) => setPatientAge(e.target.value)}
                  placeholder="Years"
                  className={inputClass}
                />
              </Field>
              <Field label="Gender">
                <input
                  value={patientGender}
                  onChange={(e) => setPatientGender(e.target.value)}
                  placeholder="Optional"
                  className={inputClass}
                />
              </Field>
              <Field label="Visit date">
                <input
                  type="date"
                  value={visitDate}
                  onChange={(e) => setVisitDate(e.target.value)}
                  className={inputClass}
                />
              </Field>
              <Field label="Clinician">
                <input
                  value={doctorName}
                  onChange={(e) => setDoctorName(e.target.value)}
                  placeholder="Name of reviewing clinician"
                  className={inputClass}
                />
              </Field>
              <Field label="Chief complaint">
                <input
                  value={chiefComplaint}
                  onChange={(e) => setChiefComplaint(e.target.value)}
                  placeholder="Presenting problem in a few words"
                  className={inputClass}
                />
              </Field>
            </div>
          </CardContent>
        </Card>

        <div className="grid gap-5 xl:grid-cols-2">
          {/* Capture + guidance */}
          <div className="space-y-5">
            <Card>
              <CardHeader className="border-b border-line pb-4">
                <CardTitle>Capture</CardTitle>
                <CardDescription className="mt-1">
                  Dictate the encounter or enter lines by hand. Every line refreshes the guidance.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4 pt-5">
                <div className="grid gap-3 sm:grid-cols-2">
                  <div>
                    <span className="label mb-1.5 block">Speaker</span>
                    <div className="flex rounded-lg border border-line bg-inset p-1">
                      {(["patient", "doctor"] as const).map((role) => (
                        <button
                          key={role}
                          type="button"
                          onClick={() => setSpeaker(role)}
                          className={cn(
                            "flex flex-1 items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium capitalize transition-colors duration-150",
                            speaker === role ? "bg-elev text-fg" : "text-muted hover:text-fg"
                          )}
                        >
                          {role === "patient" ? (
                            <User className="h-3.5 w-3.5" strokeWidth={1.75} />
                          ) : (
                            <Stethoscope className="h-3.5 w-3.5" strokeWidth={1.75} />
                          )}
                          {role}
                        </button>
                      ))}
                    </div>
                  </div>
                  <div>
                    <label className="label mb-1.5 block" htmlFor="workflow-language">
                      Input language
                    </label>
                    <select
                      id="workflow-language"
                      value={selectedLanguage}
                      onChange={(e) => setSelectedLanguage(e.target.value)}
                      className={inputClass}
                    >
                      {LANGUAGE_OPTIONS.map((opt) => (
                        <option key={opt.code} value={opt.code}>
                          {opt.label}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                <Button
                  onClick={isListening ? stopListening : startListening}
                  variant={isListening ? "destructive" : "default"}
                  size="lg"
                  className={cn("w-full", isListening && "animate-ring-pulse")}
                >
                  {isListening ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
                  {isListening ? "Stop voice capture" : "Start voice capture"}
                </Button>

                {isListening ? (
                  <p className="flex items-center gap-2 text-2xs text-danger-strong">
                    <Radio className="h-3 w-3 animate-pulse-soft" strokeWidth={2} />
                    Capturing audio
                  </p>
                ) : null}

                {lastHeardText ? (
                  <div className="rounded-lg border border-line bg-inset px-3 py-2.5">
                    <p className="label">Last captured</p>
                    <p className="mt-1 line-clamp-3 text-xs leading-relaxed text-muted">{lastHeardText}</p>
                  </div>
                ) : null}

                <form className="space-y-2 border-t border-line pt-4" onSubmit={onManualSubmit}>
                  <span className="label block">Manual transcript</span>
                  <Textarea
                    value={draftText}
                    onChange={(e) => setDraftText(e.target.value)}
                    rows={2}
                    placeholder="Type a line of the encounter…"
                    className="min-h-[68px]"
                  />
                  <Button type="submit" variant="outline" className="w-full">
                    <Send className="h-4 w-4" strokeWidth={1.9} />
                    Submit transcript
                  </Button>
                </form>

                <div className="space-y-2 border-t border-line pt-4">
                  <label className="label flex items-center gap-1.5">
                    <FileText className="h-3 w-3" strokeWidth={1.75} />
                    Test / report context
                  </label>
                  <Textarea
                    value={reportText}
                    onChange={(e) => setReportText(e.target.value)}
                    rows={3}
                    placeholder="e.g. troponin elevated, anterior ST elevation"
                    className="min-h-[80px]"
                  />
                </div>

                {error ? (
                  <Alert variant="destructive">
                    <AlertCircle />
                    <AlertTitle>Session status</AlertTitle>
                    <AlertDescription>{error}</AlertDescription>
                  </Alert>
                ) : null}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="border-b border-line pb-4">
                <div className="flex items-center justify-between gap-3">
                  <CardTitle>Copilot output</CardTitle>
                  {awaitingCopilot ? (
                    <span className="flex items-center gap-1.5 text-2xs text-faint">
                      <LoaderCircle className="h-3 w-3 animate-spin" />
                      Reasoning…
                    </span>
                  ) : null}
                </div>
              </CardHeader>
              <CardContent className="divide-y divide-line pt-0">
                {guidanceSections.map((section) => (
                  <section key={section.title} className="py-4 first:pt-5 last:pb-5">
                    <h3 className="flex items-center gap-2 text-xs font-semibold text-fg">
                      <section.icon className="h-3.5 w-3.5 text-accent" strokeWidth={1.75} />
                      {section.title}
                    </h3>
                    {section.items.length === 0 ? (
                      <p className="mt-2 text-2xs text-faint">{section.empty}</p>
                    ) : (
                      <ul className="mt-2.5 space-y-1.5">
                        {section.items.map((item) => (
                          <li key={item} className="flex gap-2 text-xs leading-relaxed text-muted">
                            <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-line2" />
                            {item}
                          </li>
                        ))}
                      </ul>
                    )}
                  </section>
                ))}
              </CardContent>
            </Card>
          </div>

          {/* Mapping + export */}
          <div className="space-y-5">
            <Card>
              <CardHeader className="pb-3">
                <CardTitle>Body pain map</CardTitle>
              </CardHeader>
              <CardContent>
                <BodyPainDiagram insights={bodyInsights} />
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm">Detected regions</CardTitle>
              </CardHeader>
              <CardContent>
                {bodyInsights.length === 0 ? (
                  <EmptyState
                    icon={HeartPulse}
                    title="No regions detected"
                    description="Region highlights appear once pain locations are described in the transcript."
                    className="py-7"
                  />
                ) : (
                  <div className="space-y-2">
                    {bodyInsights.map((item) => (
                      <div key={item.region} className="rounded-lg border border-line bg-inset p-3">
                        <div className="flex items-center justify-between gap-2">
                          <p className="text-xs font-medium text-fg">{item.label}</p>
                          <Badge
                            variant={
                              item.urgency === "high" ? "destructive" : item.urgency === "moderate" ? "warn" : "ok"
                            }
                            dot
                          >
                            {item.urgency}
                          </Badge>
                        </div>
                        {item.possibleFactors.slice(0, 2).map((factor) => (
                          <p key={factor} className="mt-1.5 flex gap-2 text-2xs leading-relaxed text-faint">
                            <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-line2" />
                            {factor}
                          </p>
                        ))}
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-2 text-sm">
                  <ImageUp className="h-3.5 w-3.5 text-accent" strokeWidth={1.75} />
                  Report image
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <input
                  type="file"
                  accept="image/png,image/jpeg,image/jpg,image/webp"
                  onChange={(e) => setReportImageFile(e.target.files?.[0] ?? null)}
                  className="block w-full cursor-pointer rounded-lg border border-line bg-inset px-3 py-2 text-xs text-muted file:mr-3 file:rounded-md file:border-0 file:bg-elev file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-fg hover:border-line2"
                />
                <Button onClick={onAnalyzeReportImage} disabled={analyzingImage} variant="outline" className="w-full">
                  {analyzingImage ? (
                    <LoaderCircle className="h-4 w-4 animate-spin" />
                  ) : (
                    <ScanLine className="h-4 w-4" strokeWidth={1.9} />
                  )}
                  {analyzingImage ? "Analyzing…" : "Analyze upload"}
                </Button>

                {reportImageAnalysis ? (
                  <div className="animate-fade-up space-y-3 rounded-lg border border-line bg-inset p-3.5">
                    <div>
                      <p className="label">Summary</p>
                      <p className="mt-1.5 text-xs leading-relaxed text-muted">{reportImageAnalysis.summary}</p>
                    </div>
                    {reportImageAnalysis.key_findings.length > 0 ? (
                      <div>
                        <p className="label">Key findings</p>
                        <ul className="mt-1.5 space-y-1">
                          {reportImageAnalysis.key_findings.map((item) => (
                            <li key={item} className="flex gap-2 text-xs leading-relaxed text-muted">
                              <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-line2" />
                              {item}
                            </li>
                          ))}
                        </ul>
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm">Captured symptom terms</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {symptomNotes.length === 0 ? (
                  <p className="text-2xs text-faint">No disease-specific terms captured yet.</p>
                ) : (
                  <div className="flex flex-wrap gap-1.5">
                    {symptomNotes.map((note) => (
                      <Badge key={note} variant="secondary">
                        {note}
                      </Badge>
                    ))}
                  </div>
                )}

                <div className="border-t border-line pt-4">
                  <Button onClick={onGenerateReport} disabled={generatingPdf} size="lg" className="w-full">
                    {generatingPdf ? (
                      <LoaderCircle className="h-4 w-4 animate-spin" />
                    ) : (
                      <Download className="h-4 w-4" strokeWidth={1.9} />
                    )}
                    {generatingPdf ? "Generating report…" : "End encounter & export PDF"}
                  </Button>
                  <p className="mt-2.5 text-2xs leading-relaxed text-faint">
                    Requires patient name, age and clinician. The report is assembled on-device and saved
                    directly from the browser.
                  </p>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
}
