# Data sources — what can legally be added

> Written 2026-10-28, after the duplicate-row correction (ADR-035). Licences
> were read from the primary source pages listed below, not from mirrors. This
> file records decisions, not data: no third-party dataset is vendored here,
> because a public repository that copies a dataset must be able to name the
> licence it is redistributing under, and this one currently cannot.

## The data in use

| | |
|---|---|
| File | `data/heart.csv` |
| Provenance | The widely circulated Kaggle `heart.csv` (`johnsmith88`), an inflated copy of the UCI Cleveland cohort |
| Rows | 1,025 — **302 distinct feature vectors**, 723 exact duplicates |
| Licence | **Not verifiable.** The Kaggle page does not expose licence metadata, so this file is not redistributable under a licence this project can name |
| Outcome | Angiographic heart disease, label inverted in the file (target 1 = healthy) |

That last row is the honest position: the dataset is in the repo as it was
supplied, and the project should not claim more than that. Anyone publishing
this repository should replace it with the UCI original (below) and a citation.

## Candidates, and what each can actually support

| Source | Licence / access | Size | Fits the 13 features? | Verdict |
|---|---|---|---|---|
| [UCI Heart Disease](https://archive.ics.uci.edu/dataset/45/heart+disease) | **CC BY 4.0** — redistribution and commercial use with attribution; no DUA, IRB or fee | 303 Cleveland; repository also has Hungarian (294), Switzerland (123), VA Long Beach (200), ~920 records across sites | **Yes — all 13**, `num` binarised to presence/absence | **The correct replacement for the Kaggle copy.** Cleveland is the same 303 patients already in `heart.csv`, so it fixes provenance, not sample size. The other sites are genuinely different cohorts but are small and have missing fields (`ca`, `thal`) |
| [UCI Statlog (Heart)](https://archive.ics.uci.edu/dataset/145/statlog+heart) | **CC BY 4.0** | 270 | Yes, after renaming (`chest-pain`, `rest-bp`, `serum-chol`, …) | **Do not pool with Cleveland.** It is the same patients in a different encoding; adding it would recreate the duplicate leak in a subtler form |
| [Z-Alizadeh Sani](https://archive.ics.uci.edu/dataset/412/z+alizadeh+sani) | **CC BY 4.0** | 303 patients | No — 54 features, different definitions | Useful only for a separate experiment, not this model's feature vector |
| [PTB-XL](https://physionet.org/content/ptb-xl/1.0.3/) | **CC BY 4.0** | 21,799 ECG records / 18,869 patients | No — ECG waveforms and metadata, not these 13 tabular features | A different task (ECG classification). Legally clean, methodologically irrelevant here |
| [NHANES](https://www.cdc.gov/nchs/nhanes/about/index.html) | US federal public domain; cite CDC | Survey cycles, not one table | Partly: age, sex, blood pressure, cholesterol; no `cp`, `thalach`, `exang`, `oldpeak`, `ca`, `thal` | Only for population-level risk work after building a documented cohort, and its outcome is not angiographic disease |
| [Framingham cohort (BioLINCC)](https://biolincc.nhlbi.nih.gov/studies/framcohort/) | Not open: registration + IRB approval; commercial use tiered | ~5,209 original cohort, repeated exams | No — different variables, 10-year CHD outcome | Out of scope without IRB and a data-use agreement |
| [MIMIC-IV](https://physionet.org/content/mimiciv/) | Credentialed Health Data License: training + DUA, research use, no redistribution | >65k ICU / 200k ED patients | Extractable proxies only | Legally possible for credentialed research; the derived data still cannot be published, which conflicts with this repo's open posture |
| [All of Us](https://support.researchallofus.org/hc/en-us/articles/22346942074132-Data-Access-Framework) | Registered/Controlled access; participant data may not be redistributed | Large, versioned | Partial proxies only | Not compatible with shipping a model and data publicly |
| [UK Biobank](https://community.ukbiobank.ac.uk/hc/en-gb/articles/28002689502237-Applying-to-UK-Biobank-and-accessing-data-FAQ) | Application + institutional MTA + fee | ~500k participants | Partial proxies only | Out of scope for a zero-budget public project |

## What would actually improve the model

1. **Provenance first, rows second.** Replace the Kaggle file with the UCI
   Cleveland original, add its citation and licence to the README, and keep the
   de-duplication (the original has duplicates of its own). This changes
   nothing about the metrics and everything about whether the repo is defensible.
2. **Then the other three UCI sites** (Hungarian, Switzerland, VA Long Beach),
   mapped to the same schema with explicit missing-value handling — `ca` and
   `thal` are absent for Long Beach and Switzerland. That is the only *free,
   same-task* way to add patients, and it should be reported per site, not
   pooled into one flattering number.
3. **Not** Statlog (same patients), not NHANES (different outcome), not PTB-XL
   (different task), not the access-controlled cohorts (cannot be redistributed).

Any of those is a research decision with a measurable cost, so it is not taken
here. The current card states 302 distinct patients, which is the real sample
size, and the calibration block shows the probability is usable on that sample.
