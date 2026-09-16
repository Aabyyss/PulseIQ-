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

const REGION_KEYWORDS: Record<BodyRegionId, string[]> = {
  head: ["head pain", "headache", "migraine", "pain in head"],
  neck: ["neck pain", "neck stiffness", "cervical pain", "pain in neck", "گردن میں درد", "gardan mein dard"],
  chest: ["chest pain", "chest pressure", "chest tightness", "pain in chest", "سینے میں درد", "seene mein dard"],
  left_arm: ["left arm pain", "pain in left arm", "left shoulder pain", "left hand numbness", "left arm", "بائیں بازو میں درد", "baen bazu mein dard"],
  right_arm: ["right arm pain", "pain in right arm", "right shoulder pain", "right arm", "دایاں بازو درد", "dayan bazu dard"],
  upper_abdomen: ["upper abdomen pain", "epigastric pain", "stomach burning", "upper stomach pain"],
  lower_abdomen: ["lower abdomen pain", "pelvic pain", "abdominal cramps", "lower stomach pain"],
  back: ["back pain", "upper back pain", "lower back pain", "pain in back", "کمر میں درد", "kamar dard"],
  left_leg: ["left leg pain", "left calf pain", "left thigh pain", "pain in left leg", "left knee pain", "بائیں ٹانگ میں درد", "baen tang mein dard"],
  right_leg: ["right leg pain", "right calf pain", "right thigh pain", "pain in right leg", "right knee pain", "دایاں ٹانگ درد", "dayan tang dard"],
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

export function inferBodyPainInsights(transcript: string, reportText: string): BodyPainInsight[] {
  const text = `${transcript} ${reportText}`.toLowerCase();
  const matched: BodyPainInsight[] = [];

  (Object.keys(REGION_KEYWORDS) as BodyRegionId[]).forEach((region) => {
    const hit = REGION_KEYWORDS[region].some((keyword) => text.includes(keyword));
    if (!hit) return;
    const factors = factorsForRegion(region, text);
    matched.push({
      region,
      label: region.replace("_", " ").replace(/\b\w/g, (c) => c.toUpperCase()),
      possibleFactors: factors.factors,
      urgency: factors.urgency,
    });
  });

  // Generic fallbacks when side isn't stated.
  if ((text.includes("arm pain") || text.includes("shoulder pain")) && !matched.some((m) => m.region === "left_arm" || m.region === "right_arm")) {
    const left = factorsForRegion("left_arm", text);
    const right = factorsForRegion("right_arm", text);
    matched.push({ region: "left_arm", label: "Left Arm", possibleFactors: left.factors, urgency: left.urgency });
    matched.push({ region: "right_arm", label: "Right Arm", possibleFactors: right.factors, urgency: right.urgency });
  }
  if (text.includes("leg pain") && !matched.some((m) => m.region === "left_leg" || m.region === "right_leg")) {
    const left = factorsForRegion("left_leg", text);
    const right = factorsForRegion("right_leg", text);
    matched.push({ region: "left_leg", label: "Left Leg", possibleFactors: left.factors, urgency: left.urgency });
    matched.push({ region: "right_leg", label: "Right Leg", possibleFactors: right.factors, urgency: right.urgency });
  }
  if (text.includes("stomach pain") && !matched.some((m) => m.region === "upper_abdomen" || m.region === "lower_abdomen")) {
    const upper = factorsForRegion("upper_abdomen", text);
    matched.push({ region: "upper_abdomen", label: "Upper Abdomen", possibleFactors: upper.factors, urgency: upper.urgency });
  }

  return matched;
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
