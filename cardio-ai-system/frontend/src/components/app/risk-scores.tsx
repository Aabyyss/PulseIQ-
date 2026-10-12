import { Badge } from "@/components/ui/badge";
import type { RiskScoreComponent, RiskScores } from "@/lib/types";
import { cn } from "@/lib/utils";

const BAND_VARIANT = {
  low: "ok",
  intermediate: "warn",
  high: "destructive"
} as const;

/** One score's one-line reading: total and band, or what it is still missing. */
function scoreLine(
  label: string,
  score: RiskScores["heart"] | RiskScores["grace"],
  extra?: string
) {
  const band = score.band ?? null;
  const total = score.score !== null ? `${score.score}/${score.max_score}` : `${score.known_points}/${score.max_score} known`;
  return {
    label,
    total,
    band,
    extra,
    missing: score.missing,
    complete: score.complete,
    components: score.components,
    source: score.source
  };
}

export function RiskScoresStrip({ scores, className }: { scores?: RiskScores | null; className?: string }) {
  if (!scores) return null;
  const stroke = scores.cha2ds2_vasc;
  const lines = [
    scoreLine("HEART", scores.heart, scores.heart.mace_risk_6_weeks ? `6-week MACE ${scores.heart.mace_risk_6_weeks}` : undefined),
    scoreLine(
      "GRACE",
      scores.grace,
      scores.grace.in_hospital_mortality?.percent != null
        ? `in-hospital mortality ${scores.grace.in_hospital_mortality.percent}%${scores.grace.in_hospital_mortality.interpolated ? " (interpolated)" : ""}`
        : undefined
    ),
    {
      label: "CHA₂DS₂-VASc",
      total: stroke.score !== null ? `${stroke.score}/${stroke.max_score}` : `${stroke.known_points}/${stroke.max_score} known`,
      band: null,
      extra:
        stroke.annual_stroke_risk_pct !== null
          ? `${stroke.annual_stroke_risk_pct}%/year · anticoagulation: ${stroke.anticoagulation_tier}`
          : undefined,
      missing: stroke.missing,
      complete: stroke.complete,
      components: stroke.components,
      source: stroke.source
    }
  ];

  return (
    <div className={cn("space-y-1.5", className)}>
      {lines.map((line) => (
        <div key={line.label} className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
          <span className="text-2xs font-medium text-fg">{line.label}</span>
          <Badge variant={line.complete && line.band ? BAND_VARIANT[line.band] : "secondary"}>
            {line.total}
            {line.complete && line.band ? ` · ${line.band}` : ""}
          </Badge>
          {line.extra ? <span className="text-2xs text-muted">{line.extra}</span> : null}
          {!line.complete ? (
            <span className="text-2xs italic text-faint">
              needs {line.missing.join(", ")}
            </span>
          ) : null}
        </div>
      ))}
      <p className="text-2xs italic leading-relaxed text-faint">
        Deterministic scores from the captured facts — the clinician decides; every point is traceable to its input.
      </p>
    </div>
  );
}

/** Full breakdown, for the medication workspace where there is room to explain. */
export function RiskScoresDetail({ scores }: { scores?: RiskScores | null }) {
  if (!scores) return null;
  const scoresList: { label: string; components: Record<string, RiskScoreComponent>; missing: string[]; source: string; extra?: string }[] = [
    {
      label: `HEART ${scores.heart.score ?? "—"}/${scores.heart.max_score}`,
      components: scores.heart.components,
      missing: scores.heart.missing,
      source: scores.heart.source,
      extra: scores.heart.mace_risk_6_weeks ? `6-week MACE ${scores.heart.mace_risk_6_weeks}` : undefined
    },
    {
      label: `GRACE ${scores.grace.score ?? "—"}`,
      components: scores.grace.components,
      missing: scores.grace.missing,
      source: scores.grace.source,
      extra: scores.grace.note
    },
    {
      label: `CHA₂DS₂-VASc ${scores.cha2ds2_vasc.score ?? "—"}/${scores.cha2ds2_vasc.max_score}`,
      components: scores.cha2ds2_vasc.components,
      missing: scores.cha2ds2_vasc.missing,
      source: scores.cha2ds2_vasc.source,
      extra: scores.cha2ds2_vasc.applies_to
    }
  ];

  return (
    <div className="space-y-3">
      {scoresList.map((score) => (
        <div key={score.label}>
          <p className="label">{score.label}</p>
          {score.extra ? <p className="mt-0.5 text-2xs text-muted">{score.extra}</p> : null}
          <ul className="mt-1.5 space-y-1">
            {Object.entries(score.components).map(([name, component]) => (
              <li key={name} className="flex items-baseline gap-2 text-2xs">
                <span className="w-6 shrink-0 font-medium text-fg">{component.points}</span>
                <span className="text-muted">
                  {name.replace(/_/g, " ")} — {component.detail}
                </span>
              </li>
            ))}
          </ul>
          {score.missing.length ? (
            <p className="mt-1 text-2xs italic text-faint">
              Not scored (needs {score.missing.join(", ")}).
            </p>
          ) : null}
          <p className="mt-1 text-2xs italic text-faint">{score.source}</p>
        </div>
      ))}
    </div>
  );
}
