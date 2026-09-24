import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  FileText,
  HeartPulse,
  ListChecks,
  Mic,
  MicOff,
  Radio,
  Send,
  Stethoscope,
  Trash2,
  User
} from "lucide-react";
import { PageHeader } from "@/components/app/page-header";
import { EmptyState } from "@/components/app/empty-state";
import { RiskPill, type RiskLevel } from "@/components/app/risk-pill";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { BodyPainDiagram } from "@/components/BodyPainDiagram";
import { getConsultationSocketUrl } from "@/lib/realtime";
import { getToken } from "@/lib/auth";
import { deriveLocalClinicalGuidance, inferBodyPainInsights, type BodyPainInsight } from "@/lib/bodyPain";
import type { RealtimeConsultationEvent } from "@/lib/types";
import { cn } from "@/lib/utils";

type TranscriptLine = {
  id: string;
  speaker: "doctor" | "patient";
  text: string;
  timestamp: string;
};

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

function SpeakerToggle({
  value,
  onChange
}: {
  value: "doctor" | "patient";
  onChange: (value: "doctor" | "patient") => void;
}) {
  return (
    <div className="flex rounded-lg border border-line bg-inset p-1">
      {(["patient", "doctor"] as const).map((role) => (
        <button
          key={role}
          type="button"
          onClick={() => onChange(role)}
          className={cn(
            "flex flex-1 items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium capitalize transition-colors duration-150",
            value === role ? "bg-elev text-fg" : "text-muted hover:text-fg"
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
  );
}

export function LiveConsultationPage() {
  const [speaker, setSpeaker] = useState<"doctor" | "patient">("patient");
  const [selectedLanguage, setSelectedLanguage] = useState("en-US");
  const [isListening, setIsListening] = useState(false);
  const [socketConnected, setSocketConnected] = useState(false);
  const [error, setError] = useState("");
  const [lastHeardText, setLastHeardText] = useState("");
  const [draftText, setDraftText] = useState("");
  const [reportText, setReportText] = useState("");
  const [doctorQuestions, setDoctorQuestions] = useState<string[]>([]);
  const [patientRecommendations, setPatientRecommendations] = useState<string[]>([]);
  const [recommendedTests, setRecommendedTests] = useState<string[]>([]);
  const [diagnosticImpression, setDiagnosticImpression] = useState<string[]>([]);
  const [nextSteps, setNextSteps] = useState<string[]>([]);
  const [safetyNote, setSafetyNote] = useState("");
  const [bodyInsights, setBodyInsights] = useState<BodyPainInsight[]>([]);
  const [transcriptLines, setTranscriptLines] = useState<TranscriptLine[]>([]);
  const [currentRisk, setCurrentRisk] = useState<RiskLevel>("Low");
  const [currentSymptoms, setCurrentSymptoms] = useState<string[]>([]);
  const [cardiacRegions, setCardiacRegions] = useState<
    {
      region: string;
      likelihood: "low" | "moderate" | "high";
      clinical_note: string;
      marker: { x: number; y: number; z: number };
    }[]
  >([]);

  const wsRef = useRef<WebSocket | null>(null);
  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const keepListeningRef = useRef(false);
  const restartTimerRef = useRef<number | null>(null);
  const transcriptEndRef = useRef<HTMLDivElement | null>(null);

  const speechSupported = useMemo(
    () => Boolean(window.SpeechRecognition || window.webkitSpeechRecognition),
    []
  );

  useEffect(() => {
    const token = getToken();
    const ws = new WebSocket(
      getConsultationSocketUrl() + (token ? `?token=${encodeURIComponent(token)}` : "")
    );

    ws.onopen = () => {
      setSocketConnected(true);
      setError(""); // a later reconnect must clear an earlier failure banner
    };
    ws.onclose = () => setSocketConnected(false);
    ws.onerror = () =>
      setError("Realtime connection failed. Start the PulseIQ backend on localhost:8000 and refresh.");
    ws.onmessage = (event) => {
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

      const entry: TranscriptLine = {
        id: crypto.randomUUID(),
        speaker: payload.speaker,
        text: payload.transcript,
        timestamp: new Date().toLocaleTimeString()
      };
      setTranscriptLines((prev) => [...prev, entry].slice(-60));
      setDoctorQuestions(payload.ai_copilot?.doctor_questions ?? payload.doctor_next_questions ?? []);
      setPatientRecommendations(payload.patient_recommendations ?? []);
      setRecommendedTests(payload.ai_copilot?.recommended_tests ?? []);
      setDiagnosticImpression(payload.ai_copilot?.diagnostic_impression ?? []);
      setNextSteps(payload.ai_copilot?.next_steps ?? payload.patient_recommendations ?? []);
      setSafetyNote(payload.ai_copilot?.safety_note ?? "");
      setCurrentRisk(payload.diagnosis?.risk_level ?? "Low");
      setCurrentSymptoms(payload.symptoms ?? []);
      setCardiacRegions(payload.cardiac_regions ?? []);
      setBodyInsights(inferBodyPainInsights(payload.transcript ?? "", reportText));
    };
    wsRef.current = ws;

    return () => ws.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [transcriptLines]);

  function pushLocalLine(text: string) {
    const entry: TranscriptLine = {
      id: crypto.randomUUID(),
      speaker,
      text,
      timestamp: new Date().toLocaleTimeString()
    };
    setTranscriptLines((prev) => [...prev, entry].slice(-60));
  }

  function sendTranscriptEntry(text: string) {
    const trimmed = text.trim();
    if (!trimmed) return;
    const localInsights = inferBodyPainInsights(trimmed, reportText);
    setBodyInsights(localInsights);
    setLastHeardText(trimmed);

    if (!socketConnected || !wsRef.current) {
      setError("Realtime engine offline — on-device triage guidance is active. Start the backend for the full copilot.");
      const localPlan = deriveLocalClinicalGuidance(localInsights);
      setDoctorQuestions(localPlan.doctorQuestions);
      setRecommendedTests(localPlan.recommendedTests);
      setNextSteps(localPlan.nextSteps);
      setDiagnosticImpression(["Local mode: backend disconnected, showing on-device triage hints only."]);
      pushLocalLine(trimmed);
      return;
    }
    setError("");
    wsRef.current.send(
      JSON.stringify({ speaker, text: trimmed, report_text: reportText, language_code: selectedLanguage })
    );
  }

  function startListening() {
    if (!speechSupported) {
      setError("Speech recognition is not supported in this browser. Use Chrome or Edge.");
      return;
    }
    if (!window.isSecureContext) {
      setError("Microphone access requires localhost or an HTTPS secure context.");
      return;
    }
    setError("");
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) return;

    const recognition = new SR();
    recognition.continuous = true;
    recognition.interimResults = false;
    recognition.lang = selectedLanguage;

    recognition.onresult = (event) => {
      const latest = event.results[event.results.length - 1];
      const transcript = latest[0].transcript.trim();
      if (!transcript) return;
      setLastHeardText(transcript);
      sendTranscriptEntry(transcript);
    };

    recognition.onerror = (event) => {
      const errorName = (event as Event & { error?: string }).error;
      if (errorName === "not-allowed" || errorName === "service-not-allowed") {
        setError("Microphone permission denied. Allow mic access in your browser site settings.");
        setIsListening(false);
        keepListeningRef.current = false;
        return;
      }
      if (!keepListeningRef.current) {
        setError("Microphone error detected. Check permissions and the input device.");
        setIsListening(false);
        keepListeningRef.current = false;
      }
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

  function submitManualEntry(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    sendTranscriptEntry(draftText);
    setDraftText("");
  }

  const guidancePanels: { title: string; icon: typeof Mic; items: string[] }[] = [
    { title: "Suggested questions", icon: Stethoscope, items: doctorQuestions },
    { title: "Recommended tests", icon: ListChecks, items: recommendedTests },
    { title: "Diagnostic direction", icon: HeartPulse, items: diagnosticImpression },
    { title: "Next steps", icon: CheckCircle2, items: nextSteps }
  ];

  return (
    <div>
      <PageHeader
        eyebrow="Workspace"
        icon={Mic}
        title="Live copilot"
        description="Transcribe an encounter as it happens. Every pass updates the risk band, the guidance panels and the body map without interrupting the conversation."
        actions={
          <>
            <Badge variant={socketConnected ? "ok" : "destructive"} dot>
              {socketConnected ? "Realtime connected" : "Offline"}
            </Badge>
            <RiskPill level={currentRisk} />
          </>
        }
      />

      <div className="grid gap-5 xl:grid-cols-[310px_minmax(0,1fr)_286px]">
        {/* Session rail */}
        <div className="space-y-5">
          <Card>
            <CardHeader>
              <CardTitle>Session</CardTitle>
              <CardDescription>Set the speaker, language and capture mode.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <SpeakerToggle value={speaker} onChange={setSpeaker} />

              <div className="space-y-1.5">
                <label className="label block">Input language</label>
                <select
                  value={selectedLanguage}
                  onChange={(e) => setSelectedLanguage(e.target.value)}
                  className="h-9 w-full rounded-lg border border-line bg-inset px-3 text-sm text-fg transition-colors hover:border-line2 focus:border-accent/45"
                >
                  {LANGUAGE_OPTIONS.map((opt) => (
                    <option key={opt.code} value={opt.code}>
                      {opt.label}
                    </option>
                  ))}
                </select>
                <p className="text-2xs text-faint">Output is normalised to English.</p>
              </div>

              <Button
                onClick={isListening ? stopListening : startListening}
                variant={isListening ? "destructive" : "default"}
                size="lg"
                className={cn("w-full", isListening && "animate-ring-pulse")}
              >
                {isListening ? (
                  <MicOff className="h-4 w-4" strokeWidth={1.9} />
                ) : (
                  <Mic className="h-4 w-4" strokeWidth={1.9} />
                )}
                {isListening ? "Stop listening" : "Start listening"}
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

              <form className="space-y-2 border-t border-line pt-4" onSubmit={submitManualEntry}>
                <label className="label block">Manual entry</label>
                <Textarea
                  value={draftText}
                  onChange={(e) => setDraftText(e.target.value)}
                  rows={2}
                  placeholder="Type a transcript line instead of speaking…"
                  className="min-h-[68px]"
                />
                <Button type="submit" variant="outline" className="w-full">
                  <Send className="h-4 w-4" strokeWidth={1.9} />
                  Submit line
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
                  placeholder="e.g. Troponin elevated, anterior ST elevation, reduced EF on echo"
                  className="min-h-[80px]"
                />
              </div>

              {error ? (
                <Alert variant="destructive">
                  <AlertCircle />
                  <AlertTitle>Stream status</AlertTitle>
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              ) : null}
            </CardContent>
          </Card>
        </div>

        {/* Transcript + guidance */}
        <div className="space-y-5">
          <Card>
            <CardHeader className="flex-row items-center justify-between gap-3 space-y-0 border-b border-line pb-4">
              <div>
                <CardTitle>Transcript</CardTitle>
                <CardDescription className="mt-1">
                  <span className="num">{transcriptLines.length}</span> lines captured
                </CardDescription>
              </div>
              <Button
                size="icon"
                variant="ghost"
                aria-label="Clear transcript"
                onClick={() => setTranscriptLines([])}
              >
                <Trash2 className="h-4 w-4" strokeWidth={1.75} />
              </Button>
            </CardHeader>
            <CardContent className="pt-4">
              <div className="h-[340px] space-y-3 overflow-y-auto pr-1">
                {transcriptLines.length === 0 ? (
                  <EmptyState
                    icon={Mic}
                    title="Waiting for the first line"
                    description="Speak into the microphone or type an entry. Lines appear here as they are captured."
                    className="h-full"
                  />
                ) : (
                  transcriptLines.map((line) => (
                    <div
                      key={line.id}
                      className={cn(
                        "max-w-[86%] animate-slide-in rounded-xl border px-3.5 py-2.5",
                        line.speaker === "patient"
                          ? "ml-auto border-accent/20 bg-accent/[0.07]"
                          : "mr-auto border-line bg-elev/70"
                      )}
                    >
                      <div className="mb-1 flex items-center gap-2">
                        <span
                          className={cn(
                            "text-[10px] font-semibold uppercase tracking-[0.12em]",
                            line.speaker === "patient" ? "text-accent" : "text-faint"
                          )}
                        >
                          {line.speaker}
                        </span>
                        <span className="num text-[10px] text-faint">{line.timestamp}</span>
                      </div>
                      <p className="text-sm leading-relaxed text-muted">{line.text}</p>
                    </div>
                  ))
                )}
                <div ref={transcriptEndRef} />
              </div>

              <div className="mt-4 flex flex-wrap gap-2 border-t border-line pt-4">
                {currentSymptoms.length === 0 ? (
                  <p className="text-2xs text-faint">Detected concepts will be listed here.</p>
                ) : (
                  currentSymptoms.map((symptom) => (
                    <Badge key={symptom} variant="secondary" dot>
                      {symptom}
                    </Badge>
                  ))
                )}
              </div>
            </CardContent>
          </Card>

          <div className="grid gap-4 sm:grid-cols-2">
            {guidancePanels.map((panel) => (
              <Card key={panel.title}>
                <CardHeader className="pb-3">
                  <CardTitle className="flex items-center gap-2 text-sm">
                    <panel.icon className="h-3.5 w-3.5 text-accent" strokeWidth={1.75} />
                    {panel.title}
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {panel.items.length === 0 ? (
                    <p className="text-2xs text-faint">Awaiting input…</p>
                  ) : (
                    <ul className="space-y-1.5">
                      {panel.items.map((item) => (
                        <li key={item} className="flex gap-2 text-xs leading-relaxed text-muted">
                          <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-line2" />
                          {item}
                        </li>
                      ))}
                    </ul>
                  )}
                  {panel.title === "Next steps" && safetyNote ? (
                    <p className="mt-3 border-t border-line pt-3 text-2xs italic leading-relaxed text-faint">
                      {safetyNote}
                    </p>
                  ) : null}
                </CardContent>
              </Card>
            ))}
          </div>

          {patientRecommendations.length > 0 ? (
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm">Patient guidance</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="space-y-1.5">
                  {patientRecommendations.map((recommendation) => (
                    <li key={recommendation} className="flex gap-2 text-xs leading-relaxed text-muted">
                      <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-accent" />
                      {recommendation}
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          ) : null}
        </div>

        {/* Body map */}
        <div className="space-y-5">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle>Body pain map</CardTitle>
              <CardDescription className="mt-1">
                Highlights are driven by described pain locations.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <BodyPainDiagram insights={bodyInsights} />
            </CardContent>
          </Card>

          {cardiacRegions.length > 0 ? (
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm">Cardiac hypotheses</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {cardiacRegions.map((entry) => (
                  <div key={entry.region} className="rounded-lg border border-line bg-inset p-3">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-xs font-medium text-fg">{entry.region}</p>
                      <Badge
                        variant={
                          entry.likelihood === "high"
                            ? "destructive"
                            : entry.likelihood === "moderate"
                              ? "warn"
                              : "ok"
                        }
                        dot
                      >
                        {entry.likelihood}
                      </Badge>
                    </div>
                    <p className="mt-1.5 text-2xs leading-relaxed text-muted">{entry.clinical_note}</p>
                  </div>
                ))}
              </CardContent>
            </Card>
          ) : null}
        </div>
      </div>
    </div>
  );
}
