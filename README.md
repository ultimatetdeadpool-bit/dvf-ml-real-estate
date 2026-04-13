# Machine Learning with Real Data — DVF Real Estate Project

A complete, beginner-friendly ML project using 16 million rows of French government
property-transaction data (DVF — Demandes de Valeurs Foncières).

## What this project covers

| Step | Topic |
|---|---|
| 1 | Loading a large, messy CSV with pandas |
| 2 | Data quality audit: missing values, duplicates, outliers |
| 3 | Automated quality tests with pytest (15 failing tests = your cleaning backlog) |
| 4 | Feature engineering & train/test split |
| 5 | Baseline model (DummyRegressor) |
| 6 | Ridge Regression with scikit-learn pipelines |
| 7 | LightGBM gradient boosting with early stopping |
| 8 | Experiment tracking with MLflow |
| 9 | Reading MAE / RMSE / R² / MAPE |

## Results

| Model | MAE (€) | RMSE (€) | R² | MAPE (%) | Train time |
|---|---|---|---|---|---|
| Baseline (Dummy median) | 241,559 | 857,108 | -0.042 | 107% | 0.004s |
| Ridge Regression | 232,751 | 841,168 | -0.003 | 105% | 0.42s |
| **LightGBM** | **168,539** | **641,242** | **0.417** | **80%** | **17.5s** |

LightGBM achieves a **30% MAE reduction** over the baseline.

## Project structure

```
ml-project/
├── data_quality_check.py    # Audit script — runs quality analysis, saves JSON
├── test_data_quality.py     # 15 pytest tests (all intentionally failing)
├── train_models.py          # Trains 3 models, logs everything to MLflow
├── build_docx.py            # Generates the tutorial document
├── ML_Project_Tutorial.docx # Step-by-step teaching guide
├── quality_results.json     # Quality audit output
├── comparison_table.csv     # Model comparison table
└── mlruns/                  # MLflow experiment store
```

## Quick start

```bash
# 1. Install dependencies
pip install pandas numpy scikit-learn lightgbm mlflow pytest python-docx

# 2. Download the dataset and place it at:
#    C:\Users\USER\Downloads\mycsvfile.csv

# 3. Run data quality audit
python data_quality_check.py

# 4. Run failing tests
pytest test_data_quality.py -v

# 5. Train all 3 models (takes ~3 min for 300k rows)
python train_models.py

# 6. Open the MLflow UI
mlflow ui --backend-store-uri file:./mlruns
# -> http://127.0.0.1:5000
```

## Dataset

**DVF — Demandes de Valeurs Foncières**
Published by the French government (data.gouv.fr).  
16,306,439 rows × 43 columns. Every property transaction registered by notaries.

**Prediction target:** `Valeur fonciere` — sale price in euros.

**Features used (7):**
- `Surface reelle bati` — built area (m²)
- `Nombre pieces principales` — room count
- `Surface terrain` — land area (m²)
- `Nombre de lots` — number of lots
- `Type local` — Maison / Appartement
- `Code departement` — French region code
- `Nature mutation` — transaction type

## Key data quality findings

- **8 columns are 100% null** — never populated in this extract
- **188,526 null prices** (1.16%) — rows that can't be used for supervised learning
- **638,222 exact duplicate rows** — inflate aggregates
- **Max price = 2,086,000,000 €** — clear encoding error, capped at 10M€
- **Surface Carrez max = 9,999 m²** — sentinel value in French cadastral software

## Learning resources

The file `ML_Project_Tutorial.docx` contains a full step-by-step explanation of
everything done in this project, written to teach machine learning concepts from
scratch using this real dataset.

## License

Data: Open License (Licence Ouverte) — French government open data.  
Code: MIT.
