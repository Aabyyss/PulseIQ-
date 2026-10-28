# Data attribution — `data/heart.csv`

This file is a modified copy of the **UCI Heart Disease** dataset (Cleveland
processed), distributed under the **Creative Commons Attribution 4.0
International licence (CC BY 4.0)**.

- **Dataset:** Heart Disease (Cleveland processed), UCI Machine Learning Repository, dataset 45
- **Source:** <https://archive.ics.uci.edu/dataset/45/heart-disease>
- **DOI:** [10.24432/C52P4X](https://doi.org/10.24432/C52P4X)
- **Licence:** [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) — redistribution and
  adaptation permitted, including commercially, with attribution
- **Data collected by:** the Cleveland Clinic Foundation; Robert Detrano, M.D., Ph.D.
- **Retrieved:** 2026-10-28

## Citation

> Janosi, A., Steinbrunn, W., Pfisterer, M., Detrano, R. (1988). *Heart Disease*.
> UCI Machine Learning Repository. <https://doi.org/10.24432/C52P4X>

## What this copy changes

`data/heart.csv` is not the raw file. The changes are listed here because CC BY 4.0
requires that modifications be indicated:

1. The 13 predictor columns are renamed to the names the model uses (`cp`,
   `trestbps`, `chol`, `fbs`, `restecg`, `thalach`, `exang`, `oldpeak`,
   `slope`, `ca`, `thal`).
2. The **6 records with a missing value** (`?` in `ca` ×4, `thal` ×2) are dropped rather
   than imputed, leaving 297 of the 303 source records. Imputing the two strongest
   predictors would invent the very evidence the model relies on.
3. The 0–4 angiographic severity column `num` is binarised: `target = 1` if `num > 0`
   (any disease) and `0` otherwise. 137 disease / 160 no disease.
4. Integer-valued fields are written without a trailing `.0`. No values were rescaled,
   clipped or otherwise edited, and no rows were added. This export contains **no
   exact duplicate feature vectors**.

## Provenance

`data/heart_source.json` records the source URL, retrieval date, licence, the SHA-256 of
the downloaded archive and of the member file it was built from, the transformations
above, and the label-direction check. `models/heart_model_meta.json` copies the licence
and source next to the model's metrics, and `backend/test_train_model.py` fails if the
attribution text or those fields are removed.

Rebuild it with:

```bash
python scripts/import_uci_heart.py
```

The importer pins both checksums and refuses to build a dataset from a payload that does
not match them.

## Why this replaced the previous file

The repository used to train on the widely circulated Kaggle `heart.csv`
(`johnsmith88`), which is a derivative of the same Cleveland cohort. That copy had
1,025 rows of which only 302 were distinct, and its target column was inverted; it also
carried no licence metadata this project could verify. It was replaced so that the data
in the repository is licensed, attributable, and free of the duplicate rows that had
produced a misleading ROC-AUC of 1.000. See ADR-035 and ADR-037.
