import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertCircle,
  Bot,
  FileText,
  ListChecks,
  Mic,
  MicOff,
  Send,
  Stethoscope,
  Trash2,
  User,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { BodyPainDiagram } from "@/components/BodyPainDiagram";
import { Textarea } from "@/components/ui/textarea";
import { getConsultationSocketUrl } from "@/lib/realtime";
import { deriveLocalClinicalGuidance, inferBodyPainInsights, type BodyPainInsight } from "@/lib/bodyPain";
import type { RealtimeConsultationEvent } from "@/lib/types";

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
  { label: "Chinese (Mandarin)", code: "zh-CN" },
];

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
  const [currentRisk, setCurrentRisk] = useState<"Low" | "Medium" | "High">("Low");
  const [currentSymptoms, setCurrentSymptoms] = useState<string[]>([]);
  const [cardiacRegions, setCardiacRegions] = useState<
    { region: string; likelihood: "low" | "moderate" | "high"; clinical_note: string; marker: { x: number; y: number; z: number } }[]
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
    const ws = new WebSocket(getConsultationSocketUrl());

    ws.onopen = () => setSocketConnected(true);
    ws.onclose = () => setSocketConnected(false);
    ws.onerror = () =>
      setError("Realtime connection failed. Start the PulseIQ backend on localhost:8000 and refresh this page.");
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
        timestamp: new Date().toLocaleTimeString(),
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
      timestamp: new Date().toLocaleTimeString(),
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
      setError("Realtime engine offline — on-device triage guidance is active. Start the backend for full AI copilot.");
      const localPlan = deriveLocalClinicalGuidance(localInsights);
      setDoctorQuestions(localPlan.doctorQuestions);
      setRecommendedTests(localPlan.recommendedTests);
      setNextSteps(localPlan.nextSteps);
      setDiagnosticImpression(["Local mode: backend disconnected, showing on-device triage hints only."]);
      pushLocalLine(trimmed);
      return;
    }
    setError("");
    wsRef.current.send(JSON.stringify({ speaker, text: trimmed, report_text: reportText, language_code: selectedLanguage }));
  }

  function startListening() {
    if (!speechSupported) {
      setError("Speech recognition is not supported in this browser. Use Chrome or Edge.");
      return;
    }
    if (!window.isSecureContext) {
      setError("Microphone access requires localhost or HTTPS secure context.");
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
        setError("Microphone permission denied. Allow mic access in browser site settings.");
        setIsListening(false);
        keepListeningRef.current = false;
        return;
      }
      // no-speech and transient network/aborted errors: keep the session alive
      if (!keepListeningRef.current) {
        setError("Microphone error detected. Please check permissions and input device.");
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

  const riskVariant = currentRisk === "High" ? "destructive" : currentRisk === "Medium" ? "secondary" : "default";

  const guidancePanels: { title: string; icon: typeof Bot; items: string[]; accent: string }[] = [
    { title: "Suggested questions", icon: Stethoscope, items: doctorQuestions, accent: "text-teal-400" },
    { title: "Recommended tests", icon: ListChecks, items: recommendedTests, accent: "text-sky-400" },
    { title: "Diagnostic direction", icon: Bot, items: diagnosticImpression, accent: "text-violet-400" },
    { title: "Next steps", icon: ListChecks, items: nextSteps, accent: "text-amber-400" },
  ];

  return (
    <div className="grid gap-5 xl:grid-cols-[380px_1fr_320px]">
      {/* LEFT: controls */}
      <div className="space-y-4">
        <Card className="card-animate border-slate-800 bg-slate-900/50">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-white">
              <Stethoscope className="h-5 w-5 text-teal-400" />
              Live copilot
            </CardTitle>
            <CardDescription>
              Speak or type; the copilot listens and surfaces guidance in real time.
            </CardDescription>
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
              <Badge variant={riskVariant}>Risk: {currentRisk}</Badge>
            </div>

            <div className="space-y-1">
              <p className="text-xs text-slate-500">Input language (output normalized to English)</p>
              <select
                value={selectedLanguage}
                onChange={(e) => setSelectedLanguage(e.target.value)}
                className="w-full rounded-md border border-slate-700 bg-slate-950/60 px-3 py-2 text-sm text-slate-200"
              >
                {LANGUAGE_OPTIONS.map((opt) => (
                  <option key={opt.code} value={opt.code}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>

            <Button
              onClick={isListening ? stopListening : startListening}
              className={`w-full ${
                isListening
                  ? "bg-rose-500/90 hover:bg-rose-500"
                  : "bg-gradient-to-r from-teal-500 to-sky-500 text-slate-950 hover:from-teal-400 hover:to-sky-400"
              }`}
              size="lg"
            >
              {isListening ? <MicOff className="mr-2 h-4 w-4" /> : <Mic className="mr-2 h-4 w-4" />}
              {isListening ? "Stop listening" : "Start listening"}
              {isListening ? <span className="pulse-dot ml-2 h-2 w-2 rounded-full bg-white" /> : null}
            </Button>

            {lastHeardText ? (
              <p className="text-xs text-slate-500">Last heard: “{lastHeardText}”</p>
            ) : null}

            <form className="space-y-2" onSubmit={submitManualEntry}>
              <Textarea
                value={draftText}
                onChange={(e) => setDraftText(e.target.value)}
                rows={2}
                placeholder="Type a transcript line instead of speaking…"
                className="border-slate-700 bg-slate-950/60 text-slate-100 placeholder:text-slate-600"
              />
              <Button type="submit" variant="outline" className="w-full border-slate-700 bg-slate-950/40 hover:bg-slate-800">
                <Send className="mr-2 h-4 w-4" />
                Send line
              </Button>
            </form>

            <div className="space-y-2 border-t border-slate-800 pt-3">
              <p className="flex items-center gap-2 text-xs font-medium text-slate-400">
                <FileText className="h-3.5 w-3.5" />
                Test/report context
              </p>
              <Textarea
                value={reportText}
                onChange={(e) => setReportText(e.target.value)}
                rows={3}
                placeholder={'e.g. "Troponin elevated, anterior ST elevation, echo reduced EF"'}
                className="border-slate-700 bg-slate-950/60 text-slate-100 placeholder:text-slate-600"
              />
            </div>

            {error ? (
              <Alert variant="destructive">
                <AlertCircle className="h-4 w-4" />
                <AlertTitle>Live stream</AlertTitle>
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            ) : null}
          </CardContent>
        </Card>
      </div>

      {/* CENTER: transcript + guidance */}
      <div className="space-y-4">
        <Card className="card-animate flex flex-col border-slate-800 bg-slate-900/50">
          <CardHeader className="flex-row items-center justify-between space-y-0 pb-3">
            <CardTitle className="text-base text-white">Consultation transcript</CardTitle>
            <Button
              size="sm"
              variant="ghost"
              className="h-8 text-slate-400 hover:bg-slate-800 hover:text-slate-200"
              onClick={() => setTranscriptLines([])}
            >
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          </CardHeader>
          <CardContent>
            <div className="h-[320px] space-y-3 overflow-y-auto rounded-xl border border-slate-800 bg-slate-950/60 p-4">
              {transcriptLines.length === 0 ? (
                <div className="flex h-full flex-col items-center justify-center gap-2 text-center">
                  <Mic className="h-8 w-8 text-slate-700" />
                  <p className="text-sm text-slate-500">Waiting for speech or typed input…</p>
                  <p className="text-xs text-slate-600">Lines appear here in real time as you speak.</p>
                </div>
              ) : (
                transcriptLines.map((line) => (
                  <div
                    key={line.id}
                    className={`max-w-[85%] rounded-2xl px-3.5 py-2.5 text-sm ${
                      line.speaker === "patient"
                        ? "ml-auto bg-teal-500/15 text-teal-50"
                        : "mr-auto border border-slate-700/60 bg-slate-800/70 text-slate-100"
                    }`}
                  >
                    <div className="mb-0.5 flex items-center gap-2 text-[10px] uppercase tracking-wide opacity-70">
                      <span>{line.speaker}</span>
                      <span>· {line.timestamp}</span>
                    </div>
                    {line.text}
                  </div>
                ))
              )}
              <div ref={transcriptEndRef} />
            </div>

            <div className="mt-3 flex flex-wrap gap-2">
              {currentSymptoms.length === 0 ? (
                <p className="text-xs text-slate-500">Detected symptoms will appear here.</p>
              ) : (
                currentSymptoms.map((symptom) => (
                  <Badge key={symptom} variant="secondary" className="bg-teal-500/10 text-teal-300">
                    {symptom}
                  </Badge>
                ))
              )}
            </div>
          </CardContent>
        </Card>

        <div className="grid gap-4 sm:grid-cols-2">
          {guidancePanels.map((panel) => (
            <Card key={panel.title} className="border-slate-800 bg-slate-900/50">
              <CardHeader className="pb-2">
                <CardTitle className={`flex items-center gap-2 text-sm ${panel.accent}`}>
                  <panel.icon className="h-4 w-4" />
                  {panel.title}
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-1.5">
                {panel.items.length === 0 ? (
                  <p className="text-xs text-slate-500">Awaiting input…</p>
                ) : (
                  panel.items.map((item) => (
                    <p key={item} className="text-sm leading-snug text-slate-300">
                      • {item}
                    </p>
                  ))
                )}
                {panel.title === "Next steps" && safetyNote ? (
                  <p className="pt-1 text-[11px] italic text-slate-500">{safetyNote}</p>
                ) : null}
              </CardContent>
            </Card>
          ))}
        </div>

        {patientRecommendations.length > 0 ? (
          <Card className="border-slate-800 bg-slate-900/50">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm text-teal-300">Patient recommendations</CardTitle>
            </CardHeader>
            <CardContent className="space-y-1.5">
              {patientRecommendations.map((recommendation) => (
                <p key={recommendation} className="text-sm text-slate-300">• {recommendation}</p>
              ))}
            </CardContent>
          </Card>
        ) : null}
      </div>

      {/* RIGHT: body map + advanced */}
      <div className="space-y-4">
        <Card className="card-animate border-slate-800 bg-slate-900/50">
          <CardHeader className="pb-2">
            <CardTitle className="text-base text-white">Body pain map</CardTitle>
            <CardDescription>Red highlights come from spoken pain descriptions.</CardDescription>
          </CardHeader>
          <CardContent>
            <BodyPainDiagram insights={bodyInsights} />
          </CardContent>
        </Card>

        {cardiacRegions.length > 0 ? (
          <Card className="border-slate-800 bg-slate-900/50">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm text-white">Cardiac region hypotheses</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {cardiacRegions.map((entry) => (
                <div key={entry.region} className="rounded-lg border border-slate-800 bg-slate-950/60 p-2.5">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-sm font-medium text-white">{entry.region}</p>
                    <Badge
                      variant={entry.likelihood === "high" ? "destructive" : "secondary"}
                      className="capitalize"
                    >
                      {entry.likelihood}
                    </Badge>
                  </div>
                  <p className="mt-1 text-xs leading-snug text-slate-400">{entry.clinical_note}</p>
                </div>
              ))}
            </CardContent>
          </Card>
        ) : null}
      </div>
    </div>
  );
}
