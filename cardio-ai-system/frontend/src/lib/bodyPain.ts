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

/**
 * OPQRST-lite pain characteristics — the details the review called out as
 * clinically decisive: character, duration, triggers/relief and radiation.
 * Extracted by regex over the accumulated transcript (English + common
 * Urdu/Roman-Urdu phrasings), so it appears the moment the patient says it.
 */
export type PainCharacteristics = {
  character: string[];
  duration: string[];
  triggers: string[];
  radiation: string[];
};

const CHARACTER_PATTERNS: { label: string; pattern: RegExp }[] = [
  { label: "Pressure / tightness", pattern: /\b(?:pressure|tightness|tight|squeezing|heaviness|heavy|crushing|band-like)\b/ },
  { label: "Burning", pattern: /\b(?:burning|acid|jalan|heartburn)\b/ },
  { label: "Sharp / stabbing", pattern: /\b(?:sharp|stabbing|knife|piercing|catching)\b/ },
  { label: "Aching / dull", pattern: /\b(?:ache|aching|dull|throbbing|pounding)\b/ },
  { label: "Cramping", pattern: /\b(?:cramp|cramping|spasm)\b/ },
  { label: "Numbness / tingling", pattern: /\b(?:numb|numbness|tingling|pins and needles|jhanjhanahat)\b/ },
  { label: "Breathlessness", pattern: /\b(?:breathless|shortness of breath|saans ki takleef|dhak dhak)\b/ },
];

const DURATION_PATTERNS: { label: string; pattern: RegExp }[] = [
  { label: "Constant", pattern: /\b(?:constant|continuous|non-stop|continuously|always)\b/ },
  // "comes and goes" was listed twice — the intended second spelling, "come and
  // go", was the one that was missing, along with the wave phrasing.
  { label: "Comes and goes", pattern: /\b(?:come[s]? and go(?:es)?|intermittent|on and off|off and on|in waves|episodes?|recurring|occasional)\b/ },
  { label: "Seconds to minutes", pattern: /\b\d+(?:\.\d+)?\s*(?:second|sec|min|minute)s\b|\bfew minutes\b|\b(?:half|quarter)\s+(?:an?\s+)?(?:minute|hour)\b/ },
  { label: "Hours", pattern: /\b\d+(?:\.\d+)?\s*hours?\b|\bfor hours\b|\b(?:an?|one|two|three|several)\s+hours?\b/ },
  { label: "Days or longer", pattern: /\b\d+(?:\.\d+)?\s*days?\b|\b(?:a|one|two|three|several|few)\s+days?\b|\bfor weeks?\b|\bfor months?\b|\bsince (?:yesterday|last)/ },
];

const TRIGGER_PATTERNS: { label: string; pattern: RegExp }[] = [
  // "worse with walking" and "worse when I walk uphill" are how a patient
  // describes exertional pain; only "walking fast" used to be recognised, so the
  // commonest trigger there is was recorded as no trigger at all.
  { label: "Exertion / climbing stairs", pattern: /\b(?:exertion|exertional|climb(?:ing|s)?|stairs|walk(?:ing|s)?|exercise|running|jogging|effort|mehnat)\b/ },
  {
    label: "Worse on exertion",
    pattern: /\b(?:worse|worsens?|brought on|brought about|triggered|aggravated)\s+(?:with|by|on|during|when)\b/
  },
  { label: "Rest relieves", pattern: /\b(?:relieved by rest|eases? with rest|better with rest|rest (?:helps|relieves)|rest karne se|settles? (?:with|on|at) rest|subsides? with rest|goes? away when I (?:rest|sit|lie))\b/ },
  { label: "Breathing triggers", pattern: /\b(?:worse (?:when |while )?breathing|on deep breath|pleuritic|breathing deeply|saans lene par)\b/ },
  { label: "Lying flat", pattern: /\b(?:lying flat|when lying down|flat on (?:my |the )?back|sone par)\b/ },
  { label: "Meals / food", pattern: /\b(?:after (?:meals?|eating|food)|worse (?:after|post) (?:meal|food)|khanay k baad)\b/ },
  { label: "Stress or emotion", pattern: /\b(?:stress|anxiety|angry|emotional|tension)\b/ },
  { label: "Cold / weather", pattern: /\b(?:cold (?:weather|air)|winter|mausam ki thand)\b/ },
  { label: "Palpation / movement", pattern: /\b(?:tender to touch|when pressed|on pressing|touch karne par|movement)\b/ },
];

const RADIATION_PATTERNS: { label: string; pattern: RegExp }[] = [
  { label: "Left arm", pattern: /\b(?:left (?:arm|hand)|baen bazu|down (?:the )?left arm)\b/ },
  { label: "Both arms / shoulders", pattern: /\b(?:both arms|either arm|(?:left|right) shoulder|bayen dayan kandha|\b(?:going|goes|went|spreading|spreads|radiating|radiates|referred)\s+to\s+(?:my\s+|the\s+)?shoulders?)\b/ },
  { label: "Jaw / neck", pattern: /\b(?:jaw|throat|gardan|chabba|neck (?:pain|ache|radiation))\b/ },
  {
    label: "Back",
    pattern: /\b(?:between (?:the )?shoulder blades|upper back|mere back|kamar|dorsum|(?:going|goes|went|spreading|spreads|radiating|radiates|referred)\s+to\s+(?:my\s+|the\s+)?(?:back|upper back))\b/
  },
  { label: "Epigastrium / stomach", pattern: /\b(?:epigastr|upper stomach|pet k upper|below (?:the )?breastbone|sternum)\b/ },
];

function collectPatterns(
  text: string,
  table: { label: string; pattern: RegExp }[]
): string[] {
  return table.filter((entry) => entry.pattern.test(text)).map((entry) => entry.label);
}

/**
 * Extract pain characteristics from the accumulated text. Returns only the
 * classes actually mentioned — an empty array means "not stated yet", which
 * the UI shows as a prompt for the clinician to ask, never as a guess.
 */
export function extractPainCharacteristics(text: string): PainCharacteristics {
  const raw = `${text}`.toLowerCase();
  const normalised = /[\u0600-\u06ff]/.test(raw) ? normalizeUrduText(raw) : raw;
  return {
    character: collectPatterns(normalised, CHARACTER_PATTERNS),
    duration: collectPatterns(normalised, DURATION_PATTERNS),
    triggers: collectPatterns(normalised, TRIGGER_PATTERNS),
    radiation: collectPatterns(normalised, RADIATION_PATTERNS),
  };
}

/** Has anything about character/duration/triggers/radiation been said? */
export function painCharacteristicsComplete(c: PainCharacteristics): boolean {
  return c.character.length + c.duration.length + c.triggers.length + c.radiation.length > 0;
}

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
// \u200c-\u200f is written as a range: listing ZWJ (\u200d) as its own
// class atom between two other atoms is a "joined character sequence".
const URDU_STRIP_RE = /[\u064b-\u0652\u0670\u0640\u200c-\u200f]/g;

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
 *
 * Each region is now generated from the same two lists — the words for the part
 * and the words for how it feels — so the map moves as one grammar instead of as
 * a fixed list of phrases: "back pain" matched and "my back aches" did not,
 * because every pattern required the symptom word to sit immediately after the
 * body part, and the natural English and Urdu constructions put a verb or two in
 * between. A short list of linking words is allowed in between; anything wider
 * (or a character window) started lighting up the wrong region when two
 * complaints shared a sentence.
 */
/**
 * How a part of the body is said to feel. One list, because the region map and
 * the side-less fallback both ask the same question, and because a verb form
 * missing from here is a region silently dropped from the map.
 */
const FEELING =
  "pain|pains|painful|paining|aches?|aching|achy|hurts?|hurting|sore|soreness|" +
  "tender|tenderness|burn(?:s|ing)?|pressure|tight(?:ness)?|heavy|heaviness|" +
  "discomfort|numb(?:ness)?|stiff(?:ness)?|cramp(?:s|ing)?|swell(?:ing|en)?|" +
  "throbbing|sharp|dull|pounding";

/**
 * Words that may sit between the part and the feeling — "my back IS aching",
 * "the chest has been hurting". Deliberately only linking words: allowing any
 * word (or a character window) here made "back is fine but chest pain" light up
 * the back, so a false region is exactly what the narrow list prevents.
 */
const LINKING = "(?:is|are|was|were|be|been|being|feels?|felt|feeling|gets?|got|has|have|had|really|very|so|too|now|still|also|and|my)";

/** "<part> [linking words] <how it feels>" — the shape most complaints take. */
function feelingAfter(parts: string): RegExp {
  return new RegExp(`\\b(?:${parts})\\b(?:\\s+${LINKING}){0,3}\\s*(?:${FEELING})\\b`, "i");
}

/**
 * The same complaint in the other order — "aching in my back", "a burning in
 * the chest". The feeling comes first here, so the link is a preposition rather
 * than a verb, and both orders have to be built or half the ward's phrasing
 * leaves the map empty.
 */
function feelingBefore(parts: string): RegExp {
  return new RegExp(
    `\\b(?:${FEELING})\\b\\s+(?:in|of|at|around|near|over|on)\\s+(?:my\\s+|the\\s+|both\\s+|both\\s+my\\s+)?(?:${parts})\\b`,
    "i"
  );
}

/** A region's patterns: both shared shapes plus whatever it alone needs. */
function region(parts: string, extra: RegExp[] = []): RegExp[] {
  return [feelingAfter(parts), feelingBefore(parts), ...extra];
}

const REGION_PATTERNS: Record<BodyRegionId, RegExp[]> = {
  head: region("head|heads", [
    /\bheadache\b/,
    /\bmigraine\b/,
    /\b(?:sar|sir|sirr)\s+(?:mein|main|me)?\s*dard\b/,
    /سر(?:\s+میں)?\s+درد/
  ]),
  neck: region("neck", [
    /\bpain(?:s)?\s+(?:in|of)\s+(?:my\s+|the\s+)?neck\b/,
    /\bcervical\s+pain\b/,
    /\bgardan\s+(?:mein|main|me)?\s*dard\b/,
    /گردن(?:\s+میں)?\s+درد/
  ]),
  chest: region("chest|chests|heart", [
    /\bpain(?:s)?\s+(?:in|of)\s+(?:my\s+|the\s+)?chest\b/,
    /\b(?:pressure|tightness|heaviness|burning)\s+in\s+(?:my\s+|the\s+)?chest\b/,
    /\btight\s+chest\b/,
    /\bangina\b/,
    /\bpain(?:s)?\s+(?:in|of)\s+(?:my\s+|the\s+)?heart\b/,
    /\bheart\s*area\b/,
    /\b(?:left|right)\s+side\s+of\s+(?:my\s+|the\s+)?(?:heart|chest)\b/,
    /\bpain\s+(?:in|on)\s+(?:my\s+|the\s+)?(?:left|right)\s+side\b/,
    // Roman Urdu incl. the spellings ASR produces ("sine me dard").
    /\b(?:seene|seenay|sine|sene)\s+(?:mein|main|me)?\s*(?:dard|darad|drad|jalan)\b/,
    /\b(?:chat|chati)\s+(?:mein|main|me)?\s*dard\b/,
    /\bdil\s+(?:mein|main|me|ka|ki)\s+(?:dard|darad|drad)\b/,
    // Urdu script as plain substrings (\b never matches Urdu).
    /سینے(?:\s+میں|\s+کا)?\s+درد/, /چھاتی\s+میں\s+درد/, /سینے\s+میں\s+جلن/,
    /دل(?:\s+میں|\s+کا)?\s+درد/
  ]),
  left_arm: region("left\\s+(?:arm|arms|hand|hands|shoulder|shoulders|elbow|elbows|wrist|wrists|finger|fingers)", [
    /\bpain\s+(?:radiating\s+)?(?:to|in|of)\s+(?:my\s+|the\s+)?left\s+(?:arm|hand)\b/,
    /\b(?:baen|bayen|bayay)\s+bazu(?:\s+(?:mein|main|me))?\s*dard\b/,
    /بائیں\s+بازو(?:\s+میں)?\s+درد/
  ]),
  right_arm: region("right\\s+(?:arm|arms|hand|hands|shoulder|shoulders|elbow|elbows|wrist|wrists|finger|fingers)", [
    /\bpain\s+(?:radiating\s+)?(?:to|in|of)\s+(?:my\s+|the\s+)?right\s+(?:arm|hand)\b/,
    /\bdayan\s+bazu(?:\s+(?:mein|main|me))?\s*dard\b/,
    /دایاں\s+بازو(?:\s+میں)?\s+درد/
  ]),
  upper_abdomen: region("upper\\s+(?:abdomen|stomach|belly)|epigastrium|epigastric", [
    /\bstomach\s+burning\b/,
    /\bpain\s+(?:in|of)\s+(?:my\s+|the\s+)?upper\s+(?:stomach|abdomen|belly)\b/
  ]),
  lower_abdomen: region("lower\\s+(?:abdomen|stomach|belly)|pelvis|pelvic", [
    /\babdominal\s+cramps\b/,
    /\bpain\s+(?:in|of)\s+(?:my\s+|the\s+)?lower\s+(?:stomach|abdomen|belly)\b/
  ]),
  back: region("back|backs|spine", [
    /\bupper\s+back\b/,
    /\blower\s+back\b/,
    /\bkamar\s+(?:mein|main|me)?\s*dard\b/,
    /کمر(?:\s+میں)?\s+درد/
  ]),
  left_leg: region("left\\s+(?:leg|legs|calf|calves|thigh|thighs|knee|knees|ankle|ankles|foot|feet|toe|toes)", [
    /\bpain\s+(?:in|of)\s+(?:my\s+|the\s+)?left\s+leg\b/,
    /\b(?:baen|bayen|bayay)\s+tang(?:\s+(?:mein|main|me))?\s*dard\b/,
    /بائیں\s+ٹانگ(?:\s+میں)?\s+درد/
  ]),
  right_leg: region("right\\s+(?:leg|legs|calf|calves|thigh|thighs|knee|knees|ankle|ankles|foot|feet|toe|toes)", [
    /\bpain\s+(?:in|of)\s+(?:my\s+|the\s+)?right\s+leg\b/,
    /\bdayan\s+tang(?:\s+(?:mein|main|me))?\s*dard\b/,
    /دایاں\s+ٹانگ(?:\s+میں)?\s+درد/
  ])
};

/**
 * Bare "leg pain" / "dard" without a side maps to both sides — including the
 * plural and the Urdu word for legs, which is how a patient says it.
 */
const GENERIC_PATTERNS: { pattern: RegExp; targets: BodyRegionId[] }[] = [
  {
    pattern: feelingAfter("arms?|shoulders?|hands?|elbows?|wrists?|fingers?"),
    targets: ["left_arm", "right_arm"]
  },
  {
    pattern: feelingAfter("legs?|calves|calf|thighs?|knees?|ankles?|feet|foot|toes?"),
    targets: ["left_leg", "right_leg"]
  },
  {
    // Urdu script needs no \b and must not have one: JS treats Urdu letters as
    // non-word characters, so a boundary assertion before them can never match.
    pattern: /\btang(?:on|en|ein)?\s*(?:mein|main|me)?\s*dard\b|(?:پیر|پاؤں|ٹانگ)(?:وں|یں)?\s*(?:میں|می)?\s*درد/,
    targets: ["left_leg", "right_leg"]
  },
  {
    pattern: feelingAfter("stomach|belly|abdomen"),
    targets: ["upper_abdomen"]
  },
  {
    pattern: /\bpet\s+(?:mein|main|me)?\s*dard\b/,
    targets: ["upper_abdomen"]
  },
  {
    pattern: /\bboth\s+(?:arms?|shoulders?|hands?)\b/,
    targets: ["left_arm", "right_arm"]
  },
  {
    pattern: /\bboth\s+(?:legs?|knees?|feet|calves)\b/,
    targets: ["left_leg", "right_leg"]
  }
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
    const match = pattern.exec(text);
    if (!match) return;
    // A phrase that names its own side is not side-less: "my left hand is numb"
    // must not also light up the right arm just because the fallback matched too.
    // The side word usually sits just outside the match ("[left] hand is numb"),
    // so the words before it are checked as well as the match itself.
    const before = text.slice(Math.max(0, match.index - 12), match.index);
    if (/\b(?:left|right)\b/i.test(match[0]) || /\b(?:left|right)\b/i.test(before)) return;
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
