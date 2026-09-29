import type { BodyRegionId } from "@/lib/bodyPain";

/** Male and female anatomical presentations; neutral when gender is unset. */
export type AnatomyVariant = "male" | "female" | "neutral";

export function variantForGender(gender: string): AnatomyVariant {
  const g = gender.trim().toLowerCase();
  if (g === "female" || g === "f" || g === "woman") return "female";
  if (g === "male" || g === "m" || g === "man") return "male";
  return "neutral";
}

export const VARIANT_LABELS: Record<AnatomyVariant, string> = {
  male: "Male anatomy",
  female: "Female anatomy",
  neutral: "Anatomy (gender not set)"
};

export type Hotspot = {
  region: BodyRegionId;
  cx: number;
  cy: number;
  rx: number;
  ry: number;
};

/**
 * Hit areas over the detailed figures, tuned per variant: the female torso
 * carries a lower, rounder chest zone and wider pelvis; the male one a
 * broader shoulder line and flatter pectoral zone. Coordinates live in each
 * figure's 100×190 space — the renderer translates per panel.
 */
const FRONT_NEUTRAL: Hotspot[] = [
  { region: "head", cx: 50, cy: 16, rx: 10.5, ry: 12 },
  { region: "neck", cx: 50, cy: 32, rx: 7, ry: 4.5 },
  { region: "chest", cx: 50, cy: 52, rx: 17, ry: 11 },
  { region: "left_arm", cx: 27.5, cy: 62, rx: 7.5, ry: 18 },
  { region: "right_arm", cx: 72.5, cy: 62, rx: 7.5, ry: 18 },
  { region: "upper_abdomen", cx: 50, cy: 74, rx: 13.5, ry: 8 },
  { region: "lower_abdomen", cx: 50, cy: 89, rx: 12.5, ry: 8 },
  { region: "left_leg", cx: 43, cy: 128, rx: 8, ry: 26 },
  { region: "right_leg", cx: 57, cy: 128, rx: 8, ry: 26 }
];

const BACK_NEUTRAL: Hotspot[] = [
  { region: "head", cx: 50, cy: 16, rx: 10.5, ry: 12 },
  { region: "neck", cx: 50, cy: 32, rx: 7, ry: 4.5 },
  { region: "back", cx: 50, cy: 60, rx: 16, ry: 20 },
  { region: "left_arm", cx: 27.5, cy: 62, rx: 7.5, ry: 18 },
  { region: "right_arm", cx: 72.5, cy: 62, rx: 7.5, ry: 18 },
  { region: "left_leg", cx: 43, cy: 128, rx: 8, ry: 26 },
  { region: "right_leg", cx: 57, cy: 128, rx: 8, ry: 26 }
];

const FRONT_MALE: Hotspot[] = FRONT_NEUTRAL.map((h) => {
  if (h.region === "chest") return { ...h, cx: 50, cy: 51, rx: 18.5, ry: 10.5 };
  if (h.region === "upper_abdomen") return { ...h, rx: 14.5 };
  if (h.region === "lower_abdomen") return { ...h, rx: 13 };
  return h;
});

const FRONT_FEMALE: Hotspot[] = FRONT_NEUTRAL.map((h) => {
  if (h.region === "chest") return { ...h, cx: 50, cy: 53, rx: 16, ry: 10 };
  if (h.region === "upper_abdomen") return { ...h, cy: 75, rx: 12, ry: 7.5 };
  if (h.region === "lower_abdomen") return { ...h, cy: 90, rx: 13.5, ry: 8.5 };
  return h;
});

export const HOTSPOTS: Record<AnatomyVariant, { front: Hotspot[]; back: Hotspot[] }> = {
  male: { front: FRONT_MALE, back: BACK_NEUTRAL },
  female: { front: FRONT_FEMALE, back: BACK_NEUTRAL },
  neutral: { front: FRONT_NEUTRAL, back: BACK_NEUTRAL }
};
