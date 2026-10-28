# Data sources — what can legally be added

> Written 2026-10-28, after the duplicate-row correction (ADR-035) and the
> dataset replacement (ADR-037). Licences were read from the primary source
> pages listed below, not from mirrors. Every dataset in this file was assessed
> for whether it can be redistributed in a public repository — more than half
> of them cannot, whatever their research value.

## The data in use

| | |
|---|---|
| File | `data/heart.csv`, built by `scripts/import_uci_heart.py` |
| Provenance | **UCI Heart Disease, Cleveland processed** (dataset 45) |
| Licence | **CC BY 4.0** — redistribution and commercial use with attribution |
| Citation | Janosi, Steinbrunn, Pfisterer, Detrano (1988), doi:10.24432/C52P4X |
| Attribution | [`data/ATTRIBUTION.md`](../data/ATTRIBUTION.md), shipped with the data |
| Rows | 303 source records; **297** after dropping 6 with a missing `ca`/`thal`; no duplicate vectors |
| Outcome | Angiographic disease: `target = 1` when `num > 0` |
| Integrity | Archive and member SHA-256 pinned in the importer; CSV SHA-256 recorded in `heart_model_meta.json` |

This replaced the widely circulated Kaggle `heart.csv`, which was a derivative
of the same Cleveland cohort: 1,025 rows of which only 302 were distinct, an
inverted target, and no licence metadata this project could verify. Its
duplicate rows are what produced the withdrawn ROC-AUC of 1.000.

If the dataset is ever swapped again, `backend/test_feature_encoding.py` fails
when the codebook changes (it asserts the categorical domains against the file),
and `backend/test_train_model.py` fails if the attribution, source fields or
split rule disappear.

## Candidates, and what each can actually support

| Source | Licence / access | Size | Fits the 13 features? | Verdict |
|---|---|---|---|---|
| [UCI Heart Disease](https://archive.ics.uci.edu/dataset/45/heart+disease) | **CC BY 4.0** — redistribution and commercial use with attribution; no DUA, IRB or fee | 303 Cleveland; repository also has Hungarian (294), Switzerland (123), VA Long Beach (200), ~920 records across sites | **Yes — all 13**, `num` binarised to presence/absence | **In use (Cleveland).** The other sites are genuinely different cohorts but small and missing `ca`/`thal`; they would need per-site reporting and explicit missingness handling |
| [UCI Statlog (Heart)](https://archive.ics.uci.edu/dataset/145/statlog+heart) | **CC BY 4.0** | 270 | Yes, after renaming (`chest-pain`, `rest-bp`, `serum-chol`, …) | **Do not pool with Cleveland.** It is the same patients in a different encoding; adding it would recreate the duplicate leak in a subtler form |
| [Z-Alizadeh Sani](https://archive.ics.uci.edu/dataset/412/z+alizadeh+sani) | **CC BY 4.0** | 303 patients | No — 54 features, different definitions | Useful only for a separate experiment, not this model's feature vector |
| [PTB-XL](https://physionet.org/content/ptb-xl/1.0.3/) | **CC BY 4.0** | 21,799 ECG records / 18,869 patients | No — ECG waveforms and metadata, not these 13 tabular features | A different task (ECG classification). Legally clean, methodologically irrelevant here |
| [NHANES](https://www.cdc.gov/nchs/nhanes/about/index.html) | US federal public domain; cite CDC | Survey cycles, not one table | Partly: age, sex, blood pressure, cholesterol; no `cp`, `thalach`, `exang`, `oldpeak`, `ca`, `thal` | Only for population-level risk work after building a documented cohort, and its outcome is not angiographic disease |
| [Framingham cohort (BioLINCC)](https://biolincc.nhlbi.nih.gov/studies/framcohort/) | Not open: registration + IRB approval; commercial use tiered | ~5,209 original cohort, repeated exams | No — different variables, 10-year CHD outcome | Out of scope without IRB and a data-use agreement |
| [MIMIC-IV](https://physionet.org/content/mimiciv/) | Credentialed Health Data License: training + DUA, research use, no redistribution | >65k ICU / 200k ED patients | Extractable proxies only | Legally possible for credentialed research; the derived data still cannot be published, which conflicts with this repo's open posture |
| [All of Us](https://support.researchallofus.org/hc/en-us/articles/22346942074132-Data-Access-Framework) | Registered/Controlled access; participant data may not be redistributed | Large, versioned | Partial proxies only | Not compatible with shipping a model and data publicly |
| [UK Biobank](https://community.ukbiobank.ac.uk/hc/en-gb/articles/28002689502237-Applying-to-UK-Biobank-and-accessing-data-FAQ) | Application + institutional MTA + fee | ~500k participants | Partial proxies only | Out of scope for a zero-budget public project |

## What would actually improve the model

1. **Provenance — done (ADR-037).** The data is now the UCI Cleveland original
   with its licence, citation, hashes and modifications shipped alongside it.
   Sample size is honestly 297 patients, not 1,025 rows.
2. **Then the other three UCI sites** (Hungarian, Switzerland, VA Long Beach),
   mapped to the same schema with explicit missing-value handling — `ca` and
   `thal` are absent for Long Beach and Switzerland. That is the only *free,
   same-task* way to add patients, and it should be reported per site, not
   pooled into one flattering number.
3. **Not** Statlog (same patients), not NHANES (different outcome), not PTB-XL
   (different task), not the access-controlled cohorts (cannot be redistributed).

Adding the other sites is a research decision with a measurable cost, so it is
not taken here. The card states 297 distinct patients, which is the real sample
size, and the calibration block shows the probability is usable on that sample.
