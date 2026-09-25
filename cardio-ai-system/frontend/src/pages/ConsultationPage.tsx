import { useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  BadgeCheck,
  CheckCircle2,
  HeartPulse,
  ImageUp,
  Info,
  ListChecks,
  LoaderCircle,
  MapPin,
  Mic,
  MicOff,
  Radio,
  Save,
  ScanLine,
  Send,
  Sparkles,
  Stethoscope,
  Trash2,
  User,
  Wand2
} from "lucide-react";
import { PageHeader } from "@/components/app/page-header";
import { EmptyState } from "@/components/app/empty-state";
import { RiskPill, type RiskLevel } from "@/components/app/risk-pill";
import { StatTile } from "@/components/app/stat-tile";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { BodyPainDiagram } from "@/components/BodyPainDiagram";
import { analyzeReportImage, diagnoseText, fetchAiInsights } from "@/lib/api";
import { finishConsultation } from "@/lib/consultationSession";
import {
  LANGUAGE_OPTIONS,
  useConsultationCapture,
  type CardiacRegionEntry
} from "@/lib/useConsultationCapture";
import type { DiagnosisResponse, ReportImageAnalysis } from "@/lib/types";
import { cn } from "@/lib/utils";

const EXAMPLES = [
  { chip: "Exertional chest pressure", text: "I feel chest pressure and shortness of breath when walking upstairs." },
  { chip: "Palpitations with dizziness", text: "Occasional palpitations and dizziness, especially after standing up." },
  { chip: "Fatigue and tightness", text: "Unusual fatigue and mild chest tightness after climbing stairs." },
  { chip: "Pleuritic chest pain", text: "Sharp chest pain when breathing deeply, worse when lying down." }
];

const inputClass =
  "h-9 w-full rounded-lg border border-line bg-inset px-3 text-sm text-fg transition-colors placeholder:text-faint hover:border-line2 focus:border-accent/45";

/**
 * Speaker control: Auto lets the copilot attribute each line from the
 * wording (symptom-telling = patient, clinical/informing = doctor);
 * the manual roles take over attribution when picked.
 */
function SpeakerControl({
  auto,
  speaker,
  onAuto,
  onPick
}: {
  auto: boolean;
  speaker: "doctor" | "patient";
  onAuto: () => void;
  onPick: (role: "doctor" | "patient") => void;
}) {
  const option = (active: boolean) =>
    cn(
      "flex flex-1 items-center justify-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium transition-colors duration-150",
      active ? "bg-elev text-fg" : "text-muted hover:text-fg"
    );
  return (
    <div className="flex rounded-lg border border-line bg-inset p-1">
      <button type="button" onClick={onAuto} className={option(auto)} title="Detect who is speaking from the wording">
        <Sparkles className="h-3.5 w-3.5" strokeWidth={1.75} />
        Auto
      </button>
      <button type="button" onClick={() => onPick("patient")} className={option(!auto && speaker === "patient")}>
        <User className="h-3.5 w-3.5" strokeWidth={1.75} />
        Patient
      </button>
      <button type="button" onClick={() => onPick("doctor")} className={option(!auto && speaker === "doctor")}>
        <Stethoscope className="h-3.5 w-3.5" strokeWidth={1.75} />
        Doctor
      </button>
    </div>
  );
}

export function ConsultationPage() {
  const capture = useConsultationCapture();
  const {
    speaker,
    setSpeaker,
    autoSpeaker,
    setAutoSpeaker,
    language,
    changeLanguage,
    isListening,
    toggleListening,
    micState,
    lines,
    interimText,
    listeningHint,
    micLevel,
    speechActive,
    lastHeard,
    draft,
    setDraft,
    submitDraft,
    clearTranscript,
    reportText,
    setReportText,
    connected,
    awaitingCopilot,
    error,
    symptoms,
    riskLevel,
    bodyInsights,
    doctorQuestions,
    recommendedTests,
    diagnosticImpression,
    nextSteps,
    safetyNote,
    cardiacRegions
  } = capture;

  const [mode, setMode] = useState<"quick" | "full">("quick");

  // Visit details — shared across both modes, used by Save visit.
  const [patientName, setPatientName] = useState("");
  const [patientAge, setPatientAge] = useState("");
  const [patientGender, setPatientGender] = useState("");
  const [visitDate, setVisitDate] = useState(new Date().toISOString().slice(0, 10));
  const [doctorName, setDoctorName] = useState("");
  const [chiefComplaint, setChiefComplaint] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [savedId, setSavedId] = useState<number | null>(null);
  const [voiceNotice, setVoiceNotice] = useState("");

  // Latest values for the voice-command effect without re-subscribing it.
  const savingRef = useRef(saving);
  const linesCountRef = useRef(lines.length);
  const saveFnRef = useRef<() => Promise<void>>(async () => {});
  savingRef.current = saving;
  linesCountRef.current = lines.length;

  // Hands-free: "save visit" runs the same guarded save as the button;
  // "clear transcript" is wiped inside the hook, so only a notice is due.
  useEffect(() => {
    const event = capture.lastVoiceCommand;
    if (!event) return;
    if (event.command === "save-visit") {
      if (savingRef.current) {
        setVoiceNotice("Save already in progress…");
        return;
      }
      if (linesCountRef.current === 0) {
        setVoiceNotice("Nothing to save yet — the transcript is empty.");
        return;
      }
      setVoiceNotice("Voice command heard — saving the visit…");
      void saveFnRef.current();
    } else if (event.command === "clear-transcript") {
      setSavedId(null);
      setSaveError("");
      setVoiceNotice("Transcript cleared by voice command.");
    }
  }, [capture.lastVoiceCommand]);

  // The notice is momentary; nothing should stick around for a minute.
  useEffect(() => {
    if (!voiceNotice) return;
    const timer = window.setTimeout(() => setVoiceNotice(""), 6000);
    return () => window.clearTimeout(timer);
  }, [voiceNotice]);

  // Narrative screening (the old screening page, folded in here).
  const [screenText, setScreenText] = useState("");
  const [screenResult, setScreenResult] = useState<DiagnosisResponse | null>(null);
  const [screenLoading, setScreenLoading] = useState(false);
  const [screenError, setScreenError] = useState("");
  const [insights, setInsights] = useState("");
  const [insightsLoading, setInsightsLoading] = useState(false);
  const [insightsError, setInsightsError] = useState("");

  // Report image reading.
  const [reportImageFile, setReportImageFile] = useState<File | null>(null);
  const [imageAnalysis, setImageAnalysis] = useState<ReportImageAnalysis | null>(null);
  const [imageLoading, setImageLoading] = useState(false);
  const [imageError, setImageError] = useState("");

  async function handleSaveVisit() {
    if (saving) return;
    setSaveError("");
    setSaving(true);
    try {
      const result = await finishConsultation({
        meta: {
          patientName: patientName.trim() || "Unnamed patient",
          patientAge: patientAge.trim() || "—",
          patientGender: patientGender.trim() || "—",
          visitDate,
          doctorName: doctorName.trim() || "—",
          chiefComplaint: chiefComplaint.trim() || symptoms.join(", ") || "—"
        },
        riskLevel,
        lines,
        symptomNotes: symptoms,
        doctorQuestions,
        recommendedTests,
        diagnosticImpression,
        nextSteps,
        reportText,
        lastHeardText: lastHeard
      });
      setSavedId(result.savedId ?? (result.saved ? 0 : null));
      if (!result.saved) {
        setSaveError(
          "The report downloaded, but saving to your records failed. Check that the backend is running and try Save again."
        );
      }
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Saving the visit failed. Try again once the engine is reachable.");
    } finally {
      setSaving(false);
    }
  }
  // Voice commands invoke the latest save closure (fresh patient fields).
  saveFnRef.current = handleSaveVisit;

  async function handleScreen(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = screenText.trim();
    if (!trimmed) {
      setScreenError("Enter a symptom description before running a screening.");
      return;
    }
    setScreenError("");
    setScreenLoading(true);
    setScreenResult(null);
    setInsights("");
    try {
      setScreenResult(await diagnoseText(trimmed, patientName.trim()));
    } catch {
      setScreenError("The screening engine did not respond. Confirm the PulseIQ backend is listening on localhost:8000.");
    } finally {
      setScreenLoading(false);
    }
  }

  async function handleInterpret() {
    if (!screenText.trim()) return;
    setInsightsLoading(true);
    setInsightsError("");
    try {
      const response = await fetchAiInsights(screenText.trim());
      if (response.error) {
        setInsightsError(response.error);
        return;
      }
      setInsights(response.insights ?? "");
    } catch {
      setInsightsError("Interpretation could not be generated right now.");
    } finally {
      setInsightsLoading(false);
    }
  }

  async function fileToBase64(file: File): Promise<string> {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const result = typeof reader.result === "string" ? reader.result : "";
        resolve(result.split(",")[1] ?? "");
      };
      reader.onerror = () => reject(new Error("Failed to read file."));
      reader.readAsDataURL(file);
    });
  }

  async function handleAnalyzeImage() {
    if (!reportImageFile) {
      setImageError("Select a report image first.");
      return;
    }
    setImageError("");
    setImageLoading(true);
    try {
      const base64 = await fileToBase64(reportImageFile);
      setImageAnalysis(await analyzeReportImage(base64, reportImageFile.type || "image/png"));
    } catch (err) {
      setImageError(err instanceof Error ? err.message : "Failed to analyze report image.");
    } finally {
      setImageLoading(false);
    }
  }

  // ------------------------------------------------------------------
  // Shared sections (rendered inside whichever mode is active)
  // ------------------------------------------------------------------

  const captureCard = (
    <Card>
      <CardHeader>
        <CardTitle>Capture</CardTitle>
        <CardDescription>
          One tap starts the microphone. The copilot attributes each line automatically.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <SpeakerControl
          auto={autoSpeaker}
          speaker={speaker}
          onAuto={() => setAutoSpeaker(true)}
          onPick={setSpeaker}
        />
        {autoSpeaker ? (
          <p className="text-2xs leading-relaxed text-faint">
            Auto: lines that tell symptoms are marked <span className="font-medium text-muted">patient</span>; clinical
            or informing lines are marked <span className="font-medium text-muted">doctor</span>.
          </p>
        ) : null}

        <div className="space-y-1.5">
          <label className="label block" htmlFor="consult-language">Input language</label>
          <select
            id="consult-language"
            value={language}
            onChange={(e) => changeLanguage(e.target.value)}
            className={inputClass}
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
          onClick={toggleListening}
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
          <>
            <p className="flex items-center gap-2 text-2xs text-danger-strong">
              <Radio className="h-3 w-3 animate-pulse-soft" strokeWidth={2} />
              {speechActive ? "Hearing you — keep going" : "Capturing audio — speak naturally"}
            </p>
            <div
              className="h-1.5 w-full overflow-hidden rounded-full border border-line bg-inset"
              role="meter"
              aria-label="Microphone level"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={Math.round(micLevel * 100)}
            >
              <div
                className={cn(
                  "h-full rounded-full transition-[width] duration-75",
                  speechActive ? "bg-ok" : "bg-accent/70"
                )}
                style={{ width: `${Math.max(2, Math.round(micLevel * 100))}%` }}
              />
            </div>
          </>
        ) : null}

        {micState === "denied" ? (
          <p className="text-2xs leading-relaxed text-danger-strong">
            Microphone blocked. Allow it in browser site settings, then start listening again.
          </p>
        ) : null}

        {lastHeard ? (
          <div className="rounded-lg border border-line bg-inset px-3 py-2.5">
            <p className="label">Last captured</p>
            <p className="mt-1 line-clamp-3 text-xs leading-relaxed text-muted">{lastHeard}</p>
          </div>
        ) : null}

        {error ? (
          <Alert variant="destructive">
            <AlertCircle />
            <AlertTitle>Stream status</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        ) : null}
      </CardContent>
    </Card>
  );

  const manualCard = (
    <Card>
      <CardHeader>
        <CardTitle>Manual entry</CardTitle>
        <CardDescription>Lines typed here join the same transcript and analysis as the audio.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <Textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          rows={3}
          placeholder="Type a transcript line instead of speaking…"
          className="min-h-[84px]"
        />
        <Button type="button" variant="outline" className="w-full" disabled={!draft.trim()} onClick={submitDraft}>
          <Send className="h-4 w-4" strokeWidth={1.9} />
          Submit line
        </Button>

        <div className="space-y-2 border-t border-line pt-4">
          <label className="label block" htmlFor="consult-report">Test / report context</label>
          <Textarea
            id="consult-report"
            value={reportText}
            onChange={(e) => setReportText(e.target.value)}
            rows={3}
            placeholder="e.g. Troponin elevated, anterior ST elevation, reduced EF on echo"
            className="min-h-[80px]"
          />
        </div>
      </CardContent>
    </Card>
  );

  const visitDetailsCard = (
    <Card>
      <CardHeader>
        <CardTitle>Patient details</CardTitle>
        <CardDescription>Head the exported report. Everything else on this page is already captured.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <input
          className={inputClass}
          value={patientName}
          onChange={(e) => setPatientName(e.target.value)}
          placeholder="Patient name"
          aria-label="Patient name"
        />
        <div className="grid grid-cols-2 gap-2">
          <input
            className={inputClass}
            value={patientAge}
            onChange={(e) => setPatientAge(e.target.value)}
            placeholder="Age"
            aria-label="Patient age"
            inputMode="numeric"
          />
          <input
            className={inputClass}
            value={patientGender}
            onChange={(e) => setPatientGender(e.target.value)}
            placeholder="Gender"
            aria-label="Patient gender"
          />
        </div>
        <div className="grid grid-cols-2 gap-2">
          <input
            className={inputClass}
            type="date"
            value={visitDate}
            onChange={(e) => setVisitDate(e.target.value)}
            aria-label="Visit date"
          />
          <input
            className={inputClass}
            value={doctorName}
            onChange={(e) => setDoctorName(e.target.value)}
            placeholder="Doctor name"
            aria-label="Doctor name"
          />
        </div>
        <input
          className={inputClass}
          value={chiefComplaint}
          onChange={(e) => setChiefComplaint(e.target.value)}
          placeholder="Chief complaint (auto: detected concepts)"
          aria-label="Chief complaint"
        />
      </CardContent>
    </Card>
  );

  const saveCard = (
    <Card>
      <CardHeader>
        <CardTitle>Finish &amp; save</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <Button onClick={handleSaveVisit} size="lg" className="w-full" disabled={saving || lines.length === 0}>
          {saving ? (
            <LoaderCircle className="h-4 w-4 animate-spin" strokeWidth={1.9} />
          ) : savedId !== null ? (
            <BadgeCheck className="h-4 w-4" strokeWidth={1.9} />
          ) : (
            <Save className="h-4 w-4" strokeWidth={1.9} />
          )}
          {saving ? "Saving visit…" : savedId !== null ? "Visit saved" : "Save visit & export PDF"}
        </Button>
        {voiceNotice ? <p className="text-2xs font-medium text-accent">{voiceNotice}</p> : null}
        <p className="text-2xs leading-relaxed text-faint">
          One click downloads the structured report as a PDF and stores the visit in your records — transcript, detected
          concepts, guidance and body map included. A patient name makes it findable on the Patients page.
        </p>

        {savedId !== null ? (
          <Alert variant="success">
            <BadgeCheck />
            <AlertTitle>Visit saved</AlertTitle>
            <AlertDescription>
              The PDF downloaded and the record is in your account. Open History → Consultations to review or re-export it.
            </AlertDescription>
          </Alert>
        ) : null}

        {saveError ? (
          <Alert variant="destructive">
            <AlertCircle />
            <AlertTitle>Save failed</AlertTitle>
            <AlertDescription>{saveError}</AlertDescription>
          </Alert>
        ) : null}
      </CardContent>
    </Card>
  );

  const transcriptCard = (
    <Card>
      <CardHeader className="flex-row items-center justify-between gap-3 space-y-0 border-b border-line pb-4">
        <div>
          <CardTitle>Transcript</CardTitle>
          <CardDescription className="mt-1">
            <span className="num">{lines.length}</span> line{lines.length === 1 ? "" : "s"} captured
            {awaitingCopilot ? (
              <span className="ml-2 inline-flex items-center gap-1 text-accent">
                <LoaderCircle className="h-3 w-3 animate-spin" strokeWidth={2} />
                copilot refining…
              </span>
            ) : null}
          </CardDescription>
        </div>
        <Button size="icon" variant="ghost" aria-label="Clear transcript" onClick={clearTranscript}>
          <Trash2 className="h-4 w-4" strokeWidth={1.75} />
        </Button>
      </CardHeader>
      <CardContent className="pt-4">
        <div className="h-[320px] space-y-3 overflow-y-auto pr-1">
          {lines.length === 0 && !interimText ? (
            <EmptyState
              icon={Mic}
              title="Waiting for the first line"
              description="Speak into the microphone or type an entry. Concepts, risk and the body map update after every line."
              className="h-full"
            />
          ) : (
            <>
              {lines.map((line) => (
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
              ))}
              {interimText ? (
                <div className="ml-auto max-w-[86%] rounded-xl border border-dashed border-accent/30 bg-accent/[0.04] px-3.5 py-2.5">
                  <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-accent">listening</span>
                  <p className="mt-1 text-sm italic leading-relaxed text-muted">{interimText}</p>
                </div>
              ) : null}
              {!interimText && listeningHint && isListening ? (
                <p className="text-center text-2xs italic leading-relaxed text-faint">{listeningHint}</p>
              ) : null}
            </>
          )}
        </div>

        <div className="mt-4 flex flex-wrap gap-2 border-t border-line pt-4">
          {symptoms.length === 0 ? (
            <p className="text-2xs text-faint">Detected concepts appear here the moment a line is captured.</p>
          ) : (
            symptoms.map((symptom) => (
              <Badge key={symptom} variant="secondary" dot>
                {symptom}
              </Badge>
            ))
          )}
        </div>
      </CardContent>
    </Card>
  );

  const guidancePanels: { title: string; icon: typeof Mic; items: string[] }[] = [
    { title: "Suggested questions", icon: Stethoscope, items: doctorQuestions },
    { title: "Recommended tests", icon: ListChecks, items: recommendedTests },
    { title: "Diagnostic direction", icon: HeartPulse, items: diagnosticImpression },
    { title: "Next steps", icon: CheckCircle2, items: nextSteps }
  ];

  const guidanceGrid = (
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
              <p className="mt-3 border-t border-line pt-3 text-2xs italic leading-relaxed text-faint">{safetyNote}</p>
            ) : null}
          </CardContent>
        </Card>
      ))}
    </div>
  );

  const bodyMapColumn = (
    <div className="space-y-5">
      <Card>
        <CardHeader className="pb-3">
          <CardTitle>Body pain map</CardTitle>
          <CardDescription className="mt-1">Accumulates every location reported across the encounter.</CardDescription>
        </CardHeader>
        <CardContent>
          <BodyPainDiagram insights={bodyInsights} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-sm">
            <MapPin className="h-3.5 w-3.5 text-accent" strokeWidth={1.75} />
            Detected regions
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {bodyInsights.length === 0 ? (
            <p className="text-2xs text-faint">No pain location described yet.</p>
          ) : (
            bodyInsights.map((insight) => (
              <div key={insight.region} className="rounded-lg border border-line bg-inset p-3">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-xs font-medium text-fg">{insight.label}</p>
                  <Badge variant={insight.urgency === "high" ? "destructive" : insight.urgency === "moderate" ? "warn" : "ok"} dot>
                    {insight.urgency}
                  </Badge>
                </div>
                <p className="mt-1.5 text-2xs leading-relaxed text-muted">{insight.possibleFactors[0]}</p>
              </div>
            ))
          )}
        </CardContent>
      </Card>

      {cardiacRegions.length > 0 ? (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm">Cardiac hypotheses</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {cardiacRegions.map((entry: CardiacRegionEntry) => (
              <div key={entry.region} className="rounded-lg border border-line bg-inset p-3">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-xs font-medium text-fg">{entry.region}</p>
                  <Badge
                    variant={entry.likelihood === "high" ? "destructive" : entry.likelihood === "moderate" ? "warn" : "ok"}
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
  );

  // Narrative screening + report image — the old screening page, folded in.
  const assessRow = (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ScanLine className="h-4 w-4 text-accent" strokeWidth={1.75} />
            Assess a narrative
          </CardTitle>
          <CardDescription className="mt-1">
            Paste or dictate the whole story for a scored risk estimate with the reasoning attached.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleScreen} className="space-y-4">
            <Textarea
              value={screenText}
              onChange={(e) => setScreenText(e.target.value)}
              placeholder="e.g. Tightness in the centre of my chest for two days, brought on by climbing stairs and relieved within a few minutes of resting."
              rows={4}
              className="min-h-[104px]"
            />
            <div className="flex flex-wrap gap-2">
              {EXAMPLES.map((example) => (
                <button
                  key={example.chip}
                  type="button"
                  title={example.text}
                  onClick={() => setScreenText(example.text)}
                  className="rounded-full border border-line bg-elev/60 px-3 py-1.5 text-xs text-muted transition-colors duration-150 hover:border-accent/40 hover:bg-accent/10 hover:text-accent"
                >
                  {example.chip}
                </button>
              ))}
            </div>

            {screenError ? (
              <Alert variant="destructive">
                <AlertCircle />
                <AlertTitle>Screening</AlertTitle>
                <AlertDescription>{screenError}</AlertDescription>
              </Alert>
            ) : null}

            <div className="flex justify-end border-t border-line pt-4">
              <Button type="submit" disabled={screenLoading}>
                {screenLoading ? (
                  <LoaderCircle className="h-4 w-4 animate-spin" />
                ) : (
                  <Wand2 className="h-4 w-4" strokeWidth={1.9} />
                )}
                {screenLoading ? "Scoring…" : "Run screening"}
              </Button>
            </div>
          </form>

          {screenResult ? (
            <div className="animate-fade-up space-y-4 border-t border-line pt-4">
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <StatTile
                  label="Probability"
                  value={`${(screenResult.probability * 100).toFixed(1)}%`}
                  tone={screenResult.risk_level === "High" ? "danger" : screenResult.risk_level === "Medium" ? "warn" : "accent"}
                />
                <StatTile label="Band" value={screenResult.risk_level} hint="Escalation guidance" />
                <StatTile
                  label="Verdict"
                  value={screenResult.prediction === 1 ? "Flagged" : "Clear"}
                  tone={screenResult.prediction === 1 ? "danger" : "ok"}
                />
                <StatTile label="Concepts" value={screenResult.symptoms.length} hint="Normalised terms" />
              </div>

              {screenResult.symptoms.length > 0 ? (
                <div className="flex flex-wrap gap-2">
                  {screenResult.symptoms.map((symptom) => (
                    <Badge key={symptom} variant="secondary" dot>
                      {symptom}
                    </Badge>
                  ))}
                </div>
              ) : null}

              <div className="rounded-lg border border-line bg-inset p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <p className="flex items-center gap-2 text-xs text-muted">
                    <Sparkles className="h-3.5 w-3.5 text-accent" strokeWidth={1.75} />
                    Written interpretation of this result
                  </p>
                  <Button onClick={handleInterpret} disabled={insightsLoading} variant="outline" size="sm">
                    {insightsLoading ? (
                      <LoaderCircle className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Wand2 className="h-3.5 w-3.5" strokeWidth={1.9} />
                    )}
                    {insightsLoading ? "Writing…" : "Interpret"}
                  </Button>
                </div>
                {insightsError ? (
                  <Alert variant="destructive" className="mt-3">
                    <AlertCircle />
                    <AlertTitle>Interpretation unavailable</AlertTitle>
                    <AlertDescription>{insightsError}</AlertDescription>
                  </Alert>
                ) : null}
                {insights ? (
                  <p className="mt-3 animate-fade-in whitespace-pre-wrap border-t border-line pt-3 text-sm leading-relaxed text-muted">
                    {insights}
                  </p>
                ) : null}
              </div>
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ImageUp className="h-4 w-4 text-accent" strokeWidth={1.75} />
            Read a lab report or scan
          </CardTitle>
          <CardDescription className="mt-1">
            Upload a photograph of a report to pull out findings, suggested tests and red flags.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <input
              type="file"
              accept="image/png,image/jpeg,image/jpg,image/webp"
              onChange={(e) => setReportImageFile(e.target.files?.[0] ?? null)}
              className="block w-full cursor-pointer rounded-lg border border-line bg-inset px-3 py-2 text-xs text-muted transition-colors file:mr-3 file:rounded-md file:border-0 file:bg-elev file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-fg hover:border-line2"
            />
            <Button onClick={handleAnalyzeImage} disabled={imageLoading} variant="outline" className="shrink-0">
              {imageLoading ? (
                <LoaderCircle className="h-4 w-4 animate-spin" />
              ) : (
                <ScanLine className="h-4 w-4" strokeWidth={1.9} />
              )}
              Analyze image
            </Button>
          </div>

          <p className="flex items-start gap-2 text-2xs leading-relaxed text-faint">
            <Info className="mt-px h-3 w-3 shrink-0" strokeWidth={1.75} />
            Image reading needs a vision model through Ollama or a Gemini key. Everything else works without either.
          </p>

          {imageError ? (
            <Alert variant="destructive">
              <AlertCircle />
              <AlertTitle>Image analysis</AlertTitle>
              <AlertDescription>{imageError}</AlertDescription>
            </Alert>
          ) : null}

          {imageAnalysis ? (
            <div className="animate-fade-up space-y-4 rounded-lg border border-line bg-inset p-4">
              <div>
                <p className="label">Summary</p>
                <p className="mt-1.5 text-sm leading-relaxed text-muted">{imageAnalysis.summary}</p>
              </div>
              {imageAnalysis.key_findings.length > 0 ? (
                <div>
                  <p className="label">Key findings</p>
                  <ul className="mt-1.5 space-y-1">
                    {imageAnalysis.key_findings.map((item) => (
                      <li key={item} className="flex gap-2 text-xs leading-relaxed text-muted">
                        <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-line2" />
                        {item}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
              {imageAnalysis.recommended_tests.length > 0 ? (
                <div className="flex flex-wrap gap-2">
                  {imageAnalysis.recommended_tests.map((item) => (
                    <Badge key={item} variant="info">
                      {item}
                    </Badge>
                  ))}
                </div>
              ) : null}
              {imageAnalysis.red_flags.length > 0 ? (
                <div className="flex flex-wrap gap-2">
                  {imageAnalysis.red_flags.map((item) => (
                    <Badge key={item} variant="destructive" dot>
                      {item}
                    </Badge>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );

  return (
    <div>
      <PageHeader
        eyebrow="Workspace"
        icon={Stethoscope}
        title="Consultation"
        description="One screen for the whole encounter: speak or type, watch concepts, risk and the body map update instantly, screen a narrative, then save the visit in one click."
        actions={
          <>
            <Badge variant={connected ? "ok" : "destructive"} dot>
              {connected ? "Realtime connected" : "Offline"}
            </Badge>
            <RiskPill level={riskLevel} />
          </>
        }
      />

      <Tabs value={mode} onValueChange={(value) => setMode(value as "quick" | "full")}>
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
          <TabsList className="w-full sm:w-auto">
            <TabsTrigger value="quick">
              <Mic className="h-3.5 w-3.5" strokeWidth={1.75} />
              Quick consult
            </TabsTrigger>
            <TabsTrigger value="full">
              <User className="h-3.5 w-3.5" strokeWidth={1.75} />
              Full consult
            </TabsTrigger>
          </TabsList>
          {mode === "quick" ? (
            <p className="text-2xs text-faint">
              Audio-first: everything typed here is already in the transcript. Switch to Full consult for patient details.
            </p>
          ) : (
            <p className="text-2xs text-faint">Synced with Quick consult — the transcript and analysis are the same.</p>
          )}
        </div>

        <TabsContent value="quick">
          <div className="grid gap-5 xl:grid-cols-[320px_minmax(0,1fr)_288px]">
            <div className="space-y-5">
              {captureCard}
              {manualCard}
              {saveCard}
            </div>
            <div className="space-y-5">
              {transcriptCard}
              {guidanceGrid}
            </div>
            {bodyMapColumn}
          </div>
        </TabsContent>

        <TabsContent value="full">
          <div className="grid gap-5 xl:grid-cols-[320px_minmax(0,1fr)_288px]">
            <div className="space-y-5">
              {visitDetailsCard}
              {manualCard}
              {saveCard}
            </div>
            <div className="space-y-5">
              {transcriptCard}
              {guidanceGrid}
            </div>
            {bodyMapColumn}
          </div>
        </TabsContent>
      </Tabs>

      <div className="mt-5">{assessRow}</div>
    </div>
  );
}
