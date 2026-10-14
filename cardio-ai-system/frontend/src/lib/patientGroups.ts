/**
 * The race/ethnicity groups the pooled cohort equations publish a model for.
 *
 * One list, shared by every form that records a patient's visit details, for the
 * same reason the score inputs are assembled once on the backend: two lists would
 * eventually offer two different sets, and the equation would be handed a group it
 * has no coefficients for. The value is the slug `backend/risk_score_context`
 * reads — it also accepts the prose and hyphenated spellings, but a form has no
 * reason to rely on that.
 *
 * Categories the equations do not publish are deliberately absent rather than
 * lumped into one of these. Recording "other" would leave the equation with no
 * model to select, which is the same state as an unrecorded group: the higher of
 * the two sex-matched models is reported, with the other one beside it. An empty
 * value means exactly that — not recorded — and is what the forms send by default.
 */
export type RaceOption = { value: string; label: string };

export const RACE_OPTIONS: RaceOption[] = [
  { value: "white", label: "White" },
  { value: "african_american", label: "African American" }
];

export const RACE_HINT =
  "The pooled cohort equations publish one model for white patients and one for African American patients. Left unrecorded, the higher of the two sex-matched models is reported and the other is shown beside it.";
