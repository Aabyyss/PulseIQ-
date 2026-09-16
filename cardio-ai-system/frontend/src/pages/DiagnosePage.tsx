import { FormEvent, useState } from "react";
import {
  Activity,
  AlertCircle,
  FileHeart,
  ImageUp,
  Lightbulb,
  LoaderCircle,
  ShieldAlert,
  Sparkles,
} from "lucide-react";
import { analyzeReportImage, diagnoseText, fetchAiInsights } from "@/lib/api";
import { addHistoryItem } from "@/lib/history";
import type { DiagnosisResponse, ReportImageAnalysis } from "@/lib/types";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";

const EXAMPLES = [
  "I feel chest pressure and shortness of breath when walking upstairs.",
  "Occasional palpitations and dizziness, especially after standing up.",
  "Unusual fatigue and mild chest tightness after climbing stairs.",
  "Sharp chest pain when breathing deeply, worse when lying down.",
];

function riskVariant(level: DiagnosisResponse["risk_level"]): "default" | "secondary" | "destructive" {
  if (level === "High") return "destructive";
  if (level === "Medium") return "secondary";
  return "default";
}

function RiskGauge({ probability, risk }: { probability: number; risk: string }) {
  const pct = Math.min(100, Math.max(0, probability * 100));
  const color = risk === "High" ? "#f43f5e" : risk === "Medium" ? "#f59e0b" : "#2dd4bf";
  const circumference = 2 * Math.PI * 52;
  const offset = circumference * (1 - pct / 100);

  return (
    <div className="relative flex h-36 w-36 items-center justify-center">
      <svg viewBox="0 0 120 120" className="h-full w-full -rotate-90">
        <circle cx="60" cy="60" r="52" stroke="rgba(148,163,184,0.15)" strokeWidth="10" fill="none" />
        <circle
          cx="60"
          cy="60"
          r="52"
          stroke={color}
          strokeWidth="10"
          fill="none"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          style={{ transition: "stroke-dashoffset 1s cubic-bezier(0.22,1,0.36,1), stroke 0.4s" }}
        />
      </svg>
      <div className="absolute text-center">
        <p className="text-3xl font-bold text-white">{pct.toFixed(0)}%</p>
        <p className="text-[11px] font-medium uppercase tracking-wider" style={{ color }}>
          {risk} risk
        </p>
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
      setValidationError("Please enter symptom text before submitting.");
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
      setRequestError("Could not reach the diagnosis engine. Confirm the PulseIQ backend is running on localhost:8000.");
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
      setInsightsError("Unable to generate AI insights right now.");
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
      setRequestError("Please select a report image first.");
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

  return (
    <div className="space-y-5">
      {/* Input card */}
      <Card className="card-animate border-slate-800 bg-slate-900/50">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-white">
            <Activity className="h-5 w-5 text-teal-400" />
            Describe your symptoms
          </CardTitle>
          <CardDescription>
            Plain language works best. PulseIQ extracts symptoms, maps them to clinical features, and scores risk.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <form className="space-y-3" onSubmit={handleSubmit}>
            <Textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="e.g. I've had chest pressure and breathlessness for two days when climbing stairs..."
              rows={5}
              className="border-slate-700 bg-slate-950/60 text-slate-100 placeholder:text-slate-600"
            />
            <div className="flex flex-wrap gap-2">
              {EXAMPLES.map((example) => (
                <button
                  key={example}
                  type="button"
                  onClick={() => setText(example)}
                  className="rounded-full border border-slate-700 bg-slate-800/60 px-3 py-1.5 text-xs text-slate-300 transition-colors hover:border-teal-500/50 hover:text-teal-300"
                >
                  {example.length > 52 ? example.slice(0, 52) + "…" : example}
                </button>
              ))}
            </div>
            {validationError ? (
              <Alert variant="destructive">
                <AlertCircle className="h-4 w-4" />
                <AlertTitle>Validation error</AlertTitle>
                <AlertDescription>{validationError}</AlertDescription>
              </Alert>
            ) : null}
            {requestError ? (
              <Alert variant="destructive">
                <AlertCircle className="h-4 w-4" />
                <AlertTitle>Service error</AlertTitle>
                <AlertDescription>{requestError}</AlertDescription>
              </Alert>
            ) : null}
            <Button
              type="submit"
              disabled={loading}
              size="lg"
              className="bg-gradient-to-r from-teal-500 to-sky-500 text-slate-950 hover:from-teal-400 hover:to-sky-400"
            >
              {loading ? <LoaderCircle className="mr-2 h-4 w-4 animate-spin" /> : <Sparkles className="mr-2 h-4 w-4" />}
              {loading ? "Analyzing…" : "Run screening"}
            </Button>
          </form>
        </CardContent>
      </Card>

      {loading ? (
        <Card className="border-slate-800 bg-slate-900/50">
          <CardHeader>
            <Skeleton className="h-7 w-56 bg-slate-800" />
          </CardHeader>
          <CardContent className="space-y-2">
            <Skeleton className="h-5 w-40 bg-slate-800" />
            <Skeleton className="h-24 w-full bg-slate-800" />
          </CardContent>
        </Card>
      ) : null}

      {/* Result */}
      {result ? (
        <Card className="card-animate border-slate-800 bg-slate-900/50">
          <CardHeader>
            <CardTitle className="flex items-center gap-3 text-white">
              <FileHeart className="h-5 w-5 text-teal-400" />
              Screening result
            </CardTitle>
            <CardDescription>Explainable output — see exactly which signals drove the score.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            <div className="flex flex-col items-center gap-6 sm:flex-row sm:items-center">
              <RiskGauge probability={result.probability} risk={result.risk_level} />
              <div className="grid w-full grid-cols-2 gap-3 sm:grid-cols-3">
                <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-4 text-center">
                  <p className="text-2xl font-bold text-white">{result.prediction === 1 ? "Flagged" : "Clear"}</p>
                  <p className="text-xs text-slate-500">Model verdict</p>
                </div>
                <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-4 text-center">
                  <p className="text-2xl font-bold text-white">{result.symptoms.length}</p>
                  <p className="text-xs text-slate-500">Symptoms detected</p>
                </div>
                <div className="col-span-2 rounded-xl border border-slate-800 bg-slate-950/50 p-4 text-center sm:col-span-1">
                  <p className="text-2xl font-bold text-white">{result.features.length}</p>
                  <p className="text-xs text-slate-500">Clinical features</p>
                </div>
              </div>
            </div>

            <div className="rounded-xl border border-teal-500/20 bg-teal-500/5 p-1">
              <Button onClick={handleGenerateInsights} disabled={insightsLoading} variant="ghost" className="w-full text-teal-300 hover:bg-teal-500/10 hover:text-teal-200">
                {insightsLoading ? <LoaderCircle className="mr-2 h-4 w-4 animate-spin" /> : <Lightbulb className="mr-2 h-4 w-4" />}
                {insightsLoading ? "Generating guidance…" : "Generate AI guidance"}
              </Button>
            </div>

            {insightsError ? (
              <Alert variant="destructive" className="mb-4">
                <AlertCircle className="h-4 w-4" />
                <AlertTitle>AI error</AlertTitle>
                <AlertDescription>{insightsError}</AlertDescription>
              </Alert>
            ) : null}
            {insights ? (
              <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-4">
                <p className="mb-2 flex items-center gap-2 text-sm font-semibold text-teal-300">
                  <Sparkles className="h-4 w-4" />
                  AI Guidance
                </p>
                <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed text-slate-300">{insights}</pre>
              </div>
            ) : null}

            <Tabs defaultValue="symptoms">
              <TabsList className="grid w-full grid-cols-3 bg-slate-950/60">
                <TabsTrigger value="symptoms">Symptoms</TabsTrigger>
                <TabsTrigger value="features">Features</TabsTrigger>
                <TabsTrigger value="prediction">Prediction</TabsTrigger>
              </TabsList>
              <TabsContent value="symptoms" className="space-y-2 pt-3">
                {result.symptoms.length > 0 ? (
                  <div className="flex flex-wrap gap-2">
                    {result.symptoms.map((symptom) => (
                      <Badge key={symptom} variant="secondary" className="bg-teal-500/10 text-teal-300">
                        {symptom}
                      </Badge>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-slate-500">No mapped symptoms were detected.</p>
                )}
              </TabsContent>
              <TabsContent value="features" className="pt-3">
                <p className="text-sm text-slate-400">{result.features.join(" · ")}</p>
              </TabsContent>
              <TabsContent value="prediction" className="pt-3">
                <p className="text-sm text-slate-400">
                  Binary model output: <span className="font-semibold text-white">{result.prediction}</span>
                  {" — "}1 indicates a positive screening pattern that warrants clinical follow-up.
                </p>
              </TabsContent>
            </Tabs>
          </CardContent>
        </Card>
      ) : null}

      {/* Report image */}
      <Card className="card-animate border-slate-800 bg-slate-900/50">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-white">
            <ImageUp className="h-5 w-5 text-teal-400" />
            Read a lab report or scan
          </CardTitle>
          <CardDescription>
            Upload a lab report or scan screenshot to extract key findings and suggestions.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <input
            type="file"
            accept="image/png,image/jpeg,image/jpg,image/webp"
            onChange={(e) => setReportImageFile(e.target.files?.[0] ?? null)}
            className="block w-full cursor-pointer rounded-md border border-slate-700 bg-slate-950/60 px-3 py-2 text-sm text-slate-300 file:mr-3 file:rounded-md file:border-0 file:bg-teal-500/20 file:px-3 file:py-1.5 file:text-xs file:font-semibold file:text-teal-300 hover:file:bg-teal-500/30"
          />
          <Button
            onClick={handleAnalyzeReportImage}
            disabled={analyzingReportImage}
            variant="outline"
            className="border-slate-700 bg-slate-950/40 hover:bg-slate-800"
          >
            {analyzingReportImage ? <LoaderCircle className="mr-2 h-4 w-4 animate-spin" /> : null}
            Analyze report image
          </Button>
          <p className="text-xs text-slate-500">
            <ShieldAlert className="mr-1 inline h-3.5 w-3.5" />
            Image reading needs a vision AI model (optional free Ollama vision model or Gemini key). Text screening above works without any setup.
          </p>

          {reportImageAnalysis ? (
            <div className="space-y-3 rounded-xl border border-slate-800 bg-slate-950/60 p-4">
              <p className="font-semibold text-white">Summary</p>
              <p className="text-sm text-slate-300">{reportImageAnalysis.summary}</p>
              {reportImageAnalysis.key_findings.length > 0 ? (
                <>
                  <p className="font-semibold text-white">Key findings</p>
                  <ul className="list-inside list-disc text-sm text-slate-300">
                    {reportImageAnalysis.key_findings.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </>
              ) : null}
              {reportImageAnalysis.recommended_tests.length > 0 ? (
                <div className="flex flex-wrap gap-2 pt-1">
                  {reportImageAnalysis.recommended_tests.map((item) => (
                    <Badge key={item} variant="secondary" className="bg-sky-500/10 text-sky-300">
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
}
