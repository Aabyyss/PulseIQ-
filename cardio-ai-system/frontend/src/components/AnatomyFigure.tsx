import { useState } from "react";
import { Heart } from "lucide-react";
import type { BodyRegionId } from "@/lib/bodyPain";
import { HOTSPOTS, VARIANT_LABELS, type AnatomyVariant, type Hotspot } from "@/lib/anatomy";

/*
 * Anatomical front figure in a 100×190 space, painted deep→superficial so
 * organs sit inside the ribcage and the vessel tree overlays everything:
 *   1. body outline (translucent skin)
 *   2. skeleton (skull, spine, ribs, pelvis, limb bones)
 *   3. organs (brain, trachea, lungs, heart, liver, stomach, kidneys,
 *      intestines, bladder — organs carry the reference-poster look)
 *   4. vessel tree: aorta red / vena cava blue with limb branches
 * Labels use poster-style leader lines on both sides.
 */

const C = {
  bone: "#E7D9BC",
  boneEdge: "#B7A57E",
  lung: "#C98B8B",
  lungEdge: "#9E6262",
  liver: "#8E4A3B",
  stomach: "#C77B4F",
  gut: "#D99A94",
  gutEdge: "#A96560",
  kidney: "#9A5A50",
  bladder: "#B7A054",
  brain: "#C89A9A",
  artery: "#C0392B",
  vein: "#2E5E9E",
  heartMuscle: "#A93226",
  leader: "#6B7280"
};

type LabelSpec = { text: string; side: "left" | "right"; y: number; targetY: number; targetX?: number };

const BODY_LABELS: LabelSpec[] = [
  { text: "Brain", side: "left", y: 12, targetY: 13, targetX: 43 },
  { text: "Trachea", side: "left", y: 33, targetY: 35, targetX: 44 },
  { text: "Vena cava", side: "left", y: 44, targetY: 46, targetX: 45 },
  { text: "Right lung", side: "left", y: 52, targetY: 50, targetX: 38 },
  { text: "Heart", side: "left", y: 60, targetY: 56, targetX: 44 },
  { text: "Liver", side: "left", y: 70, targetY: 69, targetX: 39 },
  { text: "Right kidney", side: "left", y: 79, targetY: 79, targetX: 40 },
  { text: "Ascending colon", side: "left", y: 88, targetY: 88, targetX: 40.5 },
  { text: "Small intestine", side: "left", y: 97, targetY: 96, targetX: 44 },
  { text: "Femur", side: "left", y: 124, targetY: 122, targetX: 41.5 },
  { text: "Tibia / fibula", side: "left", y: 146, targetY: 145, targetX: 41.8 },
  { text: "Left lung", side: "right", y: 47, targetY: 49, targetX: 62 },
  { text: "Aorta", side: "right", y: 58, targetY: 60, targetX: 55.5 },
  { text: "Stomach", side: "right", y: 68, targetY: 70, targetX: 62.5 },
  { text: "Spleen", side: "right", y: 76, targetY: 75.5, targetX: 65.3 },
  { text: "Left kidney", side: "right", y: 83, targetY: 79.5, targetX: 60.3 },
  { text: "Transverse colon", side: "right", y: 91, targetY: 87, targetX: 58.5 },
  { text: "Urinary bladder", side: "right", y: 102, targetY: 103, targetX: 53.5 }
];

function ArrowMarker({ id }: { id: string }) {
  return (
    <marker id={id} viewBox="0 0 8 8" refX="7" refY="4" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
      <path d="M0 0 L8 4 L0 8 Z" fill="#6B7280" />
    </marker>
  );
}

/**
 * Poster-style callouts: text sits fully outside the figure, each label
 * shoots an arrowed leader line at the structure it names. Dark text so
 * it reads over the pale canvas at a glance.
 */
function LeaderLabels({ labels, markerId }: { labels: LabelSpec[]; markerId: string }) {
  return (
    <g fontSize="4.6" fontFamily="ui-monospace, monospace" fill="#374151">
      <defs>
        <ArrowMarker id={markerId} />
      </defs>
      {labels.map((l) => {
        // Poster discipline: text in the margin, arrow starts at the text's
        // inner edge and lands on the structure — never swept across the body.
        const textX = l.side === "left" ? 19 : 81;
        const leadFrom = l.side === "left" ? 20.5 : 79.5;
        const targetX = Math.min(Math.max(l.targetX ?? 34, leadFrom), leadFrom + 24);
        return (
          <g key={l.text + l.side}>
            <text x={textX} y={l.y} textAnchor={l.side === "left" ? "end" : "start"}>
              {l.text}
            </text>
            <line x1={leadFrom} y1={l.y - 1.4} x2={targetX} y2={l.targetY} stroke="#6B7280" strokeWidth="0.4" markerEnd={`url(#${markerId})`} />
          </g>
        );
      })}
    </g>
  );
}

function Skeleton() {
  return (
    <g fill={C.bone} stroke={C.boneEdge} strokeWidth="0.3">
      {/* skull */}
      <ellipse cx="50" cy="13.5" rx="8.2" ry="9.2" fillOpacity="0.9" />
      <path d="M43.5 17 Q50 24.5 56.5 17 L54.5 22.5 Q50 25.5 45.5 22.5 Z" fillOpacity="0.75" />
      {/* spine */}
      {Array.from({ length: 16 }).map((_, i) => (
        <rect key={i} x="48.6" y={31 + i * 4.4} width="2.8" height="3.2" rx="0.7" fillOpacity="0.92" />
      ))}
      {/* clavicles */}
      <path d="M38 39.5 Q44 37 49.4 39" fill="none" strokeWidth="1.4" stroke={C.bone} strokeLinecap="round" />
      <path d="M62 39.5 Q56 37 50.6 39" fill="none" strokeWidth="1.4" stroke={C.bone} strokeLinecap="round" />
      {/* sternum */}
      <path d="M48.8 40.5 h2.4 v11.5 h-2.4 Z" fillOpacity="0.95" />
      {/* ribs */}
      {[0, 1, 2, 3, 4, 5].map((i) => (
        <g key={i} fill="none" stroke={C.bone} strokeWidth="1" opacity="0.9">
          <path d={`M48.6 ${42 + i * 2.6} Q${39 - i * 0.6} ${43.5 + i * 2.8} 38 ${40.5 + i * 3.2}`} />
          <path d={`M51.4 ${42 + i * 2.6} Q${61 + i * 0.6} ${43.5 + i * 2.8} 62 ${40.5 + i * 3.2}`} />
        </g>
      ))}
      {/* arm bones: humerus, radius+ulna */}
      {[31, 69].map((x) => (
        <g key={x}>
          <rect x={x - 1} y="44" width="2" height="23" rx="1" fillOpacity="0.8" />
          <rect x={x - 1.1} y="68" width="0.9" height="18" rx="0.45" fillOpacity="0.7" />
          <rect x={x + 0.3} y="68" width="0.9" height="18" rx="0.45" fillOpacity="0.7" />
          {/* finger rays */}
          <path d={`M${x - 2} 86 l-1 5 M${x - 0.6} 86.5 l0 5.5 M${x + 0.8} 86.5 l0.6 5 M${x + 2} 86 l1.4 4.5`} fill="none" strokeWidth="0.7" stroke={C.bone} />
        </g>
      ))}
      {/* pelvis with a crotch notch so the two legs read as two */}
      <path d="M39.5 95 Q50 90.5 60.5 95 Q59 103.5 54.5 105.5 L50 113 L45.5 105.5 Q41 103.5 39.5 95 Z" fillOpacity="0.92" />
      {/* femur / patella / tibia+fibula — centred in each thigh */}
      <rect x="37.3" y="105" width="2.4" height="24" rx="1.2" fillOpacity="0.85" />
      <rect x="60.3" y="105" width="2.4" height="24" rx="1.2" fillOpacity="0.85" />
      <circle cx="38.5" cy="130.5" r="1.5" fillOpacity="0.9" />
      <circle cx="61.5" cy="130.5" r="1.5" fillOpacity="0.9" />
      <rect x="37.7" y="132" width="1.7" height="26" rx="0.85" fillOpacity="0.75" />
      <rect x="60.6" y="132" width="1.7" height="26" rx="0.85" fillOpacity="0.75" />
      <rect x="40.2" y="132" width="0.8" height="24" rx="0.4" fillOpacity="0.6" />
      <rect x="59" y="132" width="0.8" height="24" rx="0.4" fillOpacity="0.6" />
      {/* feet rays, one set per foot */}
      <path d="M30.5 162 l-2 6 M33 162.5 l-0.6 6.5 M35.5 162.5 l1 6 M37.5 162 l2 5.4" fill="none" strokeWidth="0.7" stroke={C.bone} />
      <path d="M60.5 162 l-2 5.4 M62.5 162.5 l-1 6 M65 162.5 l0.6 6.5 M67.5 162 l2 6" fill="none" strokeWidth="0.7" stroke={C.bone} />
    </g>
  );
}

function Organs({ variant }: { variant: AnatomyVariant }) {
  const female = variant === "female";
  return (
    <g stroke="#00000022" strokeWidth="0.3">
      {/* brain */}
      <path d="M44 9 Q50 4.5 56 9 Q58.5 12 56.5 15.5 Q50 18.5 43.5 15.5 Q41.5 12 44 9 Z" fill={C.brain} />
      <path d="M50 5.5 L50 17.5 M45 7.5 Q46.5 11 45 14.5 M55 7.5 Q53.5 11 55 14.5" fill="none" stroke="#8A5F5F" strokeWidth="0.4" />
      {/* trachea + bronchi */}
      <path d="M49 31 L49 40 M49 40 L45.5 44 M49 40 L52.5 44" fill="none" stroke="#7C8794" strokeWidth="1.6" strokeLinecap="round" />
      {/* lungs */}
      <path d="M46.5 41 Q39 42 37.5 49 Q36.5 56 40 61.5 Q44 63.5 46 59 Q47 50 46.5 41 Z" fill={C.lung} />
      <path d="M53.5 41 Q61 42 62.5 49 Q63.5 56 60 61.5 Q56 63.5 54 59 Q53 50 53.5 41 Z" fill={C.lung} />
      {/* heart — slightly left-of-midline */}
      <path d="M47.5 47 Q43.5 47.5 43.5 52.5 Q43.5 58 47.5 61.5 Q49.5 63.3 51 63.5 Q52.5 63 54.5 61 Q57.5 57.5 57 52.5 Q56.5 48 52.5 47.3 Q49.8 47 48.8 48.6 Q48.2 47.2 47.5 47 Z" fill={C.heartMuscle} />
      {/* liver — right side under the lung */}
      <path d="M38.5 65.5 Q45 62.5 52 64 Q58 65.5 60.5 68.5 Q54 72 45 71.5 Q39.5 70.5 38.5 65.5 Z" fill={C.liver} />
      {/* stomach — left, tucked under the lung */}
      <path d="M55 66 Q60.5 65.5 62 69.5 Q63 73.5 59.5 75.5 Q55.5 76.5 54 72.5 Q53 68.5 55 66 Z" fill={C.stomach} />
      {/* spleen */}
      <ellipse cx="63.2" cy="75.5" rx="2.1" ry="3" fill="#7E5A72" />
      {/* kidneys */}
      <ellipse cx="42" cy="79" rx="2.3" ry="3.6" fill={C.kidney} />
      <ellipse cx="58" cy="79" rx="2.3" ry="3.6" fill={C.kidney} />
      {/* intestines: transverse colon frame + coiled small bowel */}
      <path d="M41.5 85.5 Q50 82.5 58.5 85.5" fill="none" stroke={C.gutEdge} strokeWidth="3" strokeLinecap="round" opacity="0.85" />
      <path d="M41.5 85.5 Q39.5 90 41.5 94.5 M58.5 85.5 Q60.5 90 58.5 94.5" fill="none" stroke={C.gutEdge} strokeWidth="3" strokeLinecap="round" opacity="0.85" />
      <path d="M43.5 95 Q46 92.5 48.5 95.5 Q51 98.5 53.5 95 Q56 92 58.5 95 Q56 99.5 51.5 99.8 Q46 100.2 43.5 95 Z" fill={C.gut} />
      <path d="M44 96.5 Q47 94.5 49.5 96.5 M50.5 97.5 Q53 95 55.5 97" fill="none" stroke={C.gutEdge} strokeWidth="0.5" />
      {/* urinary bladder — sits above the pubic arch, female pelvis slightly lower */}
      <path d="M46.5 100.5 Q50 99 53.5 100.5 Q53.3 104.8 50 105.6 Q46.7 104.8 46.5 100.5 Z" fill={C.bladder} transform={female ? "translate(0,0.8)" : undefined} />
      {/* male/female reproductive markers (poster style, subtle) */}
      {female ? (
        <path d="M46 98.5 Q50 96.8 54 98.5" fill="none" stroke="#B06A8A" strokeWidth="1.4" strokeLinecap="round" />
      ) : null}
    </g>
  );
}

function Vessels() {
  return (
    <g fill="none" strokeLinecap="round">
      {/* aortic arch + descending aorta */}
      <path d="M47 46 Q47.5 40.5 51 40 Q54.5 40.5 55 44 L55.5 48 Q56 60 55 72 Q54.5 82 53.5 92" stroke={C.artery} strokeWidth="1.5" />
      {/* subclavian → brachial → radial (both arms) */}
      <path d="M47.5 42 Q40 42.5 35.5 45 Q31 48 30 52 Q29 60 30.5 68 Q31.5 74 31 80" stroke={C.artery} strokeWidth="0.9" />
      <path d="M54.5 42 Q62 42.5 66.5 45 Q71 48 70 52 Q71 60 69.5 68 Q68.5 74 69 80" stroke={C.artery} strokeWidth="0.9" />
      {/* carotids */}
      <path d="M47.5 40 L46.5 31" stroke={C.artery} strokeWidth="0.8" />
      <path d="M52.5 40 L53.5 31" stroke={C.artery} strokeWidth="0.8" />
      {/* iliac → femoral → popliteal, one tree per leg */}
      <path d="M53 92 Q52 100 55 106 Q59 112 60.5 122 Q61.5 138 62 150" stroke={C.artery} strokeWidth="1" />
      <path d="M47 92 Q48 100 45 106 Q41 112 39.5 122 Q38.5 138 38 150" stroke={C.artery} strokeWidth="1" />
      {/* superior + inferior vena cava */}
      <path d="M44 40 Q44.5 34 46 30" stroke={C.vein} strokeWidth="1.6" />
      <path d="M44.5 44 Q45.5 56 45.5 68 Q45.5 80 46.5 92" stroke={C.vein} strokeWidth="1.6" />
      {/* jugulars */}
      <path d="M44 40 Q42.5 35 43 30" stroke={C.vein} strokeWidth="0.9" />
      <path d="M56 40 Q57.5 35 57 30" stroke={C.vein} strokeWidth="0.9" />
      {/* brachial veins */}
      <path d="M33.5 50 Q31.5 60 33 70 Q34 76 33.5 82" stroke={C.vein} strokeWidth="0.8" />
      <path d="M66.5 50 Q68.5 60 67 70 Q66 76 66.5 82" stroke={C.vein} strokeWidth="0.8" />
      {/* great saphenous, one per leg */}
      <path d="M41 116 Q39.5 130 41.5 144 Q42.5 156 42 166" stroke={C.vein} strokeWidth="0.9" />
      <path d="M59 116 Q60.5 130 58.5 144 Q57.5 156 58 166" stroke={C.vein} strokeWidth="0.9" />
      {/* portal fan over the liver */}
      <path d="M46 66 Q49 64.5 52 65.5" stroke={C.vein} strokeWidth="0.7" opacity="0.8" />
    </g>
  );
}

function BodyOutline({ variant }: { variant: AnatomyVariant }) {
  const shoulder = variant === "male" ? 26 : variant === "female" ? 21 : 23.5;
  const bust = variant === "female" ? -1.5 : 0;
  const waist = variant === "female" ? 10.5 : variant === "male" ? 13.5 : 12;
  const hip = variant === "female" ? 17.5 : variant === "male" ? 15.5 : 16.5;
  return (
    <path
      d={[
        "M50 3.5 Q58 3.5 58.5 13 Q58.5 20 55 23.5 L55 30",
        `L${50 + shoulder * 0.55} 34.5`,
        `Q${50 + shoulder + 2} 37 ${50 + shoulder + 1} 47`,
        `Q${50 + shoulder} 60 ${50 + shoulder - 2} 72`,
        `Q${50 + shoulder - 3.5} 78 ${50 + shoulder - 4.5} 84`,
        `L${50 + shoulder - 6.5} 88 Q${50 + shoulder - 7.5} 90.5 ${50 + shoulder - 9} 88.5`,
        `Q${50 + shoulder - 9.5} 84 ${50 + shoulder - 8.5} 76`,
        `Q${50 + shoulder - 8} 66 ${50 + shoulder - 6.5} 56`,
        `Q${50 + shoulder - 5} 48 ${50 + shoulder - 8} 43.5`,
        `L${50 + waist + 2} ${52 + bust}`,
        `Q${50 + waist} ${70 + bust} ${50 + hip} 90`,
        `Q${50 + hip + 1} 98 ${50 + hip - 1} 103`,
        // right leg: outer line down, outward foot, inner line up to the crotch
        `L${50 + hip - 1} 104 L${50 + hip} 132 Q${50 + hip + 1} 152 ${50 + hip + 1.5} 170.5`,
        `L${50 + hip + 6} 172.5 Q${50 + hip + 7.5} 176 ${50 + hip + 6} 180 L${50 + hip - 4} 180 L${50 + hip - 3.5} 172`,
        `Q${50 + hip - 5} 160 ${50 + hip - 7} 145 L${50 + hip - 6.5} 124 Q${50 + hip - 6} 116 50 113`,
        // left leg: crotch, inner line down, outward foot, outer line up
        `L${50 - hip + 6.5} 124 Q${50 - hip + 7} 145 ${50 - hip + 5} 160 L${50 - hip + 3.5} 172`,
        `L${50 - hip + 4} 180 L${50 - hip - 6} 180 Q${50 - hip - 7.5} 176 ${50 - hip - 6} 172.5 L${50 - hip - 1.5} 170.5`,
        `Q${50 - hip - 2.5} 152 ${50 - hip - 1} 132 L${50 - hip + 0.5} 112 L${50 - hip + 1} 104`,
        `Q${50 - hip - 1} 98 ${50 - hip} 90`,
        `Q${50 - waist} ${70 + bust} ${50 - waist - 2} ${52 + bust}`,
        `L${50 - shoulder + 8} 43.5`,
        `Q${50 - shoulder + 5} 48 ${50 - shoulder + 6.5} 56`,
        `Q${50 - shoulder + 8} 66 ${50 - shoulder + 8.5} 76`,
        `Q${50 - shoulder + 9.5} 84 ${50 - shoulder + 9} 88.5`,
        `Q${50 - shoulder + 7.5} 90.5 ${50 - shoulder + 6.5} 88`,
        `L${50 - shoulder + 4.5} 84`,
        `Q${50 - shoulder + 3.5} 78 ${50 - shoulder + 2} 72`,
        `Q${50 - shoulder} 60 ${50 - shoulder - 1} 47`,
        `Q${50 - shoulder - 2} 37 ${50 - shoulder * 0.55} 34.5`,
        "L45 30 L45 23.5 Q41.5 20 41.5 13 Q42 3.5 50 3.5 Z"
      ].join(" ")}
      fill="#E8C4A8"
      fillOpacity="0.16"
      stroke="#C89B7B"
      strokeWidth="0.8"
      strokeLinejoin="round"
    />
  );
}

function FrontFigure({ variant }: { variant: AnatomyVariant }) {
  return (
    <g>
      <BodyOutline variant={variant} />
      <Skeleton />
      <Organs variant={variant} />
      <Vessels />
    </g>
  );
}

export function AnatomyFigure({ variant }: { variant: AnatomyVariant }) {
  return (
    <svg viewBox="-30 -2 160 194" className="h-full w-auto" role="img" aria-label={VARIANT_LABELS[variant]}>
      <FrontFigure variant={variant} />
      <LeaderLabels labels={BODY_LABELS} markerId="bodyArrow" />
    </svg>
  );
}

/* ------------------------------------------------------------------ */
/* Heart detail — chambers, valves, conduction nodes, coronaries       */
/* ------------------------------------------------------------------ */

type HeartLabelSpec = {
  text: string;
  /** Text block position; the arrow starts at the block's inner edge. */
  tx: number;
  ty: number;
  anchor: "start" | "end";
  /** Short arrow: stops a little short of the structure. */
  ax: number;
  ay: number;
  /** Arrow tip on the structure itself. */
  tip: [number, number];
};

/*
 * Poster layout: the drawing sits centre (x 28–72); labels live in four
 * margin columns — two per side — and every leader is a SHORT line to the
 * nearest edge of its structure, never crossing the heart. Left column at
 * x≈13, inner-left at x≈24, inner-right at x≈76, right column at x≈87.
 */
const HEART_LABELS: HeartLabelSpec[] = [
  // upper-left column
  { text: "Superior vena cava", tx: 13, ty: 22, anchor: "end", ax: 14, ay: 21.5, tip: [35, 30] },
  { text: "Right atrium", tx: 13, ty: 32, anchor: "end", ax: 14, ay: 31.5, tip: [31, 49] },
  { text: "SA node", tx: 13, ty: 42, anchor: "end", ax: 14, ay: 41.5, tip: [36.5, 42.5] },
  // inner-left column (short reach)
  { text: "Right ventricle", tx: 22, ty: 60, anchor: "end", ax: 23, ay: 59.5, tip: [33, 68] },
  { text: "Inferior vena cava", tx: 22, ty: 70, anchor: "end", ax: 23, ay: 69.5, tip: [43.5, 79] },
  { text: "LAD coronary", tx: 22, ty: 80, anchor: "end", ax: 23, ay: 79.5, tip: [50.8, 62] },
  // upper-right column
  { text: "Aorta", tx: 87, ty: 22, anchor: "start", ax: 86, ay: 21.5, tip: [62, 21] },
  { text: "Main pulmonary artery", tx: 87, ty: 32, anchor: "start", ax: 86, ay: 31.5, tip: [73, 40] },
  { text: "Left atrium", tx: 87, ty: 42, anchor: "start", ax: 86, ay: 41.5, tip: [68.5, 52] },
  // inner-right column (short reach)
  { text: "Aortic valve", tx: 78, ty: 60, anchor: "start", ax: 77, ay: 59.5, tip: [50.5, 40] },
  { text: "Mitral valve", tx: 78, ty: 70, anchor: "start", ax: 77, ay: 69.5, tip: [55, 57.5] },
  { text: "Left ventricle", tx: 78, ty: 80, anchor: "start", ax: 77, ay: 79.5, tip: [64, 72] }
];

export function HeartDetail() {
  return (
    <div className="space-y-2">
      <div className="rounded-lg border border-line bg-inset p-3">
        <svg viewBox="-18 8 136 96" className="mx-auto h-[340px] w-auto" role="img" aria-label="Heart anatomy — chambers, valves, conduction system and coronary arteries">
          <defs>
            <radialGradient id="heartBody" cx="38%" cy="32%" r="80%">
              <stop offset="0%" stopColor="#C4574E" />
              <stop offset="100%" stopColor="#83281F" />
            </radialGradient>
            <radialGradient id="atriumTint" cx="45%" cy="35%" r="80%">
              <stop offset="0%" stopColor="#9E5A8C" />
              <stop offset="100%" stopColor="#6E3358" />
            </radialGradient>
          </defs>
          {/* great vessels */}
          <g fill="none" strokeLinecap="round">
            {/* aorta: root → arch → descending */}
            <path d="M48 44 Q47 34 49 28 Q52 20 62 20 Q70 21 69 30 Q68 40 62 48 Q58 56 56 64" stroke={C.artery} strokeWidth="6.5" />
            <path d="M48 44 Q47 34 49 28 Q52 20 62 20" stroke="#D96B5B" strokeWidth="2.2" opacity="0.55" />
            {/* pulmonary artery trunk + branches */}
            <path d="M54 42 Q60 36 66 37 Q73 38.5 74 45" stroke="#46688F" strokeWidth="4.6" />
            <path d="M66 37 Q72 32 78 33" stroke="#46688F" strokeWidth="2.6" />
            <path d="M52 40 Q44 34 37 36" stroke="#46688F" strokeWidth="2.4" />
            {/* SVC + IVC */}
            <path d="M36 22 Q35.5 32 36.5 42" stroke="#3E6FA8" strokeWidth="4.6" />
            <path d="M45 88 Q43.5 78 45.5 70" stroke="#3E6FA8" strokeWidth="4.2" />
            {/* pulmonary veins */}
            <path d="M68 50 Q74 48 78 50" stroke="#5B7BA8" strokeWidth="2.4" />
            <path d="M68 56 Q74 56 78 58" stroke="#5B7BA8" strokeWidth="2.2" />
          </g>
          {/* heart body */}
          <path
            d="M38 36 Q28 42 29 56 Q30 72 42 84 Q48 90 51 91 Q54 89.5 61 83 Q72 72 71.5 57 Q71 43 60 38 Q54 35.5 50.5 41 Q46 35.5 38 36 Z"
            fill="url(#heartBody)"
            stroke="#5E1F18"
            strokeWidth="0.7"
          />
          {/* atria */}
          <path d="M36 38 Q29.5 42 30.5 51 Q31.5 58 38 58.5 Q43.5 58 44 51 Q43.5 41.5 36 38 Z" fill="url(#atriumTint)" opacity="0.85" />
          <path d="M63 42 Q69 45 68.5 52.5 Q68 59.5 62 59.5 Q57 59 57 52.5 Q57.5 45 63 42 Z" fill="url(#atriumTint)" opacity="0.85" />
          {/* interventricular groove + interatrial line */}
          <g fill="none" stroke="#5E1F18" strokeWidth="0.8" opacity="0.85">
            <path d="M50.5 42 L51.5 89" />
            <path d="M31 52 Q37 49.5 44 51.5" opacity="0.7" />
            <path d="M57.5 52 Q63 49.5 68.5 51.5" opacity="0.7" />
          </g>
          {/* valves */}
          <g fill="none" strokeLinecap="round">
            {/* tricuspid */}
            <path d="M43.5 53 Q46.5 55.5 49 54" stroke="#E8D9A0" strokeWidth="1.1" />
            <path d="M43.5 53 Q45.5 58 48.5 58.5" stroke="#E8D9A0" strokeWidth="0.9" />
            {/* mitral */}
            <path d="M57.5 53.5 Q54.5 56 52 55" stroke="#E8D9A0" strokeWidth="1.1" />
            <path d="M57.5 53.5 Q55.5 58.5 52.5 58.8" stroke="#E8D9A0" strokeWidth="0.9" />
            {/* aortic valve cusps at the root */}
            <path d="M46.5 41 Q48 39.2 49.5 41 M49.5 41 Q51 39.2 52.5 41" stroke="#E8D9A0" strokeWidth="0.9" />
            {/* pulmonary valve */}
            <path d="M54.5 39.5 Q56 38 57.5 39.5" stroke="#E8D9A0" strokeWidth="0.8" />
          </g>
          {/* conduction system: SA node, AV node, bundle branches */}
          <g fill="none" strokeLinecap="round">
            <circle cx="37.5" cy="42.5" r="1.5" fill="#F2E27A" stroke="#B8A24A" strokeWidth="0.3" />
            <path d="M38.5 44 Q43 47 47 49.5" stroke="#F2E27A" strokeWidth="0.9" strokeDasharray="1.4 0.8" />
            <circle cx="47.5" cy="50" r="1.2" fill="#F2E27A" stroke="#B8A24A" strokeWidth="0.3" />
            <path d="M48 51.5 Q48.5 58 49 64" stroke="#F2E27A" strokeWidth="1" />
            <path d="M49 64 Q46.5 70 44.5 76" stroke="#F2E27A" strokeWidth="0.9" strokeDasharray="1.3 0.8" />
            <path d="M49 64 Q52 70 55.5 76" stroke="#F2E27A" strokeWidth="0.9" strokeDasharray="1.3 0.8" />
            <path d="M44.5 76 Q43 81 42.5 85 M55.5 76 Q57 81 57.5 85" stroke="#F2E27A" strokeWidth="0.8" strokeDasharray="1.2 0.8" />
            {/* Purkinje fan */}
            <path d="M42.5 85 L39 88 M42.5 85 L44 89 M57.5 85 L59.5 88.5 M57.5 85 L56 89.5" stroke="#F2E27A" strokeWidth="0.6" opacity="0.8" />
          </g>
          {/* coronary arteries */}
          <g fill="none" strokeLinecap="round">
            {/* LAD in the anterior groove */}
            <path d="M50.5 43 Q49.5 55 50.5 65 Q51 74 52.5 82" stroke="#F2C14E" strokeWidth="1.4" />
            <path d="M50 50 Q45.5 54 44 60" stroke="#F2C14E" strokeWidth="0.9" />
            <path d="M51 60 Q55 63 56.5 68" stroke="#F2C14E" strokeWidth="0.9" />
            {/* RCA around the right side */}
            <path d="M39 41 Q31.5 46 31.5 55 Q32 63 36 69" stroke="#F2C14E" strokeWidth="1.1" />
            {/* circumflex */}
            <path d="M60 41 Q67 46 67.5 54" stroke="#F2C14E" strokeWidth="0.9" />
          </g>
          {/* poster callouts: margin text, one short arrow each, no crossings */}
          <g fontSize="4.2" fontFamily="ui-monospace, monospace" fill="#374151">
            <defs>
              <ArrowMarker id="heartArrow" />
            </defs>
            {HEART_LABELS.map((l) => (
              <g key={l.text}>
                <text x={l.tx} y={l.ty} textAnchor={l.anchor}>{l.text}</text>
                <line x1={l.ax} y1={l.ay} x2={l.tip[0]} y2={l.tip[1]} stroke="#6B7280" strokeWidth="0.4" markerEnd="url(#heartArrow)" />
              </g>
            ))}
            <text x="50" y="99" textAnchor="middle">AV node</text>
            {/* deep structure: dashed leader runs along the septum groove */}
            <line x1="50" y1="95" x2="47.8" y2="51.5" stroke="#6B7280" strokeWidth="0.4" strokeDasharray="1.5 1" markerEnd="url(#heartArrow)" />
          </g>
        </svg>
      </div>
      <p className="text-2xs leading-relaxed text-faint">
        Chambers in red (atria tinted), valves in cream, conduction system in yellow — SA node → AV node → bundle
        branches — and the coronary tree wrapped around the surface. Chest findings on the map point here first.
      </p>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Body-map canvas: two labelled figures + pain hotspots               */
/* ------------------------------------------------------------------ */

const ZONE_ACTIVE = "#F2555A";

function HotspotEllipses({ hotspots, active, show }: { hotspots: Hotspot[]; active: Set<BodyRegionId>; show: boolean }) {
  return (
    <>
      {hotspots.map((h) => {
        const on = active.has(h.region);
        if (!on && !show) return null;
        return (
          <ellipse
            key={h.region}
            cx={h.cx}
            cy={h.cy}
            rx={h.rx}
            ry={h.ry}
            fill={on ? ZONE_ACTIVE : "#3A404A"}
            fillOpacity={on ? 0.5 : 0.26}
            stroke={on ? "#FF9A9D" : "#5A616C"}
            strokeWidth={on ? 0.7 : 0.4}
            strokeDasharray={on ? undefined : "1.6 1.2"}
            className="transition-[fill,fill-opacity] duration-300"
          />
        );
      })}
    </>
  );
}

const BACK_LABELS: LabelSpec[] = [
  { text: "Cervical spine", side: "left", y: 38, targetY: 40, targetX: 47 },
  { text: "Thoracic spine", side: "left", y: 56, targetY: 58, targetX: 47 },
  { text: "Lumbar spine", side: "left", y: 74, targetY: 76, targetX: 47 },
  { text: "Sacrum", side: "left", y: 94, targetY: 98, targetX: 47 },
  { text: "Scapula", side: "right", y: 46, targetY: 48, targetX: 58 },
  { text: "Latissimus dorsi", side: "right", y: 62, targetY: 64, targetX: 61 },
  { text: "Erector spinae", side: "right", y: 76, targetY: 78, targetX: 55 },
  { text: "Gluteus", side: "right", y: 94, targetY: 99, targetX: 57 }
];

function BackFigure({ variant }: { variant: AnatomyVariant }) {
  return (
    <g>
      <BodyOutline variant={variant} />
      <Skeleton />
      {/* spine emphasised from behind */}
      <path d="M50 31 L50 100" stroke={C.boneEdge} strokeWidth="1.8" strokeOpacity="0.9" strokeLinecap="round" />
      {[36, 42, 48, 54, 60, 66, 72, 78, 84, 90, 96].map((y) => (
        <line key={y} x1="48.2" y1={y} x2="51.8" y2={y} stroke="#8A7F66" strokeWidth="0.9" />
      ))}
      {/* scapulae + erector spinae + glutes */}
      <g fill="#9E4038" opacity="0.75">
        <path d="M39 42 Q46 41 45.5 50 Q44 56 39.5 54 Q37 48 39 42 Z" />
        <path d="M61 42 Q54 41 54.5 50 Q56 56 60.5 54 Q63 48 61 42 Z" />
        <path d="M42.5 56 Q50 58 48 84 L46 84 Q43.5 70 42.5 56 Z" opacity="0.8" />
        <path d="M57.5 56 Q50 58 52 84 L54 84 Q56.5 70 57.5 56 Z" opacity="0.8" />
        <path d="M41 96 Q47 94 49 101 Q47 105.5 43.5 104.5 Q40.5 101 41 96 Z" />
        <path d="M59 96 Q53 94 51 101 Q53 105.5 56.5 104.5 Q59.5 101 59 96 Z" />
      </g>
      <Vessels />
    </g>
  );
}

export function AnatomyBodyMap({ insights, variant }: { insights: { region: BodyRegionId }[]; variant: AnatomyVariant }) {
  const [showZones, setShowZones] = useState(false);
  const [showHeart, setShowHeart] = useState(false);
  const active = new Set(insights.map((i) => i.region));
  const heartInvolved = active.has("chest");
  const hotspots = HOTSPOTS[variant];

  return (
    <div className="space-y-2.5">
      <div className="flex items-center justify-between gap-2">
        <div className="flex rounded-md border border-line bg-inset p-0.5" role="group" aria-label="Body map detail level">
          {(["body", "heart"] as const).map((mode) => {
            const on = (mode === "body") === !showHeart;
            return (
              <button
                key={mode}
                type="button"
                onClick={() => setShowHeart(mode === "heart")}
                className={`rounded px-2.5 py-1 text-2xs font-medium capitalize transition-colors ${
                  on ? "bg-elev text-strong" : "text-faint hover:text-strong"
                }`}
              >
                {mode === "heart" ? (
                  <span className="flex items-center gap-1.5">
                    <Heart className="h-3 w-3" strokeWidth={1.9} /> Heart detail
                  </span>
                ) : (
                  "Body"
                )}
              </button>
            );
          })}
        </div>
        <label className="flex cursor-pointer items-center gap-1.5 text-2xs text-faint">
          <input
            type="checkbox"
            checked={showZones}
            onChange={(e) => setShowZones(e.target.checked)}
            className="h-3 w-3 accent-[#7C5CFC]"
          />
          Show all zones
        </label>
      </div>

      {showHeart ? (
        <HeartDetail />
      ) : (
        <div className="rounded-lg border border-line bg-inset p-3">
          <div className="flex items-stretch justify-center gap-2">
            <svg viewBox="-32 -2 164 194" className="h-[330px] w-1/2">
              <FrontFigure variant={variant} />
              <LeaderLabels labels={BODY_LABELS} markerId="bodyArrowFront" />
              <HotspotEllipses hotspots={hotspots.front} active={active} show={showZones} />
              <text x="-30" y="188" fontSize="6.5" fill="#6B7280" fontFamily="ui-monospace, monospace">
                FRONT
              </text>
            </svg>
            <svg viewBox="-32 -2 164 194" className="h-[330px] w-1/2">
              <BackFigure variant={variant} />
              <LeaderLabels labels={BACK_LABELS} markerId="bodyArrowBack" />
              <HotspotEllipses hotspots={hotspots.back} active={active} show={showZones} />
              <text x="130" y="188" fontSize="6.5" fill="#6B7280" fontFamily="ui-monospace, monospace" textAnchor="end">
                BACK
              </text>
            </svg>
          </div>
          <p className="mt-1 text-center text-2xs text-faint">{VARIANT_LABELS[variant]}</p>
        </div>
      )}

      {heartInvolved && !showHeart ? (
        <p className="text-2xs font-medium text-accent">Chest reported — see Heart detail for the coronary view.</p>
      ) : null}
      <div className="flex items-center justify-between gap-3">
        <span className="flex items-center gap-2 text-2xs text-faint">
          <span className="h-2 w-2 rounded-sm bg-[#3A404A]" />
          Unexamined
          <span className="ml-2 h-2 w-2 rounded-sm bg-[#F2555A]" />
          Reported
        </span>
        <span className="num text-2xs text-faint">
          {active.size} region{active.size === 1 ? "" : "s"}
        </span>
      </div>
    </div>
  );
}
