import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { Download, ImageUp, Mic, MicOff, Send, Sparkles, Stethoscope, User } from "lucide-react";
import { BodyPainDiagram } from "@/components/BodyPainDiagram";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { analyzeReportImage, generateFinalReport } from "@/lib/api";
import { deriveLocalClinicalGuidance, inferBodyPainInsights, type BodyPainInsight } from "@/lib/bodyPain";
import { exportConsultationPdf } from "@/lib/pdfReport";
import { getConsultationSocketCandidates } from "@/lib/realtime";
import type { RealtimeConsultationEvent, ReportImageAnalysis } from "@/lib/types";

const DISEASE_TERMS = [
  "chest pain",
  "shortness of breath",
  "palpitations",
  "dizziness",
  "fatigue",
  "left arm pain",
  "back pain",
  "troponin",
  "st elevation",
];

const LANGUAGE_OPTIONS = [
  { label: "English", code: "en-US" },
  { label: "Urdu", code: "ur-PK" },
  { label: "Hindi", code: "hi-IN" },
  { label: "Arabic", code: "ar-SA" },
  { label: "French", code: "fr-FR" },
  { label: "Spanish", code: "es-ES" },
  { label: "German", code: "de-DE" },
  { label: "Chinese (Mandarin)", code: "zh-CN" },
];

const inputClass =
  "w-full rounded-md border border-slate-700 bg-slate-950/60 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-600";

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
  const [riskLevel, setRiskLevel] = useState<"Low" | "Medium" | "High">("Low");
  const [generatingPdf, setGeneratingPdf] = useState(false);
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

      const nextUrl = candidates[0];
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
    setAiStreamingTrue();
    wsRef.current.send(JSON.stringify({ speaker, text: trimmed, report_text: reportText, language_code: selectedLanguage }));
  }

  function setAiStreamingTrue() {
    // placeholder for streaming indicator state; kept simple for reliability
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
      setError("Please fill Patient Name, Age, and Doctor Name before generating the final report.");
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
        next_steps: nextSteps,
      });
      exportConsultationPdf(report, {
        patientName,
        patientAge,
        patientGender,
        visitDate,
        doctorName,
        chiefComplaint,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate report.");
    } finally {
      setGeneratingPdf(false);
    }
  }

  const riskVariant = riskLevel === "High" ? "destructive" : riskLevel === "Medium" ? "secondary" : "default";

  return (
    <div className="space-y-5">
      {/* Visit details */}
      <Card className="card-animate border-slate-800 bg-slate-900/50">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-white">
            <User className="h-5 w-5 text-teal-400" />
            Visit details
          </CardTitle>
          <CardDescription>Required for the final PDF report header.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-2.5 md:grid-cols-3 lg:grid-cols-6">
            <input value={patientName} onChange={(e) => setPatientName(e.target.value)} placeholder="Patient name" className={inputClass} />
            <input value={patientAge} onChange={(e) => setPatientAge(e.target.value)} placeholder="Age" className={inputClass} />
            <input value={patientGender} onChange={(e) => setPatientGender(e.target.value)} placeholder="Gender" className={inputClass} />
            <input type="date" value={visitDate} onChange={(e) => setVisitDate(e.target.value)} className={inputClass} />
            <input value={doctorName} onChange={(e) => setDoctorName(e.target.value)} placeholder="Doctor name" className={`${inputClass} md:col-span-2`} />
            <input value={chiefComplaint} onChange={(e) => setChiefComplaint(e.target.value)} placeholder="Chief complaint" className={`${inputClass} md:col-span-3 lg:col-span-6`} />
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-5 xl:grid-cols-2">
        {/* LEFT column */}
        <div className="space-y-5">
          <Card className="card-animate border-slate-800 bg-slate-900/50">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-white">
                <Sparkles className="h-5 w-5 text-teal-400" />
                Consultation controls
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex flex-wrap items-center gap-2">
                <div className="flex rounded-lg border border-slate-700 bg-slate-950/60 p-1">
                  {(["patient", "doctor"] as const).map((role) => (
                    <button
                      key={role}
                      onClick={() => setSpeaker(role)}
                      className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium capitalize transition-colors ${
                        speaker === role ? "bg-teal-500/20 text-teal-300" : "text-slate-400 hover:text-slate-200"
                      }`}
                    >
                      {role === "patient" ? <User className="h-3.5 w-3.5" /> : <Stethoscope className="h-3.5 w-3.5" />}
                      {role}
                    </button>
                  ))}
                </div>
                <Badge variant={socketConnected ? "default" : "destructive"} className={socketConnected ? "bg-teal-500/15 text-teal-300" : ""}>
                  {socketConnected ? "Realtime" : "Offline"}
                </Badge>
                <Badge variant={riskVariant}>Risk: {riskLevel}</Badge>
              </div>

              <div className="space-y-1">
                <p className="text-xs text-slate-500">Input language (output normalized to English)</p>
                <select value={selectedLanguage} onChange={(e) => setSelectedLanguage(e.target.value)} className={inputClass}>
                  {LANGUAGE_OPTIONS.map((opt) => (
                    <option key={opt.code} value={opt.code}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>

              <div className="flex gap-2">
                {!isListening ? (
                  <Button onClick={startListening} className="flex-1 bg-gradient-to-r from-teal-500 to-sky-500 text-slate-950 hover:from-teal-400 hover:to-sky-400">
                    <Mic className="mr-2 h-4 w-4" />
                    Start voice
                  </Button>
                ) : (
                  <Button onClick={stopListening} variant="destructive" className="flex-1">
                    <MicOff className="mr-2 h-4 w-4" />
                    Stop voice
                  </Button>
                )}
              </div>

              {lastHeardText ? <p className="text-xs text-slate-500">Last heard: “{lastHeardText}”</p> : null}

              <form className="space-y-2" onSubmit={onManualSubmit}>
                <Textarea
                  value={draftText}
                  onChange={(e) => setDraftText(e.target.value)}
                  rows={2}
                  placeholder="Manual transcript input…"
                  className="border-slate-700 bg-slate-950/60 text-slate-100 placeholder:text-slate-600"
                />
                <Button type="submit" variant="outline" className="w-full border-slate-700 bg-slate-950/40 hover:bg-slate-800">
                  <Send className="mr-2 h-4 w-4" />
                  Submit transcript
                </Button>
              </form>

              <div className="space-y-1 border-t border-slate-800 pt-3">
                <p className="text-xs text-slate-500">Test/report context</p>
                <Textarea
                  value={reportText}
                  onChange={(e) => setReportText(e.target.value)}
                  rows={3}
                  placeholder='e.g. "troponin elevated, anterior ST elevation"'
                  className="border-slate-700 bg-slate-950/60 text-slate-100 placeholder:text-slate-600"
                />
              </div>

              {error ? (
                <Alert variant="destructive">
                  <AlertTitle>Workflow status</AlertTitle>
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              ) : null}
            </CardContent>
          </Card>

          <Card className="card-animate border-slate-800 bg-slate-900/50">
            <CardHeader>
              <CardTitle className="text-white">AI questions & recommendations</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <div>
                <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-teal-400">Doctor questions</p>
                {doctorQuestions.length === 0 ? <p className="text-xs text-slate-500">Start voice or submit transcript.</p> : null}
                {doctorQuestions.map((q) => (
                  <p key={q} className="text-slate-300">• {q}</p>
                ))}
              </div>
              <div>
                <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-sky-400">Recommended tests</p>
                {recommendedTests.length === 0 ? <p className="text-xs text-slate-500">No tests suggested yet.</p> : null}
                {recommendedTests.map((t) => (
                  <p key={t} className="text-slate-300">• {t}</p>
                ))}
              </div>
              <div>
                <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-violet-400">Diagnosis direction</p>
                {diagnosticImpression.length === 0 ? <p className="text-xs text-slate-500">No diagnosis direction yet.</p> : null}
                {diagnosticImpression.map((d) => (
                  <p key={d} className="text-slate-300">• {d}</p>
                ))}
              </div>
              <div>
                <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-amber-400">Next steps</p>
                {nextSteps.length === 0 ? <p className="text-xs text-slate-500">No next steps yet.</p> : null}
                {nextSteps.map((s) => (
                  <p key={s} className="text-slate-300">• {s}</p>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>

        {/* RIGHT column */}
        <div className="space-y-5">
          <Card className="card-animate border-slate-800 bg-slate-900/50">
            <CardHeader>
              <CardTitle className="text-white">Body pain map</CardTitle>
            </CardHeader>
            <CardContent>
              <BodyPainDiagram insights={bodyInsights} />
            </CardContent>
          </Card>

          <Card className="card-animate border-slate-800 bg-slate-900/50">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm text-white">Detected pain regions</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              {bodyInsights.length === 0 ? <p className="text-xs text-slate-500">No regions detected from speech/transcript yet.</p> : null}
              {bodyInsights.map((item) => (
                <div key={item.region} className="rounded-lg border border-slate-800 bg-slate-950/60 p-2.5">
                  <div className="mb-1 flex items-center gap-2">
                    <span className="font-medium text-white">{item.label}</span>
                    <Badge variant={item.urgency === "high" ? "destructive" : item.urgency === "moderate" ? "secondary" : "default"}>
                      {item.urgency}
                    </Badge>
                  </div>
                  {item.possibleFactors.slice(0, 2).map((factor) => (
                    <p key={factor} className="text-xs text-slate-400">• {factor}</p>
                  ))}
                </div>
              ))}
            </CardContent>
          </Card>

          <Card className="card-animate border-slate-800 bg-slate-900/50">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-white">
                <ImageUp className="h-5 w-5 text-teal-400" />
                Report image analysis
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <input
                type="file"
                accept="image/png,image/jpeg,image/jpg,image/webp"
                onChange={(e) => setReportImageFile(e.target.files?.[0] ?? null)}
                className="block w-full cursor-pointer rounded-md border border-slate-700 bg-slate-950/60 px-3 py-2 text-sm text-slate-300 file:mr-3 file:rounded-md file:border-0 file:bg-teal-500/20 file:px-3 file:py-1.5 file:text-xs file:font-semibold file:text-teal-300"
              />
              <Button onClick={onAnalyzeReportImage} disabled={analyzingImage} variant="outline" className="border-slate-700 bg-slate-950/40 hover:bg-slate-800">
                {analyzingImage ? "Analyzing…" : "Analyze uploaded report"}
              </Button>
              {reportImageAnalysis ? (
                <div className="space-y-2 rounded-lg border border-slate-800 bg-slate-950/60 p-3">
                  <p className="font-medium text-white">Summary</p>
                  <p className="text-slate-300">{reportImageAnalysis.summary}</p>
                  {reportImageAnalysis.key_findings.length > 0 ? (
                    <>
                      <p className="font-medium text-white">Key findings</p>
                      {reportImageAnalysis.key_findings.map((item) => (
                        <p key={item} className="text-slate-300">• {item}</p>
                      ))}
                    </>
                  ) : null}
                </div>
              ) : null}
            </CardContent>
          </Card>

          <Card className="card-animate border-slate-800 bg-slate-900/50">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm text-white">Disease symptom notes</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <div className="flex flex-wrap gap-2">
                {symptomNotes.length === 0 ? (
                  <p className="text-xs text-slate-500">No disease-specific symptoms captured yet.</p>
                ) : (
                  symptomNotes.map((s) => (
                    <Badge key={s} variant="secondary" className="bg-teal-500/10 text-teal-300">
                      {s}
                    </Badge>
                  ))
                )}
              </div>
              <Button
                onClick={onGenerateReport}
                disabled={generatingPdf}
                size="lg"
                className="w-full bg-gradient-to-r from-teal-500 to-sky-500 text-slate-950 hover:from-teal-400 hover:to-sky-400"
              >
                <Download className="mr-2 h-4 w-4" />
                {generatingPdf ? "Generating PDF…" : "End consultation & download PDF"}
              </Button>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
