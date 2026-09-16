import type { BodyPainInsight, BodyRegionId } from "@/lib/bodyPain";

type Zone = {
  region: BodyRegionId;
  cx: number;
  cy: number;
  rx: number;
  ry: number;
};

const FRONT_ZONES: Zone[] = [
  { region: "head", cx: 65, cy: 24, rx: 8, ry: 8 },
  { region: "neck", cx: 65, cy: 40, rx: 6, ry: 5 },
  { region: "chest", cx: 65, cy: 62, rx: 16, ry: 13 },
  { region: "left_arm", cx: 39, cy: 71, rx: 7, ry: 16 },
  { region: "right_arm", cx: 91, cy: 71, rx: 7, ry: 16 },
  { region: "upper_abdomen", cx: 65, cy: 84, rx: 13, ry: 9 },
  { region: "lower_abdomen", cx: 65, cy: 99, rx: 12, ry: 8 },
  { region: "left_leg", cx: 56, cy: 131, rx: 7, ry: 19 },
  { region: "right_leg", cx: 74, cy: 131, rx: 7, ry: 19 },
];

const BACK_ZONES: Zone[] = [
  { region: "head", cx: 164, cy: 24, rx: 8, ry: 8 },
  { region: "neck", cx: 164, cy: 40, rx: 6, ry: 5 },
  { region: "back", cx: 164, cy: 68, rx: 15, ry: 18 },
  { region: "left_arm", cx: 138, cy: 71, rx: 7, ry: 16 },
  { region: "right_arm", cx: 190, cy: 71, rx: 7, ry: 16 },
  { region: "left_leg", cx: 155, cy: 131, rx: 7, ry: 19 },
  { region: "right_leg", cx: 173, cy: 131, rx: 7, ry: 19 },
];

function isActive(activeRegions: Set<BodyRegionId>, region: BodyRegionId) {
  return activeRegions.has(region);
}

function bodyFill(active: boolean) {
  return active ? "#f43f5e" : "#334155";
}

function bodyOpacity(active: boolean) {
  return active ? 0.95 : 0.4;
}

function Silhouette({ x, front }: { x: number; front: boolean }) {
  return (
    <g transform={`translate(${x},0)`}>
      <ellipse cx="0" cy="24" rx="10" ry="10" fill="#475569" fillOpacity="0.35" />
      <rect x="-7" y="33" width="14" height="14" rx="6" fill="#475569" fillOpacity="0.35" />
      <rect x="-17" y="45" width="34" height="44" rx="14" fill="#475569" fillOpacity="0.35" />
      <rect x="-31" y="52" width="12" height="50" rx="7" fill="#475569" fillOpacity="0.35" />
      <rect x="19" y="52" width="12" height="50" rx="7" fill="#475569" fillOpacity="0.35" />
      <rect x="-13" y="89" width="12" height="66" rx="8" fill="#475569" fillOpacity="0.35" />
      <rect x="1" y="89" width="12" height="66" rx="8" fill="#475569" fillOpacity="0.35" />
      {!front ? <ellipse cx="0" cy="66" rx="16" ry="15" fill="#475569" fillOpacity="0.35" /> : null}
    </g>
  );
}

export function BodyPainDiagram({ insights }: { insights: BodyPainInsight[] }) {
  const active = new Set(insights.map((item) => item.region));

  return (
    <div className="rounded-xl border border-slate-800 bg-gradient-to-b from-slate-950/70 to-slate-900/40 p-3">
      <svg viewBox="0 0 230 170" className="mx-auto h-[360px] w-full max-w-[560px]">
        <Silhouette x={65} front />
        <Silhouette x={164} front={false} />

        {FRONT_ZONES.map((zone) => {
          const on = isActive(active, zone.region);
          return (
            <ellipse
              key={`front-${zone.region}`}
              cx={zone.cx}
              cy={zone.cy}
              rx={zone.rx}
              ry={zone.ry}
              fill={bodyFill(on)}
              fillOpacity={bodyOpacity(on)}
              stroke={on ? "#dc2626" : "transparent"}
              strokeWidth={on ? 1.2 : 0}
            />
          );
        })}

        {BACK_ZONES.map((zone) => {
          const on = isActive(active, zone.region);
          return (
            <ellipse
              key={`back-${zone.region}`}
              cx={zone.cx}
              cy={zone.cy}
              rx={zone.rx}
              ry={zone.ry}
              fill={bodyFill(on)}
              fillOpacity={bodyOpacity(on)}
              stroke={on ? "#dc2626" : "transparent"}
              strokeWidth={on ? 1.2 : 0}
            />
          );
        })}

        <text x="48" y="165" fontSize="8" fill="#64748b">Front</text>
        <text x="148" y="165" fontSize="8" fill="#64748b">Back</text>
      </svg>

      <p className="mt-1 text-center text-xs text-slate-500">
        Red zones indicate pain regions detected from transcript/report context.
      </p>
    </div>
  );
}
