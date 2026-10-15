import { describe, expect, it } from "vitest";
import {
  deriveLocalClinicalGuidance,
  extractPainCharacteristics,
  inferBodyPainInsights,
  painCharacteristicsComplete,
  mergeInsights
} from "@/lib/bodyPain";

/**
 * The body map is drawn from these functions: they decide which region lights up
 * and which factors are listed beside it. Every case below is a phrase a patient
 * (or the ASR) actually produces — the ones the dictionary matcher used to miss
 * are the reason the patterns are regex-based, so they are the ones worth
 * pinning.
 */
describe("inferBodyPainInsights", () => {
  it("maps the phrasings a patient uses for the heart onto the chest", () => {
    for (const spoken of [
      "it pains in my heart",
      "pain in the left side of my heart",
      "seene mein dard ho raha hai",
      "سینے میں درد ہے",
      "tight chest pressure walking uphill"
    ]) {
      const regions = inferBodyPainInsights(spoken, "").map((insight) => insight.region);
      expect(regions, spoken).toContain("chest");
    }
  });

  it("reads the report text as well as the transcript", () => {
    const regions = inferBodyPainInsights("routine visit", "patient reports left arm pain").map(
      (insight) => insight.region
    );
    expect(regions).toContain("left_arm");
  });

  it("maps a side-less complaint to both sides", () => {
    const regions = inferBodyPainInsights("leg pain after walking", "").map((insight) => insight.region);
    expect(regions).toEqual(expect.arrayContaining(["left_leg", "right_leg"]));
  });

  it("reports nothing rather than guessing when no location was said", () => {
    expect(inferBodyPainInsights("feeling tired and dizzy", "")).toEqual([]);
  });

  it("returns regions in a stable display order", () => {
    const first = inferBodyPainInsights("headache and back pain and chest pain", "").map((i) => i.region);
    const second = inferBodyPainInsights("chest pain and back pain and headache", "").map((i) => i.region);
    expect(first).toEqual(second);
  });

  it("raises urgency when a cardiac flag arrives in a later line", () => {
    const line = inferBodyPainInsights("chest pain", "");
    expect(line[0].urgency).toBe("moderate");
    const accumulated = mergeInsights(line, [], "chest pain with sweating and shortness of breath");
    expect(accumulated[0].urgency).toBe("high");
    expect(accumulated[0].possibleFactors.join(" ")).toContain("ischemia");
  });

  it("accumulates regions instead of replacing them line by line", () => {
    const first = inferBodyPainInsights("chest pain", "");
    const merged = mergeInsights(first, inferBodyPainInsights("lower back pain", ""), "chest pain. lower back pain");
    expect(merged.map((insight) => insight.region)).toEqual(["chest", "back"]);
  });
});

describe("extractPainCharacteristics", () => {
  it("reads the OPQRST classes from English and Roman-Urdu wording", () => {
    const characteristics = extractPainCharacteristics(
      "tight crushing chest pain for 20 minutes, worse on climbing stairs, relieved by rest"
    );
    expect(characteristics.character).toContain("Pressure / tightness");
    expect(characteristics.duration).toContain("Seconds to minutes");
    expect(characteristics.triggers).toContain("Exertion / climbing stairs");
    expect(characteristics.triggers).toContain("Rest relieves");
    expect(painCharacteristicsComplete(characteristics)).toBe(true);
  });

  it("leaves a class empty rather than inventing one", () => {
    const characteristics = extractPainCharacteristics("my chest hurts");
    expect(characteristics.character).toEqual([]);
    expect(characteristics.duration).toEqual([]);
    expect(painCharacteristicsComplete(characteristics)).toBe(false);
  });
});

describe("deriveLocalClinicalGuidance", () => {
  it("asks for the examination and an ECG when a high-urgency region is present", () => {
    const guidance = deriveLocalClinicalGuidance(inferBodyPainInsights("chest pain and sweating", ""));
    expect(guidance.recommendedTests).toContain("12-lead ECG");
    expect(guidance.nextSteps.join(" ")).toContain("high-risk");
  });

  it("asks for the basics when nothing has been localised yet", () => {
    const guidance = deriveLocalClinicalGuidance([]);
    expect(guidance.doctorQuestions.length).toBeGreaterThan(0);
    expect(guidance.recommendedTests).not.toContain("12-lead ECG");
  });
});
