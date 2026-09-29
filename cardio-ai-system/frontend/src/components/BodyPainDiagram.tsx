import { AnatomyBodyMap } from "@/components/AnatomyFigure";
import { variantForGender } from "@/lib/anatomy";
import type { BodyPainInsight } from "@/lib/bodyPain";

/**
 * Detailed anatomical body map. `gender` is the raw Patient-details value;
 * female → female figure, male → male figure, anything else → neutral.
 */
export function BodyPainDiagram({ insights, gender = "" }: { insights: BodyPainInsight[]; gender?: string }) {
  return <AnatomyBodyMap insights={insights} variant={variantForGender(gender)} />;
}
