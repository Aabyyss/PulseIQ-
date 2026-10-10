# Competitive landscape — what PulseIQ has, and what it can gain

Comparison against the two competitor categories reviewed on 3 Oct 2026:
general medical AI scribes with cardiology modules (Abridge, DeepScribe, Suki,
Nabla, Freed, Sunoh) and cardiology-specific assistants (EvidenceMD,
Doximity Ask, Shifaa AI, OmniMD).

## The four gaps in existing tools — PulseIQ status

| Gap in competitors | PulseIQ today | Distance |
| --- | --- | --- |
| One-way scribes (note in, nothing out; no pull of past records) | Visits are stored per account and per patient; the Patients timeline groups screenings, saved visits and notes for the same name. SOAP note + `/extract-entities` produce structured output, and `/fhir-export` turns the encounter into a FHIR R4 Bundle (ADR-019). | Export only — still no live connection to an EHR system. |
| Black-box risk scores — AI guesses a missing variable quietly | Deterministic calculators only: risk band from 13 mapped model inputs with per-feature attribution; `attribution_agent` puts a guideline source under every suggestion; `plan_confidence` says "Not enough information yet" instead of inventing; reference-range flags always show matched text + reference + explanation. | Add HEART / CHA₂DS₂-VASc / GRACE calculators as deterministic modules (zero cost, listed in the no-cost assessment). |
| Scribes *record* medications but never check them (no allergy, renal or interaction safety net) | Documented medications are parsed (names, brands, doses) and the new `/medication-review` returns options, allergy/condition/laboratory blocks and interaction alerts — each naming the fact that triggered it (`triggered_by`, `blocks[].trigger`), with an alternative route behind every allergy block and missing inputs reported instead of assumed. | Curated cardiac drug table only: no full formulary, no pricing, no paediatric dosing. Extending the table is a data edit in `agents/pharmacology_agent.py`. |
| Scribes only hear audio — no ECG/echo/Holter waveforms | Report *text* is screened (`/screen-report`: labs, ECG statements, EF, critical-first) and report images are analysed. | Raw waveform ingestion is the PTB-XL/1D-CNN proposal — needs dataset + training, higher cost tier. |
| Coding/denial friction (CPT, HCC) | Nothing yet. | Out of scope at zero cost: CPT code tables are AMA-licensed; HCC mapping needs CMS GEMs. Documented as future work. |

## The three "standout architecture" pillars — honest scorecard

1. **Inspectable reasoning (white-box)** — **Have.** Guideline source under every suggestion, confidence badge with an explicit insufficient-information state, per-feature model attribution, lab flags with matched_text/reference/explanation, deterministic SOAP notes, a medication review where every option and block names its trigger, and the evaluation harness to measure it. This is the strongest pillar and the natural paper story.
2. **Bi-directional EHR sync (structured write-backs)** — **Exportable, not synced.** Structured fields are parsed (medications, durations, risk factors, EF and lab values from report text), SOAP notes are structured, and the consultation screen now exports the encounter as a FHIR R4 Bundle (ADR-019): `Patient`, `Practitioner`, `Encounter`, `Condition`, `Observation`, `AllergyIntolerance`, `MedicationStatement`, `DetectedIssue` and `DocumentReference`, with the zero-cost step the assessment named (Condition/Observation/DocumentReference) inside it. Everything inferred is marked provisional/unconfirmed and carries the decision-support disclaimer; no code is guessed and no terminology server is called. Still nothing is pushed into a hospital system — that needs the system and its API contract, not more code.
3. **Multimodal ingestion (audio + waveforms)** — **Partial.** Speech in nine languages + report text + report images + body map already merge into one patient context. Raw ECG/Holter signal is the compute-bound tier (PTB-XL fine-tune).

## Feature-level gaps worth building (zero cost, ranked by leverage)

1. **Deterministic risk calculators (HEART, CHA₂DS₂-VASc, GRACE, ASCVD)** — directly answers EvidenceMD's "verifiable risk scores" pitch; inputs are already extracted.
2. **Drug-interaction layer** — medication extraction with doses already exists (`medical_entities.py`); add a rule-based contraindication/double-check layer over the extracted list (e.g. antiplatelet + anticoagulant stacking). Pure rules, no model.
3. **Referral letter + pre-op clearance templates** — the SOAP builder pattern extends to letters; documentation burden is the number-one clinician complaint.
4. **Longitudinal comparison** — Patients timeline exists; add "visit over visit" deltas for labs/EF when the same patient name recurs.
5. **FHIR export** — **Done.** `POST /fhir-export` + the "Export FHIR JSON" action on the consultation screen emit the bundle above (ADR-019). Remaining distance is the integration itself, not the format.
6. **White-box as the brand** — surface the source *and* the confidence everywhere (done in the last wave); publish the calibration/ECE numbers from the evaluation harness.

## Where PulseIQ is already differentiated vs. both categories

- Runs fully on-device (Ollama) — the enterprise scribes are all cloud; privacy by architecture.
- Self-learning clinician vocabulary (teach/correct phrases, per-account overlay).
- De-identification before storage with an audit trail (ADR-016) + recorded consent gate.
- Urdu/Roman-Urdu pain-characteristic extraction alongside English.
- Deterministic, auditable outputs (SOAP, lab flags, attribution) rather than generative guesses.

## Out of scope at zero cost (documented, not dismissed)

- **CPT/HCC coding support** — AMA-licensed code tables; needs a licensing decision.
- **Live EHR integration** — needs a hospital system and its API contracts.
- **Raw waveform deep learning** — dataset download + GPU-class training time.
- **Federated/DP learning** — single site today; future-work paragraph for the paper.
