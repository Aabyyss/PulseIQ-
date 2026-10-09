import { useState } from "react";
import {
  AlertTriangle,
  Ban,
  CheckCircle2,
  FlaskConical,
  Info,
  Pill,
  ShieldAlert,
  Sparkles
} from "lucide-react";
import { PageHeader } from "@/components/app/page-header";
import { EmptyState } from "@/components/app/empty-state";
import { RiskPill } from "@/components/app/risk-pill";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { reviewMedications } from "@/lib/api";
import type { MedicationReview } from "@/lib/types";
import { usePageMeta } from "@/lib/usePageMeta";
import { cn } from "@/lib/utils";

const inputClass =
  "h-9 w-full rounded-lg border border-line bg-inset px-3 text-sm text-fg transition-colors placeholder:text-faint hover:border-line2 focus:border-accent/45";

const PATHWAY_TONE = {
  emergency: "destructive",
  urgent: "warning",
  routine: "info"
} as const;

const PATHWAY_LABEL = {
  emergency: "Emergency pathway",
  urgent: "Urgent review",
  routine: "Routine review"
} as const;

const RECOMMENDATION_TONE = {
  recommended: "default",
  alternative: "info",
  "already-documented": "secondary"
} as const;

const RECOMMENDATION_LABEL = {
  recommended: "Option",
  alternative: "Alternative",
  "already-documented": "Already on record"
} as const;

const BLOCK_KIND_LABEL: Record<string, string> = {
  allergy: "Allergy",
  condition: "Condition/history",
  lab: "Laboratory value"
};

function Field({
  label,
  hint,
  children
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block space-y-1.5">
      <span className="label block">{label}</span>
      {children}
      {hint ? <span className="block text-2xs leading-relaxed text-faint">{hint}</span> : null}
    </label>
  );
}

export function MedicationsPage() {
  usePageMeta(
    "Medication review",
    "Medication options and safety review built from the presentation, conditions, history, allergies, current medications and laboratory values."
  );

  const [text, setText] = useState("");
  const [reportText, setReportText] = useState("");
  const [age, setAge] = useState("");
  const [sex, setSex] = useState("");
  const [pregnancy, setPregnancy] = useState<"" | "yes" | "no">("");
  const [conditions, setConditions] = useState("");
  const [allergies, setAllergies] = useState("");
  const [currentMedications, setCurrentMedications] = useState("");

  const [result, setResult] = useState<MedicationReview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const canRun =
    text.trim().length > 0 ||
    reportText.trim().length > 0 ||
    conditions.trim().length > 0 ||
    allergies.trim().length > 0 ||
    currentMedications.trim().length > 0;

  async function run() {
    setBusy(true);
    setError("");
    try {
      const review = await reviewMedications({
        text,
        reportText,
        age,
        sex,
        pregnancy,
        conditions,
        allergies,
        currentMedications
      });
      setResult(review);
    } catch (err) {
      setResult(null);
      setError(err instanceof Error ? err.message : "Medication review failed.");
    } finally {
      setBusy(false);
    }
  }

  const formCard = (
    <Card>
      <CardHeader>
        <CardTitle>Encounter & patient context</CardTitle>
        <CardDescription>
          Everything you record here is weighed: the narrative and report text are parsed for concepts,
          medications and laboratory values; the fields below add the history the text does not state.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3.5">
        <Field label="Narrative / transcript">
          <Textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Crushing chest pain radiating to the left arm since 1 hour, sweaty; known diabetic and hypertensive."
          />
        </Field>

        <Field
          label="Report text (optional)"
          hint="Lab lines are read as numbers — e.g. “Troponin I: 0.05 ng/mL. Potassium 6.4 mmol/L. eGFR 22. LVEF 32%”."
        >
          <Textarea
            value={reportText}
            onChange={(e) => setReportText(e.target.value)}
            placeholder="Troponin I: 0.05 ng/mL. Creatinine 1.6 mg/dL. Potassium 5.6 mmol/L."
            className="min-h-[72px]"
          />
        </Field>

        <div className="grid grid-cols-2 gap-2">
          <Field label="Age">
            <Input
              value={age}
              onChange={(e) => setAge(e.target.value)}
              placeholder="62"
              inputMode="numeric"
              aria-label="Patient age"
            />
          </Field>
          <Field label="Sex">
            <select
              className={inputClass}
              value={sex}
              onChange={(e) => setSex(e.target.value)}
              aria-label="Patient sex"
            >
              <option value="">Not recorded</option>
              <option value="female">Female</option>
              <option value="male">Male</option>
            </select>
          </Field>
        </div>

        <Field
          label="Pregnancy status"
          hint="Left as not recorded, the review reports the gap instead of assuming — pregnancy blocks statins, ACE inhibitors and ARBs."
        >
          <select
            className={inputClass}
            value={pregnancy}
            onChange={(e) => setPregnancy(e.target.value as "" | "yes" | "no")}
            aria-label="Pregnancy status"
          >
            <option value="">Not recorded</option>
            <option value="no">Not pregnant / not applicable</option>
            <option value="yes">Pregnant or breastfeeding</option>
          </select>
        </Field>

        <Field
          label="Conditions & history"
          hint="Plain clinical phrasing works: “previous MI”, “stent 2023”, “heart failure”, “atrial fibrillation”, “asthma”, “CKD”, “peptic ulcer”, “pregnant”."
        >
          <Textarea
            value={conditions}
            onChange={(e) => setConditions(e.target.value)}
            placeholder="Hypertension, prior MI 2021, chronic kidney disease"
            className="min-h-[72px]"
          />
        </Field>

        <Field label="Allergies" hint="Separate with commas. Left empty, the review says so instead of assuming none.">
          <Input
            value={allergies}
            onChange={(e) => setAllergies(e.target.value)}
            placeholder="aspirin, sulfa"
            aria-label="Known allergies"
          />
        </Field>

        <Field label="Current medications" hint="Names or common brands — used for interaction screening.">
          <Input
            value={currentMedications}
            onChange={(e) => setCurrentMedications(e.target.value)}
            placeholder="metoprolol 25 mg, warfarin"
            aria-label="Current medications"
          />
        </Field>

        <div className="flex items-center gap-2 pt-1">
          <Button onClick={() => void run()} disabled={!canRun || busy}>
            <Pill className="h-3.5 w-3.5" strokeWidth={1.75} />
            {busy ? "Reviewing…" : "Review medications"}
          </Button>
          {result || error ? (
            <Button
              variant="ghost"
              onClick={() => {
                setResult(null);
                setError("");
              }}
            >
              Clear result
            </Button>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );

  const results = (
    <div className="space-y-4">
      {error ? (
        <Alert variant="destructive">
          <AlertTriangle />
          <AlertTitle>Review failed</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      {!result && !error ? (
        <EmptyState
          icon={Pill}
          title="No review yet"
          description="Record the encounter and patient context, then run the review. Options, blocks, interactions and every missing fact come back labelled with what triggered them."
        />
      ) : null}

      {result ? (
        <>
          <Alert variant={PATHWAY_TONE[result.pathway.urgency]}>
            <ShieldAlert />
            <AlertTitle className="flex flex-wrap items-center gap-2">
              {PATHWAY_LABEL[result.pathway.urgency]}
              {result.diagnosis ? <RiskPill level={result.diagnosis.risk_level} /> : null}
            </AlertTitle>
            <AlertDescription>
              <p>{result.pathway.statement}</p>
              {result.pathway.rationale.length ? (
                <ul className="mt-1.5 space-y-1">
                  {result.pathway.rationale.map((line) => (
                    <li key={line}>— {line}</li>
                  ))}
                </ul>
              ) : null}
              <p className="mt-1.5">
                {result.summary} {result.disclaimer}
              </p>
            </AlertDescription>
          </Alert>

          {result.indications.length ? (
            <div className="flex flex-wrap gap-1.5">
              {result.indications.map((item) => (
                <Badge key={item.name} variant="outline" title={item.triggered_by}>
                  {item.name.replace(/_/g, " ")}
                </Badge>
              ))}
            </div>
          ) : null}

          {result.missing_information.length ? (
            <Alert variant="warning">
              <Info />
              <AlertTitle>What is missing</AlertTitle>
              <AlertDescription>
                <ul className="space-y-1">
                  {result.missing_information.map((line) => (
                    <li key={line}>— {line}</li>
                  ))}
                </ul>
              </AlertDescription>
            </Alert>
          ) : null}

          {result.allergy_alerts.length ? (
            <section className="space-y-2">
              <p className="label flex items-center gap-1.5">
                <Ban className="h-3 w-3" strokeWidth={1.75} />
                Blocked by allergy
              </p>
              {result.allergy_alerts.map((alert) => (
                <Alert key={alert.drug} variant="destructive">
                  <Ban />
                  <AlertTitle>
                    {alert.drug}
                    <span className="ml-2 font-normal opacity-80">({alert.drug_class.replace(/_/g, " ")})</span>
                  </AlertTitle>
                  <AlertDescription>
                    <p>Matched reported allergy: {alert.matched_terms.join(", ")}. {alert.action}</p>
                    <p className="mt-1">Instead: {alert.alternative}</p>
                  </AlertDescription>
                </Alert>
              ))}
            </section>
          ) : null}

          {result.recommendations.length ? (
            <section className="space-y-2">
              <p className="label flex items-center gap-1.5">
                <CheckCircle2 className="h-3 w-3" strokeWidth={1.75} />
                Options for this patient ({result.recommendations.length})
              </p>
              {result.recommendations.map((rec) => (
                <Card key={rec.drug}>
                  <CardContent className="p-4">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="num text-2xs text-faint">#{rec.priority}</span>
                      <p className="text-sm font-semibold text-fg">{rec.drug}</p>
                      <Badge variant={RECOMMENDATION_TONE[rec.status]} dot>
                        {RECOMMENDATION_LABEL[rec.status]}
                      </Badge>
                      <Badge variant="outline">{rec.drug_class.replace(/_/g, " ")}</Badge>
                    </div>

                    {rec.triggered_by.length ? (
                      <ul className="mt-2 space-y-1">
                        {rec.triggered_by.map((reason) => (
                          <li key={reason} className="text-2xs leading-relaxed text-muted">
                            Because: {reason}
                          </li>
                        ))}
                      </ul>
                    ) : null}

                    <p className="mt-2 text-xs leading-relaxed text-fg">{rec.dose_note}</p>

                    {rec.review_flags.length ? (
                      <ul className="mt-2 space-y-1.5">
                        {rec.review_flags.map((flag) => (
                          <li
                            key={flag}
                            className="flex gap-2 rounded-md border border-warn/30 bg-warn/[0.06] px-2.5 py-1.5 text-2xs leading-relaxed text-warn-strong"
                          >
                            <AlertTriangle className="mt-px h-3 w-3 shrink-0" strokeWidth={1.75} />
                            {flag}
                          </li>
                        ))}
                      </ul>
                    ) : null}

                    {rec.monitoring.length ? (
                      <p className="mt-2 text-2xs leading-relaxed text-muted">
                        <span className="font-medium text-fg">Monitor:</span> {rec.monitoring.join(" · ")}
                      </p>
                    ) : null}

                    <p className="mt-2 text-2xs italic leading-relaxed text-faint">{rec.evidence}</p>
                    <p className="mt-1 text-2xs leading-relaxed text-faint">{rec.action}</p>
                  </CardContent>
                </Card>
              ))}
            </section>
          ) : null}

          {result.contraindicated.length ? (
            <section className="space-y-2">
              <p className="label flex items-center gap-1.5">
                <ShieldAlert className="h-3 w-3" strokeWidth={1.75} />
                Blocked or needs review ({result.contraindicated.length})
              </p>
              {result.contraindicated.map((item) => (
                <Alert
                  key={item.drug}
                  variant={item.severity === "absolute" ? "destructive" : "warning"}
                >
                  <ShieldAlert />
                  <AlertTitle className="flex flex-wrap items-center gap-2">
                    {item.drug}
                    <Badge variant={item.severity === "absolute" ? "destructive" : "warn"}>
                      {item.severity === "absolute" ? "Do not use" : "Review first"}
                    </Badge>
                    {item.already_documented ? <Badge variant="secondary">already documented</Badge> : null}
                  </AlertTitle>
                  <AlertDescription>
                    <ul className="space-y-1.5">
                      {item.blocks.map((block) => (
                        <li key={`${block.kind}-${block.trigger}`}>
                          <span className="font-medium">{BLOCK_KIND_LABEL[block.kind] ?? block.kind}:</span>{" "}
                          {block.note}
                        </li>
                      ))}
                    </ul>
                    <p className="mt-1.5">{item.note}</p>
                    <p className="mt-1 italic opacity-80">{item.evidence}</p>
                  </AlertDescription>
                </Alert>
              ))}
            </section>
          ) : null}

          {result.interaction_alerts.length ? (
            <section className="space-y-2">
              <p className="label flex items-center gap-1.5">
                <AlertTriangle className="h-3 w-3" strokeWidth={1.75} />
                Interactions ({result.interaction_alerts.length})
              </p>
              {result.interaction_alerts.map((alert) => (
                <Alert
                  key={alert.pair.join("-")}
                  variant={alert.severity === "major" ? "destructive" : "warning"}
                >
                  <AlertTriangle />
                  <AlertTitle className="flex flex-wrap items-center gap-2">
                    {alert.pair.map((side) => side.replace(/_/g, " ")).join(" + ")}
                    <Badge variant={alert.severity === "major" ? "destructive" : "warn"}>
                      {alert.severity}
                    </Badge>
                  </AlertTitle>
                  <AlertDescription>
                    <p>{alert.note}</p>
                    <p className="mt-1">{alert.action}</p>
                    {alert.drugs.length ? (
                      <p className="mt-1 opacity-80">Involved here: {alert.drugs.map((d) => d.replace(/_/g, " ")).join(", ")}.</p>
                    ) : null}
                  </AlertDescription>
                </Alert>
              ))}
            </section>
          ) : null}

          {result.monitoring_plan.length ? (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-sm">
                  <FlaskConical className="h-4 w-4 text-accent" strokeWidth={1.75} />
                  Monitoring plan
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="space-y-1.5">
                  {result.monitoring_plan.map((line) => (
                    <li key={line} className="text-xs leading-relaxed text-muted">
                      — {line}
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          ) : null}

          {result.patient_profile.conditions.length ||
          result.patient_profile.current_medication_classes.length ? (
            <Card>
              <CardHeader>
                <CardTitle className="text-sm">What the analysis used</CardTitle>
                <CardDescription>
                  Only these captured facts drove the review — nothing was inferred beyond them.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-2">
                <div className="flex flex-wrap gap-1.5">
                  {result.patient_profile.conditions.map((tag) => (
                    <Badge key={tag} variant="outline">
                      {tag.replace(/_/g, " ")}
                    </Badge>
                  ))}
                </div>
                {result.patient_profile.current_medication_classes.length ? (
                  <p className="text-2xs text-muted">
                    Documented classes: {result.patient_profile.current_medication_classes.join(", ").replace(/_/g, " ")}
                  </p>
                ) : null}
                {Object.keys(result.patient_profile.labs_considered).length ? (
                  <p className="num text-2xs text-muted">
                    Labs applied:{" "}
                    {Object.entries(result.patient_profile.labs_considered)
                      .map(([key, value]) => `${key.replace(/_/g, " ")} ${value}`)
                      .join(" · ")}
                  </p>
                ) : null}
              </CardContent>
            </Card>
          ) : null}
        </>
      ) : null}
    </div>
  );

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Workspace"
        icon={Pill}
        title="Medication review"
        description="Medication options and safety checks for one encounter, weighed against the presentation, conditions and history, allergies, current medications and laboratory values. Options, blocks and interactions each name the fact that triggered them."
      />

      <Alert variant="default">
        <Sparkles />
        <AlertTitle>Decision support, not a prescription</AlertTitle>
        <AlertDescription>
          PulseIQ suggests options and flags unsafe ones; the clinician selects, doses and documents.
          Emergency presentations are escalated regardless of what the medication list says, and nothing on
          this page is stored.
        </AlertDescription>
      </Alert>

      <div className={cn("grid gap-4", "lg:grid-cols-[minmax(0,1fr)_minmax(0,1.35fr)]")}>
        <div>{formCard}</div>
        <div>{results}</div>
      </div>
    </div>
  );
}
