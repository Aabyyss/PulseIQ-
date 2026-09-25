export type BodyRegionId =
  | "head"
  | "neck"
  | "chest"
  | "left_arm"
  | "right_arm"
  | "upper_abdomen"
  | "lower_abdomen"
  | "back"
  | "left_leg"
  | "right_leg";

export type BodyPainInsight = {
  region: BodyRegionId;
  label: string;
  possibleFactors: string[];
  urgency: "low" | "moderate" | "high";
};

export type LocalClinicalGuidance = {
  doctorQuestions: string[];
  recommendedTests: string[];
  nextSteps: string[];
};

/**
 * Mirror of the backend's Urdu normalisation: arabic yeh/heh/alef
 * codepoints are unified with the Urdu ones and vowel marks are
 * dropped, so the same dictated word written differently still matches.
 */
const URDU_CHAR_MAP: Record<string, string> = {
  "\u0622": "\u0627",
  "\u0623": "\u0627",
  "\u0625": "\u0627",
  "\u064a": "\u06cc",
  "\u0649": "\u06cc",
  "\u0647": "\u06c1",
  "\u0629": "\u06c1"
};
const URDU_STRIP_RE = /[\u064b-\u0652\u0670\u0640\u200c\u200d\u200e\u200f]/g;

function normalizeUrduText(text: string): string {
  return text
    .replace(/[\u0622\u0623\u0625]/g, "\u0627")
    .replace(/[\u064a\u0649]/g, "\u06cc")
    .replace(/[\u0647\u0629]/g, "\u06c1")
    .replace(URDU_STRIP_RE, "");
}

/**
 * Region matching is regex-based and word-aware so patient phrasings such as
 * "it pains in my heart", "left side of the heart" or "mera seena dard" hit
 * the right zone. Substring matching missed them (they contain no "chest").
 * Most patterns live under the chest concept — cardiac pain is localised to
 * "the heart" and its sides, and ASR turns "pains" into a verb — plus the
 * side-specific arm/leg variants and Urdu/Roman-Urdu phrasings.
 *
 * \b only bounds ASCII words: Urdu-script patterns are plain multi-word
 * substrings (wrapping them in \b made them unmatchable), and Roman-Urdu
 * lists every spelling ASR tends to produce.
 */
const REGION_PATTERNS: Record<BodyRegionId, RegExp[]> = {
  head: [
    /\bhead\s*(pain|ache|aches|hurts?|paining)\b/,
    /\bpain(?:s)?\s+(?:in|of)\s+(?:my\s+|the\s+)?head\b/,
    /\bheadache\b/, /\bmigraine\b/,
    /\b(?:sar|sir|sirr)\s+(?:mein|main|me)?\s*dard\b/,
    /سر(?:\s+میں)?\s+درد/
  ],
  neck: [
    /\bneck\s*(pain|ache|aches|hurts?|stiffness|stiff|paining)\b/,
    /\bpain(?:s)?\s+(?:in|of)\s+(?:my\s+|the\s+)?neck\b/, /\bcervical\s+pain\b/,
    /\bgardan\s+(?:mein|main|me)?\s*dard\b/,
    /گردن(?:\s+میں)?\s+درد/
  ],
  chest: [
    /\bchest\s*(pain|pressure|tightness|discomfort|hurts?|heavy|heaviness|burning|paining)\b/,
    /\bpain(?:s)?\s+(?:in|of)\s+(?:my\s+|the\s+)?chest\b/,
    /\b(?:pressure|tightness|heaviness|burning)\s+in\s+(?:my\s+|the\s+)?chest\b/,
    /\btight\s+chest\b/, /\bangina\b/,
    // Patients say "heart", not "chest" — every cardiac phrasing maps here.
    /\bheart\s*(pain|pains|hurts?|ache|aches|paining|burning)\b/,
    /\bpain(?:s)?\s+(?:in|of)\s+(?:my\s+|the\s+)?heart\b/,
    /\bheart\s*area\b/,
    /\b(?:left|right)\s+side\s+of\s+(?:my\s+|the\s+)?(?:heart|chest)\b/,
    /\bpain\s+(?:in|on)\s+(?:my\s+|the\s+)?(?:left|right)\s+side\b/,
    /\bheart\s+pain\b/,
    // Roman Urdu incl. the spellings ASR produces ("sine me dard").
    /\b(?:seene|seenay|sine|sene)\s+(?:mein|main|me)?\s*(?:dard|darad|drad|jalan)\b/,
    /\b(?:chat|chati)\s+(?:mein|main|me)?\s*dard\b/,
    /\bdil\s+(?:mein|main|me|ka|ki)\s+(?:dard|darad|drad)\b/,
    // Urdu script as plain substrings (\b never matches Urdu).
    /سینے(?:\s+میں|\s+کا)?\s+درد/, /چھاتی\s+میں\s+درد/, /سینے\s+میں\s+جلن/,
    /دل(?:\s+میں|\s+کا)?\s+درد/
  ],
  left_arm: [
    /\bleft\s+arm\b/, /\bpain\s+in\s+(?:my\s+|the\s+)?left\s+arm\b/,
    /\bleft\s+shoulder\b/, /\bleft\s+hand\s+numbness\b/,
    /\b(?:baen|bayen|bayay)\s+bazu(?:\s+(?:mein|main|me))?\s*dard\b/,
    /بائیں\s+بازو(?:\s+میں)?\s+درد/
  ],
  right_arm: [
    /\bright\s+arm\b/, /\bpain\s+in\s+(?:my\s+|the\s+)?right\s+arm\b/,
    /\bright\s+shoulder\b/,
    /\bdayan\s+bazu(?:\s+(?:mein|main|me))?\s*dard\b/,
    /دایاں\s+بازو(?:\s+میں)?\s+درد/
  ],
  upper_abdomen: [
    /\bupper\s+(?:abdomen|stomach|belly)\s*(pain|ache|hurts?)?/,
    /\bepigastric\b/, /\bstomach\s+burning\b/,
    /\bpain\s+(?:in|of)\s+(?:my\s+|the\s+)?upper\s+(?:stomach|abdomen)\b/
  ],
  lower_abdomen: [
    /\blower\s+(?:abdomen|stomach|belly)\s*(pain|ache|hurts?)?/,
    /\bpelvic\s+pain\b/, /\babdominal\s+cramps\b/,
    /\bpain\s+(?:in|of)\s+(?:my\s+|the\s+)?lower\s+(?:stomach|abdomen|belly)\b/
  ],
  back: [
    /\bback\s*(pain|ache|hurts?|paining)\b/,
    /\bpain(?:s)?\s+(?:in|of)\s+(?:my\s+|the\s+)?back\b/,
    /\bupper\s+back\b/, /\blower\s+back\b/,
    /\bkamar\s+(?:mein|main|me)?\s*dard\b/,
    /کمر(?:\s+میں)?\s+درد/
  ],
  left_leg: [
    /\bleft\s+(?:leg|calf|thigh|knee|ankle|foot|feet)\b/,
    /\bpain\s+(?:in|of)\s+(?:my\s+|the\s+)?left\s+leg\b/,
    /\b(?:baen|bayen|bayay)\s+tang(?:\s+(?:mein|main|me))?\s*dard\b/,
    /بائیں\s+ٹانگ(?:\s+میں)?\s+درد/
  ],
  right_leg: [
    /\bright\s+(?:leg|calf|thigh|knee|ankle|foot|feet)\b/,
    /\bpain\s+(?:in|of)\s+(?:my\s+|the\s+)?right\s+leg\b/,
    /\bdayan\s+tang(?:\s+(?:mein|main|me))?\s*dard\b/,
    /دایاں\s+ٹانگ(?:\s+میں)?\s+درد/
  ]
};

/** Bare "leg pain" / "dard" without a side maps to both sides. */
const GENERIC_PATTERNS: { pattern: RegExp; targets: BodyRegionId[] }[] = [
  { pattern: /\barm\s*(pain|ache|hurts?|paining)\b|\bshoulder\s+pain\b/, targets: ["left_arm", "right_arm"] },
  { pattern: /\bleg\s*(pain|ache|hurts?|paining)\b/, targets: ["left_leg", "right_leg"] },
  { pattern: /\bstomach\s*(pain|ache|hurts?)\b|\bbelly\s+pain\b|\bpet\s+(?:mein|main|me)?\s*dard\b/, targets: ["upper_abdomen"] }
];

const REGION_LABELS: Record<BodyRegionId, string> = {
  head: "Head",
  neck: "Neck",
  chest: "Chest",
  left_arm: "Left Arm",
  right_arm: "Right Arm",
  upper_abdomen: "Upper Abdomen",
  lower_abdomen: "Lower Abdomen",
  back: "Back",
  left_leg: "Left Leg",
  right_leg: "Right Leg"
};

function factorsForRegion(region: BodyRegionId, text: string): { factors: string[]; urgency: "low" | "moderate" | "high" } {
  const hasCardiacFlags =
    text.includes("shortness of breath") ||
    text.includes("sweating") ||
    text.includes("troponin elevated") ||
    text.includes("st elevation");

  if (region === "left_arm") {
    return {
      factors: [
        "Musculoskeletal strain or shoulder tendinopathy",
        "Cervical nerve root irritation (radiculopathy)",
        "Referred cardiac pain (higher concern if chest symptoms coexist)",
      ],
      urgency: hasCardiacFlags ? "high" : "moderate",
    };
  }
  if (region === "chest") {
    return {
      factors: [
        "Myocardial ischemia/angina pattern",
        "Costochondritis or chest wall strain",
        "Reflux/esophageal pain",
      ],
      urgency: hasCardiacFlags ? "high" : "moderate",
    };
  }
  if (region === "back") {
    return {
      factors: [
        "Postural or muscular strain",
        "Thoracic spine/radicular pain",
        "Referred visceral pain depending on associated symptoms",
      ],
      urgency: "low",
    };
  }
  if (region === "head" || region === "neck") {
    return {
      factors: [
        "Tension pattern pain",
        "Cervical muscular spasm",
        "Vascular/neurologic causes depending on red flags",
      ],
      urgency: "moderate",
    };
  }
  if (region === "upper_abdomen" || region === "lower_abdomen") {
    return {
      factors: [
        "Gastrointestinal inflammation/spasm",
        "Muscular wall pain",
        "Visceral referred pain requiring clinical correlation",
      ],
      urgency: "moderate",
    };
  }
  return {
    factors: [
      "Musculoskeletal overuse or strain",
      "Peripheral nerve irritation",
      "Vascular/inflammatory causes based on exam and tests",
    ],
    urgency: "low",
  };
}

function insightFor(region: BodyRegionId, text: string): BodyPainInsight {
  const factors = factorsForRegion(region, text);
  return {
    region,
    label: REGION_LABELS[region],
    possibleFactors: factors.factors,
    urgency: factors.urgency,
  };
}

export function inferBodyPainInsights(transcript: string, reportText: string): BodyPainInsight[] {
  const raw = `${transcript} ${reportText}`.toLowerCase();
  const text = /[\u0600-\u06ff]/.test(raw) ? normalizeUrduText(raw) : raw;
  const matched: BodyPainInsight[] = [];
  const seen = new Set<BodyRegionId>();

  (Object.keys(REGION_PATTERNS) as BodyRegionId[]).forEach((region) => {
    const hit = REGION_PATTERNS[region].some((pattern) => pattern.test(text));
    if (!hit) return;
    seen.add(region);
    matched.push(insightFor(region, text));
  });

  // Generic fallbacks when side isn't stated.
  GENERIC_PATTERNS.forEach(({ pattern, targets }) => {
    if (!pattern.test(text)) return;
    targets
      .filter((region) => !seen.has(region))
      .forEach((region) => {
        seen.add(region);
        matched.push(insightFor(region, text));
      });
  });

  // Keep a stable display order regardless of match order.
  const order = Object.keys(REGION_LABELS) as BodyRegionId[];
  return matched.sort((a, b) => order.indexOf(a.region) - order.indexOf(b.region));
}

/**
 * Merge per-line insights into a running view of the encounter: the body map
 * accumulates every region reported across the whole transcript instead of
 * flashing to "0 regions" whenever a new line contains no location.
 * Re-derives factors/urgency against the full accumulated text so cardiac
 * flags ("…and sweating") raise urgency even when they arrive later.
 */
export function mergeInsights(existing: BodyPainInsight[], incoming: BodyPainInsight[], text: string): BodyPainInsight[] {
  const regions = new Set([...existing.map((i) => i.region), ...incoming.map((i) => i.region)]);
  return (Object.keys(REGION_LABELS) as BodyRegionId[])
    .filter((region) => regions.has(region))
    .map((region) => insightFor(region, text));
}

export function deriveLocalClinicalGuidance(insights: BodyPainInsight[]): LocalClinicalGuidance {
  if (insights.length === 0) {
    return {
      doctorQuestions: [
        "Can you describe exact location, severity, and duration of pain?",
        "What triggers or relieves the symptoms?",
        "Any associated symptoms like shortness of breath, sweating, or dizziness?",
      ],
      recommendedTests: ["Vital signs and pulse oximetry", "Focused clinical examination"],
      nextSteps: ["Continue focused history and exam", "Escalate if red-flag symptoms are present"],
    };
  }

  const hasHigh = insights.some((i) => i.urgency === "high");
  return {
    doctorQuestions: [
      "Is the pain radiating to jaw, arm, or back?",
      "Is pain related to exertion, breathing, or position?",
      "Any syncope, severe breathlessness, or diaphoresis?",
    ],
    recommendedTests: hasHigh
      ? ["12-lead ECG", "Serial troponin", "Continuous monitoring and vitals"]
      : ["Focused exam", "Baseline ECG if clinically indicated", "Basic labs per protocol"],
    nextSteps: hasHigh
      ? ["Treat as high-risk until ruled out", "Follow urgent chest pain pathway"]
      : ["Monitor progression and reassess", "Plan outpatient or urgent follow-up based on clinician judgment"],
  };
}
