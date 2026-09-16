import { FormEvent, useState } from "react";
import {
  AlertCircle,
  ImageUp,
  Info,
  LoaderCircle,
  ScanLine,
  Sparkles,
  Wand2
} from "lucide-react";
import { analyzeReportImage, diagnoseText, fetchAiInsights } from "@/lib/api";
import { addHistoryItem } from "@/lib/history";
import type { DiagnosisResponse, ReportImageAnalysis } from "@/lib/types";
import { PageHeader } from "@/components/app/page-header";
import { RiskPill, type RiskLevel } from "@/components/app/risk-pill";
import { StatTile } from "@/components/app/stat-tile";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

const EXAMPLES = [
  {
    chip: "Exertional chest pressure",
    text: "I feel chest pressure and shortness of breath when walking upstairs."
  },
  { chip: "Palpitations with dizziness", text: "Occasional palpitations and dizziness, especially after standing up." },
  { chip: "Fatigue and tightness", text: "Unusual fatigue and mild chest tightness after climbing stairs." },
  { chip: "Pleuritic chest pain", text: "Sharp chest pain when breathing deeply, worse when lying down." }
];

/** Model inputs, in the exact order the backend assembles them. */
const FEATURE_LABELS: { name: string; label: string; unit?: string }[] = [
  { name: "age", label: "Age", unit: "yrs" },
  { name: "sex", label: "Sex (0 F / 1 M)" },
  { name: "cp", label: "Chest pain type" },
  { name: "trestbps", label: "Resting BP", unit: "mmHg" },
  { name: "chol", label: "Cholesterol", unit: "mg/dl" },
  { name: "fbs", label: "Fasting glucose flag" },
  { name: "restecg", label: "Resting ECG" },
  { name: "thalach", label: "Max heart rate", unit: "bpm" },
  { name: "exang", label: "Exercise angina" },
  { name: "oldpeak", label: "ST depression" },
  { name: "slope", label: "ST slope" },
  { name: "ca", label: "Major vessels" },
  { name: "thal", label: "Thalassemia study" }
];

function RiskScale({ probability, level }: { probability: number; level: RiskLevel }) {
  const pct = Math.min(100, Math.max(0, probability * 100));
  const fill = level === "High" ? "bg-danger" : level === "Medium" ? "bg-warn" : "bg-ok";

  return (
    <div>
      <div className="relative h-2 w-full overflow-hidden rounded-full border border-line bg-inset">
        <div
          className={cn("h-full rounded-full transition-[width] duration-700 ease-out", fill)}
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="num mt-2 flex justify-between text-[10px] text-faint">
        <span>0</span>
        <span>25</span>
        <span>50</span>
        <span>75</span>
        <span>100%</span>
      </div>
    </div>
  );
}

export function DiagnosePage() {
  const [text, setText] = useState("");
  const [validationError, setValidationError] = useState("");
  const [requestError, setRequestError] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<DiagnosisResponse | null>(null);
  const [insights, setInsights] = useState("");
  const [insightsError, setInsightsError] = useState("");
  const [insightsLoading, setInsightsLoading] = useState(false);
  const [reportImageFile, setReportImageFile] = useState<File | null>(null);
  const [reportImageAnalysis, setReportImageAnalysis] = useState<ReportImageAnalysis | null>(null);
  const [analyzingReportImage, setAnalyzingReportImage] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setRequestError("");

    const trimmed = text.trim();
    if (!trimmed) {
      setValidationError("Enter a symptom description before running a screening.");
      return;
    }

    setValidationError("");
    setLoading(true);
    setInsights("");
    setInsightsError("");
    setReportImageAnalysis(null);
    try {
      const diagnosis = await diagnoseText(trimmed);
      setResult(diagnosis);
      addHistoryItem(diagnosis);
    } catch {
      setRequestError(
        "The screening engine did not respond. Confirm the PulseIQ backend is listening on localhost:8000."
      );
    } finally {
      setLoading(false);
    }
  }

  async function handleGenerateInsights() {
    if (!text.trim()) return;
    setInsightsLoading(true);
    setInsightsError("");
    try {
      const response = await fetchAiInsights(text.trim());
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
        const base64 = result.split(",")[1] ?? "";
        resolve(base64);
      };
      reader.onerror = () => reject(new Error("Failed to read file."));
      reader.readAsDataURL(file);
    });
  }

  async function handleAnalyzeReportImage() {
    if (!reportImageFile) {
      setRequestError("Select a report image first.");
      return;
    }
    setAnalyzingReportImage(true);
    setRequestError("");
    try {
      const base64 = await fileToBase64(reportImageFile);
      const analysis = await analyzeReportImage(base64, reportImageFile.type || "image/png");
      setReportImageAnalysis(analysis);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to analyze report image.";
      setRequestError(message);
    } finally {
      setAnalyzingReportImage(false);
    }
  }

  const riskLevel = (result?.risk_level ?? "Low") as RiskLevel;

  return (
    <div>
      <PageHeader
        eyebrow="Assess"
        icon={ScanLine}
        title="Symptom screening"
        description="Describe the complaint the way a patient would. PulseIQ extracts the clinical concepts, maps them to model inputs, and returns an explained risk estimate with the reasoning attached."
      />

      <div className="space-y-5">
        {/* Intake */}
        <Card>
          <CardHeader>
            <div className="flex items-start justify-between gap-4">
              <div>
                <CardTitle>Clinical narrative</CardTitle>
                <CardDescription className="mt-1">
                  Onset, character, radiation, triggers and associated symptoms all improve the mapping.
                </CardDescription>
              </div>
              <Badge variant="secondary">Free text</Badge>
            </div>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              <Textarea
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="e.g. Tightness in the centre of my chest for two days, brought on by climbing stairs and relieved within a few minutes of resting. No radiation."
                rows={5}
                className="min-h-[132px]"
              />

              <div>
                <p className="label mb-2">Common presentations</p>
                <div className="flex flex-wrap gap-2">
                  {EXAMPLES.map((example) => (
                    <button
                      key={example.chip}
                      type="button"
                      title={example.text}
                      onClick={() => setText(example.text)}
                      className="rounded-full border border-line bg-elev/60 px-3 py-1.5 text-xs text-muted transition-colors duration-150 hover:border-accent/40 hover:bg-accent/10 hover:text-accent"
                    >
                      {example.chip}
                    </button>
                  ))}
                </div>
              </div>

              {validationError ? (
                <Alert variant="destructive">
                  <AlertCircle />
                  <AlertTitle>Input required</AlertTitle>
                  <AlertDescription>{validationError}</AlertDescription>
                </Alert>
              ) : null}

              {requestError ? (
                <Alert variant="destructive">
                  <AlertCircle />
                  <AlertTitle>Engine unavailable</AlertTitle>
                  <AlertDescription>{requestError}</AlertDescription>
                </Alert>
              ) : null}

              <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line pt-4">
                <p className="num text-2xs text-faint">{text.trim().length} characters</p>
                <Button type="submit" size="lg" disabled={loading}>
                  {loading ? (
                    <LoaderCircle className="h-4 w-4 animate-spin" />
                  ) : (
                    <Wand2 className="h-4 w-4" strokeWidth={1.9} />
                  )}
                  {loading ? "Scoring…" : "Run screening"}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>

        {loading ? (
          <Card>
            <CardContent className="space-y-3 pt-5">
              <Skeleton className="h-4 w-40" />
              <Skeleton className="h-20 w-full" />
              <Skeleton className="h-4 w-2/3" />
            </CardContent>
          </Card>
        ) : null}

        {/* Result */}
        {result ? (
          <Card className="animate-fade-up">
            <CardHeader>
              <div className="flex items-start justify-between gap-4">
                <div>
                  <CardTitle>Risk estimate</CardTitle>
                  <CardDescription className="mt-1">
                    Produced by the bundled model. Attribution below shows what moved the score.
                  </CardDescription>
                </div>
                <RiskPill level={riskLevel} />
              </div>
            </CardHeader>
            <CardContent className="space-y-5">
              <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
                <div className="panel-flat px-4 py-4">
                  <p className="label">Estimated probability</p>
                  <p className="num mt-2 text-4xl font-semibold text-fg">
                    {(result.probability * 100).toFixed(1)}
                    <span className="ml-0.5 text-lg font-medium text-faint">%</span>
                  </p>
                  <div className="mt-4">
                    <RiskScale probability={result.probability} level={riskLevel} />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <StatTile
                    label="Model verdict"
                    value={result.prediction === 1 ? "Flagged" : "Clear"}
                    tone={result.prediction === 1 ? "danger" : "ok"}
                    hint={result.prediction === 1 ? "Follow-up advised" : "No pattern detected"}
                  />
                  <StatTile
                    label="Concepts found"
                    value={result.symptoms.length}
                    hint="Normalised symptom terms"
                  />
                  <StatTile label="Model inputs" value={result.features.length} hint="Mapped feature vector" />
                  <StatTile
                    label="Band"
                    value={result.risk_level}
                    tone={riskLevel === "High" ? "danger" : riskLevel === "Medium" ? "warn" : "ok"}
                    hint="Escalation guidance"
                  />
                </div>
              </div>

              <Tabs defaultValue="attribution">
                <TabsList>
                  <TabsTrigger value="attribution">Attribution</TabsTrigger>
                  <TabsTrigger value="symptoms">Symptoms</TabsTrigger>
                  <TabsTrigger value="trace">Input trace</TabsTrigger>
                </TabsList>

                <TabsContent value="attribution">
                  {result.symptoms.length > 0 ? (
                    <div className="space-y-3">
                      <p className="text-xs leading-relaxed text-muted">
                        Each concept below was resolved from the narrative and contributed to the feature
                        vector that produced this score.
                      </p>
                      <div className="flex flex-wrap gap-2">
                        {result.symptoms.map((symptom) => (
                          <Badge key={symptom} variant="secondary" dot>
                            {symptom}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  ) : (
                    <p className="text-xs text-muted">
                      No recognised cardiac concepts were detected. Treat a low score on an unrecognised
                      narrative as inconclusive rather than reassuring.
                    </p>
                  )}
                </TabsContent>

                <TabsContent value="symptoms">
                  <div className="flex flex-wrap gap-2">
                    {result.symptoms.length > 0 ? (
                      result.symptoms.map((symptom) => (
                        <Badge key={symptom} variant="default" dot>
                          {symptom}
                        </Badge>
                      ))
                    ) : (
                      <p className="text-xs text-muted">No mapped symptoms were detected.</p>
                    )}
                  </div>
                </TabsContent>

                <TabsContent value="trace">
                  <div className="grid gap-x-8 gap-y-0 sm:grid-cols-2">
                    {result.features.map((value, index) => {
                      const meta = FEATURE_LABELS[index];
                      return (
                        <div
                          key={meta?.name ?? index}
                          className="flex items-baseline justify-between gap-3 border-b border-line py-2 last:border-b-0"
                        >
                          <span className="truncate text-xs text-muted">
                            {meta ? meta.label : `Feature ${index + 1}`}
                          </span>
                          <span className="num shrink-0 text-xs font-medium text-fg">
                            {typeof value === "number" ? Number(value.toFixed(3)) : String(value)}
                            {meta?.unit ? <span className="ml-1 text-2xs text-faint">{meta.unit}</span> : null}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </TabsContent>
              </Tabs>

              <div className="rounded-lg border border-line bg-inset p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <p className="flex items-center gap-2 text-xs text-muted">
                    <Sparkles className="h-3.5 w-3.5 text-accent" strokeWidth={1.75} />
                    Generate a written interpretation of this result
                  </p>
                  <Button
                    onClick={handleGenerateInsights}
                    disabled={insightsLoading}
                    variant="outline"
                    size="sm"
                  >
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
                  <div className="mt-3 animate-fade-in border-t border-line pt-3">
                    <p className="whitespace-pre-wrap text-sm leading-relaxed text-muted">{insights}</p>
                  </div>
                ) : null}
              </div>
            </CardContent>
          </Card>
        ) : null}

        {/* Report image */}
        <Card>
          <CardHeader>
            <div className="flex items-start justify-between gap-4">
              <div>
                <CardTitle className="flex items-center gap-2">
                  <ImageUp className="h-4 w-4 text-accent" strokeWidth={1.75} />
                  Read a lab report or scan
                </CardTitle>
                <CardDescription className="mt-1">
                  Upload a photograph of a report to pull out findings, suggested tests and red flags.
                </CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
              <input
                type="file"
                accept="image/png,image/jpeg,image/jpg,image/webp"
                onChange={(e) => setReportImageFile(e.target.files?.[0] ?? null)}
                className="block w-full cursor-pointer rounded-lg border border-line bg-inset px-3 py-2 text-xs text-muted transition-colors file:mr-3 file:rounded-md file:border-0 file:bg-elev file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-fg hover:border-line2"
              />
              <Button
                onClick={handleAnalyzeReportImage}
                disabled={analyzingReportImage}
                variant="outline"
                className="shrink-0"
              >
                {analyzingReportImage ? (
                  <LoaderCircle className="h-4 w-4 animate-spin" />
                ) : (
                  <ScanLine className="h-4 w-4" strokeWidth={1.9} />
                )}
                Analyze image
              </Button>
            </div>

            <p className="flex items-start gap-2 text-2xs leading-relaxed text-faint">
              <Info className="mt-px h-3 w-3 shrink-0" strokeWidth={1.75} />
              Image reading needs a vision model. Install a free local one through Ollama, or supply a
              Gemini key, to enable it. Text screening and everything else works without either.
            </p>

            {reportImageAnalysis ? (
              <div className="animate-fade-up space-y-4 rounded-lg border border-line bg-inset p-4">
                <div>
                  <p className="label">Summary</p>
                  <p className="mt-1.5 text-sm leading-relaxed text-muted">{reportImageAnalysis.summary}</p>
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

                {reportImageAnalysis.recommended_tests.length > 0 ? (
                  <div>
                    <p className="label">Suggested tests</p>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {reportImageAnalysis.recommended_tests.map((item) => (
                        <Badge key={item} variant="info">
                          {item}
                        </Badge>
                      ))}
                    </div>
                  </div>
                ) : null}

                {reportImageAnalysis.red_flags.length > 0 ? (
                  <div>
                    <p className="label">Red flags</p>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {reportImageAnalysis.red_flags.map((item) => (
                        <Badge key={item} variant="destructive" dot>
                          {item}
                        </Badge>
                      ))}
                    </div>
                  </div>
                ) : null}
              </div>
            ) : null}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
