# Medication catalogue and interaction table

Generated from `agents/pharmacology_agent.py` — the tables are the source of truth, this page is how a
reviewer reads them without opening the module. `backend/test_pharmacology_agent.py` fails when an
entry here would be untrue: a missing source, an unresolvable id, a duplicate key or a rule that no
drug or class can reach.

- **36 drug options**, each with indications, gates, allergens, monitoring, a dose note and sources.
- **53 interaction rules**, each naming at least one source.
- **12 sources**, all with a publisher URL.

## How an option is decided

`review_medications()` maps the captured facts to tags (conditions, histories, lab thresholds), looks
up which indications those tags satisfy, and then blocks, flags or offers each option. An option is
offered when *any* of its indications is present, so a drug that needs two facts together gets a
compound indication (`diabetic_kidney_disease`, `pregnancy_hypertension`,
`residual_hypertriglyceridaemia`) rather than a list of tags that would fire on either one.

## Sources

| id | citation | url |
|---|---|---|
| `ccd-2023` | 2023 AHA/ACC/ACCP/ASPC/NLA/PCNA Guideline for the Management of Patients With Chronic Coronary Disease | <https://www.ahajournals.org/doi/10.1161/CIR.0000000000001168> |
| `hf-2022` | 2022 AHA/ACC/HFSA Guideline for the Management of Heart Failure | <https://www.ahajournals.org/doi/10.1161/CIR.0000000000001063> |
| `acs-2025` | 2025 ACC/AHA/ACEP/NAEMSP/SCAI Guideline for the Management of Patients With Acute Coronary Syndromes | <https://www.ahajournals.org/doi/10.1161/CIR.0000000000001309> |
| `af-2023` | 2023 ACC/AHA/ACCP/HRS Guideline for the Diagnosis and Management of Atrial Fibrillation | <https://www.ahajournals.org/doi/10.1161/CIR.0000000000001193> |
| `cholesterol-2018` | 2018 AHA/ACC/Multisociety Guideline on the Management of Blood Cholesterol | <https://www.ahajournals.org/doi/10.1161/CIR.0000000000000625> |
| `hypertension-2017` | 2017 ACC/AHA/AAPA/ABC/ACPM/AGS/APhA/ASH/ASPC/NMA/PCNA Guideline for the Prevention, Detection, Evaluation, and Management of High Blood Pressure in Adults | <https://www.ahajournals.org/doi/10.1161/hyp.0000000000000065> |
| `primary-prevention-2019` | 2019 ACC/AHA Guideline on the Primary Prevention of Cardiovascular Disease | <https://www.ahajournals.org/doi/10.1161/CIR.0000000000000678> |
| `ckd-2024` | KDIGO 2024 Clinical Practice Guideline for the Evaluation and Management of Chronic Kidney Disease | <https://doi.org/10.1016/j.kint.2023.10.018> |
| `ada-2025` | Standards of Care in Diabetes—2025 (American Diabetes Association) | <https://diabetesjournals.org/care/issue/48/Supplement_1> |
| `acog-222` | Gestational Hypertension and Preeclampsia: ACOG Practice Bulletin, Number 222 | <https://doi.org/10.1097/AOG.0000000000003891> |
| `gold-2025` | Global Strategy for the Prevention, Diagnosis and Management of COPD: 2025 Report (GOLD) | <https://goldcopd.org/2025-gold-report/> |
| `label` | FDA prescribing information (DailyMed) — drug-specific interactions and dose limits | <https://dailymed.nlm.nih.gov/dailymed/> |

## Drug options

| option | class | priority | indications | sources |
|---|---|---|---|---|
| Aspirin (`aspirin`) | `antiplatelet` | 1 | `suspected_acs`, `established_cad`, `prior_mi`, `prior_pci_cabg`, `cerebrovascular_disease` | `acs-2025` |
| Nitrate (sublingual GTN) (`nitrate`) | `nitrate` | 1 | `suspected_acs`, `established_cad` | `ccd-2023`, `acs-2025` |
| Clopidogrel (P2Y12 inhibitor) (`clopidogrel`) | `p2y12` | 2 | `suspected_acs`, `prior_pci_cabg` | `acs-2025` |
| High-intensity statin (atorvastatin/rosuvastatin) (`statin_high_intensity`) | `statin` | 2 | `suspected_acs`, `established_cad`, `prior_mi`, `prior_pci_cabg`, `dyslipidemia`, `dyslipidemia_lab`, `non_hdl_high`, `diabetes`, `cerebrovascular_disease` | `cholesterol-2018`, `ccd-2023` |
| Loop diuretic (furosemide) (`loop_diuretic`) | `loop_diuretic` | 2 | `congestion`, `heart_failure` | `hf-2022` |
| Moderate-intensity statin (primary prevention) (`statin_primary_prevention`) | `statin` | 2 | `ascvd_intermediate_risk` | `primary-prevention-2019`, `cholesterol-2018` |
| Ticagrelor (P2Y12 inhibitor) (`ticagrelor`) | `p2y12` | 2 | `suspected_acs`, `prior_pci_cabg` | `acs-2025` |
| ACE inhibitor (ramipril/lisinopril) (`ace_inhibitor`) | `ace_inhibitor` | 3 | `heart_failure`, `reduced_ef`, `prior_mi`, `hypertension`, `diabetes`, `chronic_kidney_disease` | `hf-2022`, `ckd-2024` |
| ARNI (sacubitril/valsartan) (`arni`) | `arni` | 3 | `heart_failure`, `reduced_ef` | `hf-2022` |
| Anticoagulant (apixaban/warfarin) (`anticoagulant`) | `anticoagulant` | 3 | `atrial_fibrillation`, `cerebrovascular_disease` | `af-2023` |
| Beta-blocker (metoprolol/bisoprolol/carvedilol) (`beta_blocker`) | `beta_blocker` | 3 | `suspected_acs`, `established_cad`, `prior_mi`, `heart_failure`, `reduced_ef`, `atrial_fibrillation` | `ccd-2023`, `hf-2022` |
| Labetalol (pregnancy hypertension) (`labetalol`) | `beta_blocker` | 3 | `pregnancy_hypertension` | `acog-222`, `hypertension-2017` |
| ARB (losartan/valsartan) (`arb`) | `arb` | 4 | `heart_failure`, `reduced_ef`, `hypertension`, `diabetes`, `chronic_kidney_disease` | `hf-2022` |
| Ezetimibe (`ezetimibe`) | `cholesterol_absorption_inhibitor` | 4 | `dyslipidemia`, `dyslipidemia_lab`, `non_hdl_high`, `ldl_very_high`, `statin_intolerance`, `established_cad`, `prior_mi` | `cholesterol-2018` |
| Finerenone (non-steroidal MRA) (`finerenone`) | `nonsteroidal_mra` | 4 | `diabetic_kidney_disease` | `ckd-2024`, `ada-2025` |
| Mineralocorticoid receptor antagonist (spironolactone) (`mra`) | `mra` | 4 | `heart_failure`, `reduced_ef` | `hf-2022` |
| Non-dihydropyridine CCB (diltiazem/verapamil) (`nd_ccb`) | `nd_ccb` | 4 | `atrial_fibrillation`, `atrial_fibrillation_symptomatic`, `hypertension` | `af-2023`, `hypertension-2017` |
| Calcium-channel blocker (amlodipine) (`ccb`) | `ccb` | 5 | `hypertension`, `established_cad` | `ccd-2023` |
| GLP-1 receptor agonist (semaglutide/dulaglutide) (`glp1_ra`) | `glp1_ra` | 5 | `diabetes`, `obesity`, `diabetes_with_ascvd` | `ada-2025`, `ccd-2023` |
| Icosapent ethyl (purified EPA) (`icosapent_ethyl`) | `omega3` | 5 | `residual_hypertriglyceridaemia` | `ccd-2023` |
| Ivabradine (`ivabradine`) | `sinus_node_inhibitor` | 5 | `heart_failure`, `reduced_ef` | `hf-2022`, `ccd-2023` |
| Metformin (`metformin`) | `biguanide` | 5 | `diabetes` | `ada-2025` |
| PCSK9 inhibitor (evolocumab/alirocumab) (`pcsk9_inhibitor`) | `pcsk9_inhibitor` | 5 | `familial_hypercholesterolemia`, `ldl_very_high`, `statin_intolerance` | `cholesterol-2018` |
| SGLT2 inhibitor (dapagliflozin/empagliflozin) (`sglt2_inhibitor`) | `sglt2_inhibitor` | 5 | `heart_failure`, `reduced_ef`, `diabetes`, `chronic_kidney_disease` | `hf-2022`, `ada-2025` |
| Bempedoic acid (`bempedoic_acid`) | `acl_inhibitor` | 6 | `statin_intolerance`, `ldl_very_high` | `label` |
| Colchicine (low dose) (`colchicine`) | `anti_inflammatory` | 6 | `established_cad`, `prior_mi` | `ccd-2023` |
| Digoxin (`digoxin`) | `cardiac_glycoside` | 6 | `atrial_fibrillation_symptomatic` | `af-2023` |
| Fenofibrate (`fenofibrate`) | `fibrate` | 6 | `triglycerides_severe`, `pancreatitis` | `cholesterol-2018` |
| Hydralazine with isosorbide dinitrate (`hydralazine_isosorbide`) | `vasodilator` | 6 | `heart_failure`, `reduced_ef` | `hf-2022` |
| Proton-pump inhibitor (pantoprazole) (`ppi`) | `ppi` | 6 | `antithrombotic_bleeding_risk` | `ccd-2023`, `label` |
| Ranolazine (`ranolazine`) | `antianginal` | 6 | `refractory_angina` | `ccd-2023` |
| Thiazide-like diuretic (chlorthalidone/indapamide) (`thiazide`) | `thiazide` | 6 | `hypertension` | `hypertension-2017` |
| Amiodarone (`amiodarone`) | `antiarrhythmic` | 7 | `atrial_fibrillation_symptomatic` | `af-2023` |
| Dronedarone (`dronedarone`) | `antiarrhythmic` | 7 | `atrial_fibrillation`, `atrial_fibrillation_symptomatic` | `af-2023` |
| Flecainide (`flecainide`) | `antiarrhythmic` | 8 | `atrial_fibrillation_symptomatic` | `af-2023` |
| NSAIDs (ibuprofen/diclofenac) (`nsaid`) | `nsaid` | 8 | `avoid_advice` | `ccd-2023`, `label` |

## Interaction rules

| pair | severity | action | sources |
|---|---|---|---|
| `p2y12` + `anticoagulant` | major | Use only with a defined indication and stop date; add gastroprotection and review at each visit. | `acs-2025`, `af-2023` |
| `aspirin` + `anticoagulant` | major | Combine only with a clear indication (e.g. recent stent); add gastroprotection and set a stop date. | `af-2023` |
| `aspirin` + `p2y12` | major | Use only per ACS/PCI protocol, and document the planned duration. | `acs-2025` |
| `aspirin` + `nsaid` | major | Avoid NSAIDs; use paracetamol for analgesia. | `ccd-2023`, `label` |
| `nsaid` + `anticoagulant` | major | Avoid NSAIDs; if unavoidable add gastroprotection (generally not recommended). | `label`, `af-2023` |
| `nsaid` + `ace_inhibitor` | moderate | Avoid where possible; if used, check creatinine and potassium within a week. | `ckd-2024` |
| `nsaid` + `arb` | moderate | Avoid where possible; monitor renal function if used. | `ckd-2024` |
| `nsaid` + `loop_diuretic` | moderate | Avoid; review diuretic dose if NSAIDs are unavoidable. | `label`, `hf-2022` |
| `ace_inhibitor` + `mra` | major | Check potassium and creatinine at 1 and 4 weeks; stop if K+ >5.5 mmol/L. | `hf-2022`, `ckd-2024` |
| `arb` + `mra` | major | Check potassium and creatinine at 1 and 4 weeks. | `hf-2022` |
| `ace_inhibitor` + `arb` | major | Use one agent only. | `hf-2022` |
| `beta_blocker` + `nd_ccb` | major | Avoid the combination; amlodipine is the safe calcium-channel option here. | `label`, `af-2023` |
| `statin_high_intensity` + `amiodarone` | major | Cap simvastatin at 20 mg, or switch to rosuvastatin/pravastatin and warn about muscle pain. | `label` |
| `amiodarone` + `anticoagulant` | major | Reduce the anticoagulant dose and monitor INR/bleeding closely. | `label` |
| `amiodarone` + `digoxin` | major | Halve the digoxin dose and check the level. | `label` |
| `digoxin` + `loop_diuretic` | moderate | Monitor potassium and digoxin level; replace potassium as needed. | `label`, `hf-2022` |
| `nitrate` + `pde5_inhibitor` | major | Contraindicated — separate by at least 24 h (48 h for tadalafil) and counsel the patient. | `label`, `ccd-2023` |
| `clopidogrel` + `ppi` | moderate | Use pantoprazole when gastroprotection is needed alongside clopidogrel. | `label`, `ccd-2023` |
| `metformin` + `loop_diuretic` | moderate | Hold metformin during acute illness or aggressive diuresis. | `ada-2025`, `label` |
| `arni` + `ace_inhibitor` | major | Never combine them: stop the ACE inhibitor and wait 36 hours before the first ARNI dose. | `hf-2022`, `label` |
| `arni` + `arb` | major | Use one RAAS strategy only; the ARNI replaces the ARB. | `hf-2022` |
| `arni` + `mra` | major | Check potassium and creatinine at 1 and 4 weeks; stop if K+ >5.5 mmol/L. | `hf-2022` |
| `ivabradine` + `nd_ccb` | major | Avoid the combination; if rate control is the goal, choose one agent. | `label` |
| `ivabradine` + `beta_blocker` | moderate | Titrate against resting heart rate and review for symptomatic bradycardia. | `hf-2022` |
| `colchicine` + `statin` | major | Warn about muscle pain; check CK if symptoms appear, and reduce the colchicine dose in renal impairment. | `label` |
| `colchicine` + `nd_ccb` | major | Halve the colchicine dose or avoid the combination; review blood counts. | `label` |
| `ranolazine` + `nd_ccb` | major | Avoid the combination; if ranolazine is needed, choose a rate-control agent that is not a CYP3A4 inhibitor. | `label` |
| `ranolazine` + `statin` | major | Cap simvastatin at 20 mg or use a statin without this interaction, and warn about muscle pain. | `label` |
| `ranolazine` + `amiodarone` | major | Review the ECG/QTc before combining them and avoid other QT-prolonging drugs. | `label` |
| `dronedarone` + `amiodarone` | major | Use one rhythm-control agent; specialist input before any switch. | `label`, `af-2023` |
| `dronedarone` + `digoxin` | major | Halve the digoxin dose and check the level. | `label` |
| `dronedarone` + `statin` | major | Cap simvastatin at 10 mg or switch to a statin without this interaction. | `label` |
| `dronedarone` + `anticoagulant` | moderate | Review the anticoagulant dose and bleeding risk at each visit. | `label`, `af-2023` |
| `dronedarone` + `beta_blocker` | moderate | Check rate and ECG before and after starting either agent. | `label`, `af-2023` |
| `dronedarone` + `nd_ccb` | major | Avoid the combination; if rate control is needed, review the whole antiarrhythmic plan. | `label` |
| `flecainide` + `amiodarone` | major | Specialist input only; monitor QRS and QTc closely if both are used. | `label`, `af-2023` |
| `flecainide` + `nd_ccb` | major | Avoid combining them unless a specialist is supervising. | `label` |
| `flecainide` + `beta_blocker` | moderate | Review the ECG for QRS widening and bradycardia after titration. | `label`, `af-2023` |
| `ticagrelor` + `statin` | moderate | Cap simvastatin at 40 mg or use a statin without this interaction. | `label` |
| `ticagrelor` + `digoxin` | moderate | Check the digoxin level and monitor for toxicity when starting or stopping. | `label` |
| `thiazide` + `loop_diuretic` | moderate | Reserve the combination for resistant oedema, with electrolytes checked within a week. | `label`, `hf-2022` |
| `thiazide` + `digoxin` | moderate | Monitor potassium, sodium and the digoxin level; replace electrolytes as needed. | `label`, `af-2023` |
| `thiazide` + `nsaid` | moderate | Avoid where possible; check creatinine and electrolytes within a week if used. | `label`, `ckd-2024` |
| `icosapent_ethyl` + `anticoagulant` | moderate | Monitor for bleeding after starting; review the anticoagulant indication. | `label`, `ccd-2023` |
| `fenofibrate` + `statin` | major | Use the lowest effective doses, warn about muscle pain, and check CK if symptoms appear. | `label`, `cholesterol-2018` |
| `fenofibrate` + `anticoagulant` | major | Check INR more often after starting or changing the dose. | `label` |
| `bempedoic_acid` + `statin` | moderate | Review muscle symptoms and CK if they appear; the combination is used when LDL remains above goal. | `label` |
| `finerenone` + `ace_inhibitor` | major | Check potassium and eGFR at 4 weeks and after any dose change; stop if K+ >5.5 mmol/L. | `ckd-2024` |
| `finerenone` + `arb` | major | Check potassium and eGFR at 4 weeks; hold finerenone during acute illness. | `ckd-2024` |
| `finerenone` + `mra` | major | Use one MRA only; switch rather than stacking. | `ckd-2024`, `hf-2022` |
| `hydralazine_isosorbide` + `pde5_inhibitor` | major | Contraindicated — separate by at least 24 h (48 h for tadalafil) and counsel the patient. | `label`, `hf-2022` |
| `nd_ccb` + `statin` | moderate | Cap simvastatin at 10 mg or use a statin without this interaction. | `label` |
| `nd_ccb` + `digoxin` | moderate | Reduce the digoxin dose and monitor the level and heart rate. | `label`, `af-2023` |

## Adding an option

1. Add the tag the indication needs to `CONDITION_PATTERNS` or `lab_tags` — an entry nothing can
   trigger is dead weight, and the tests only check that the structures are sound, not that a
   clinician can reach them.
2. Add the `DRUGS` entry with the gates (`avoid`, `caution`, `lab_guards`), the aliases in
   `MED_ALIASES`, an alternative in `_ALLERGY_ALTERNATIVES`, and at least one id from `SOURCES`.
3. Add each interaction rule the option creates, also sourced. A rule naming a key, class or alias
   nothing produces will fail the invariant test.
4. Add a directional test: the fact in, the option or block out.

