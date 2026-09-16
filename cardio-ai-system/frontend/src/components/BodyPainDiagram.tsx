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
  { region: "right_leg", cx: 74, cy: 131, rx: 7, ry: 19 }
];

const BACK_ZONES: Zone[] = [
  { region: "head", cx: 164, cy: 24, rx: 8, ry: 8 },
  { region: "neck", cx: 164, cy: 40, rx: 6, ry: 5 },
  { region: "back", cx: 164, cy: 68, rx: 15, ry: 18 },
  { region: "left_arm", cx: 138, cy: 71, rx: 7, ry: 16 },
  { region: "right_arm", cx: 190, cy: 71, rx: 7, ry: 16 },
  { region: "left_leg", cx: 155, cy: 131, rx: 7, ry: 19 },
  { region: "right_leg", cx: 173, cy: 131, rx: 7, ry: 19 }
];

const SILHOUETTE = "#2B3038";
const ZONE_IDLE = "#3A404A";
const ZONE_ACTIVE = "#F2555A";

function Silhouette({ x, front }: { x: number; front: boolean }) {
  return (
    <g transform={`translate(${x},0)`} fill={SILHOUETTE} fillOpacity="0.85">
      <ellipse cx="0" cy="24" rx="10" ry="10" />
      <rect x="-7" y="33" width="14" height="14" rx="6" />
      <rect x="-17" y="45" width="34" height="44" rx="14" />
      <rect x="-31" y="52" width="12" height="50" rx="7" />
      <rect x="19" y="52" width="12" height="50" rx="7" />
      <rect x="-13" y="89" width="12" height="66" rx="8" />
      <rect x="1" y="89" width="12" height="66" rx="8" />
      {!front ? <ellipse cx="0" cy="66" rx="16" ry="15" /> : null}
    </g>
  );
}

function ZoneEllipses({ zones, active }: { zones: Zone[]; active: Set<BodyRegionId> }) {
  return (
    <>
      {zones.map((zone) => {
        const on = active.has(zone.region);
        return (
          <ellipse
            key={zone.region}
            cx={zone.cx}
            cy={zone.cy}
            rx={zone.rx}
            ry={zone.ry}
            fill={on ? ZONE_ACTIVE : ZONE_IDLE}
            fillOpacity={on ? 0.92 : 0.45}
            stroke={on ? "#FF9A9D" : "transparent"}
            strokeWidth={on ? 1 : 0}
            className="transition-[fill,fill-opacity] duration-300"
          />
        );
      })}
    </>
  );
}

export function BodyPainDiagram({ insights }: { insights: BodyPainInsight[] }) {
  const active = new Set(insights.map((item) => item.region));

  return (
    <div>
      <div className="rounded-lg border border-line bg-inset p-3">
        <svg viewBox="0 0 230 172" className="mx-auto h-[330px] w-full max-w-[520px]">
          <Silhouette x={65} front />
          <Silhouette x={164} front={false} />
          <ZoneEllipses zones={FRONT_ZONES} active={active} />
          <ZoneEllipses zones={BACK_ZONES} active={active} />
          <text x="47" y="168" fontSize="8" fill="#6B7280" fontFamily="ui-monospace, monospace">
            FRONT
          </text>
          <text x="150" y="168" fontSize="8" fill="#6B7280" fontFamily="ui-monospace, monospace">
            BACK
          </text>
        </svg>
      </div>

      <div className="mt-2.5 flex items-center justify-between gap-3">
        <span className="flex items-center gap-2 text-2xs text-faint">
          <span className="h-2 w-2 rounded-sm bg-[#3A404A]" />
          Unexamined
          <span className="ml-2 h-2 w-2 rounded-sm bg-[#F2555A]" />
          Reported
        </span>
        <span className="num text-2xs text-faint">{active.size} region{active.size === 1 ? "" : "s"}</span>
      </div>
    </div>
  );
}
