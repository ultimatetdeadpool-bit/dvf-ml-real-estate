"""
DVF Real Estate — model training with MLflow tracking.

Target : Valeur fonciere (sale price in €)
Models :
  1. Baseline  — DummyRegressor (median strategy)
  2. Ridge     — Ridge regression with standard scaling
  3. LightGBM  — Gradient boosting (efficient on tabular data)

Scope : residential transactions (Maison / Appartement) with known price,
        capped at 10 M€ to exclude encoding errors found in the QA step.
"""

import warnings
warnings.filterwarnings("ignore")

import pandas as pd
import numpy as np
import mlflow
import mlflow.sklearn
import mlflow.lightgbm
import time

from sklearn.model_selection import train_test_split
from sklearn.dummy import DummyRegressor
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler, OrdinalEncoder
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    mean_absolute_error, mean_squared_error, r2_score,
    mean_absolute_percentage_error,
)
import lightgbm as lgb

# ── Config ─────────────────────────────────────────────────────────────────────
CSV_PATH   = r"C:\Users\USER\Downloads\mycsvfile.csv"
EXPERIMENT = "DVF_Price_Prediction"
SAMPLE_N   = 300_000   # rows after filtering — fast enough, representative enough
RANDOM_STATE = 42
TEST_SIZE    = 0.2
PRICE_CAP    = 10_000_000   # from QA: above this are likely encoding errors
PRICE_FLOOR  = 1_000        # below this are symbolic / non-market transfers

# ── Load & clean ───────────────────────────────────────────────────────────────
print("Loading data …")
t0 = time.time()
df = pd.read_csv(
    CSV_PATH,
    sep=",",
    low_memory=False,
    decimal=",",
    usecols=[
        "Valeur fonciere", "Type local", "Surface reelle bati",
        "Nombre pieces principales", "Surface terrain",
        "Code departement", "Code postal", "Commune",
        "Nombre de lots", "Nature mutation",
    ],
)
print(f"  Loaded {len(df):,} rows in {time.time()-t0:.1f}s")

# Keep residential only and filter out QA-flagged price outliers
df = df[df["Type local"].isin(["Maison", "Appartement"])].copy()
df = df.dropna(subset=["Valeur fonciere"])
df["Valeur fonciere"] = pd.to_numeric(df["Valeur fonciere"], errors="coerce")
df = df[(df["Valeur fonciere"] >= PRICE_FLOOR) & (df["Valeur fonciere"] <= PRICE_CAP)]

# Surface terrain: some rows are strings due to mixed decimal formats
df["Surface terrain"] = pd.to_numeric(df["Surface terrain"], errors="coerce")

# Cap extreme surface values found in QA
df["Surface reelle bati"] = pd.to_numeric(df["Surface reelle bati"], errors="coerce").clip(upper=2000)
df["Surface terrain"]     = df["Surface terrain"].clip(upper=100_000)

print(f"  After filtering: {len(df):,} residential rows")

# Reproducible sample
df = df.sample(n=min(SAMPLE_N, len(df)), random_state=RANDOM_STATE).reset_index(drop=True)
print(f"  Working sample : {len(df):,} rows")

# ── Features ───────────────────────────────────────────────────────────────────
TARGET = "Valeur fonciere"
NUM_FEATURES = ["Surface reelle bati", "Nombre pieces principales",
                "Surface terrain", "Nombre de lots"]
CAT_FEATURES = ["Type local", "Code departement", "Nature mutation"]

X = df[NUM_FEATURES + CAT_FEATURES]
y = np.log1p(df[TARGET])   # log-transform price for better regression behaviour

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=TEST_SIZE, random_state=RANDOM_STATE
)
print(f"  Train: {len(X_train):,}  |  Test: {len(X_test):,}\n")

# ── Preprocessor (shared by Ridge) ────────────────────────────────────────────
num_pipe = Pipeline([
    ("impute", SimpleImputer(strategy="median")),
    ("scale",  StandardScaler()),
])
cat_pipe = Pipeline([
    ("impute",  SimpleImputer(strategy="most_frequent")),
    ("encode",  OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)),
])
preprocessor = ColumnTransformer([
    ("num", num_pipe, NUM_FEATURES),
    ("cat", cat_pipe, CAT_FEATURES),
])

# LightGBM preprocessor (no scaling needed, but still needs imputation)
lgb_num_pipe = Pipeline([("impute", SimpleImputer(strategy="median"))])
lgb_cat_pipe = Pipeline([
    ("impute",  SimpleImputer(strategy="most_frequent")),
    ("encode",  OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)),
])
lgb_preprocessor = ColumnTransformer([
    ("num", lgb_num_pipe, NUM_FEATURES),
    ("cat", lgb_cat_pipe, CAT_FEATURES),
])

# ── Metric helper ──────────────────────────────────────────────────────────────
LOG_FLOOR = np.log1p(PRICE_FLOOR)   # ~6.91
LOG_CAP   = np.log1p(PRICE_CAP)     # ~16.12

def compute_metrics(y_true_log, y_pred_log):
    """Compute metrics in log space and original price space.
    Predictions are clipped to the valid log-price range before conversion
    so that models without built-in output bounds (e.g. Ridge) are evaluated
    fairly without catastrophic RMSE inflation from a handful of wild outliers.
    """
    y_pred_log_clipped = np.clip(y_pred_log, LOG_FLOOR, LOG_CAP)
    y_true = np.expm1(y_true_log)
    y_pred = np.expm1(y_pred_log_clipped)
    return {
        "mae":      round(mean_absolute_error(y_true, y_pred), 2),
        "rmse":     round(np.sqrt(mean_squared_error(y_true, y_pred)), 2),
        "r2":       round(r2_score(y_true, y_pred), 4),
        "mape":     round(mean_absolute_percentage_error(y_true, y_pred) * 100, 2),
        "log_mae":  round(mean_absolute_error(y_true_log, y_pred_log), 4),
        "log_rmse": round(np.sqrt(mean_squared_error(y_true_log, y_pred_log)), 4),
    }

# ── MLflow setup ───────────────────────────────────────────────────────────────
mlflow.set_tracking_uri("file:./mlruns")
mlflow.set_experiment(EXPERIMENT)

results = []

# ══════════════════════════════════════════════════════════════════════════════
# MODEL 1 — Baseline (DummyRegressor)
# ══════════════════════════════════════════════════════════════════════════════
print("Training Model 1: Baseline (DummyRegressor / median) …")
with mlflow.start_run(run_name="01_Baseline_DummyRegressor"):
    params = {"strategy": "median"}
    mlflow.log_params(params)
    mlflow.log_param("sample_size", len(X_train))
    mlflow.log_param("features", NUM_FEATURES + CAT_FEATURES)

    t = time.time()
    model = DummyRegressor(strategy="median")
    model.fit(X_train, y_train)
    train_time = round(time.time() - t, 3)

    y_pred = model.predict(X_test)
    metrics = compute_metrics(y_test.values, y_pred)

    mlflow.log_metrics(metrics)
    mlflow.log_metric("train_time_s", train_time)
    mlflow.sklearn.log_model(model, "model", input_example=X_test.head(3))

    run_id = mlflow.active_run().info.run_id
    results.append({"Model": "Baseline (Dummy median)", **metrics,
                    "train_time_s": train_time, "run_id": run_id})
    print(f"  MAE={metrics['mae']:,.0f}€  RMSE={metrics['rmse']:,.0f}€  "
          f"R²={metrics['r2']}  MAPE={metrics['mape']}%  [{train_time}s]")

# ══════════════════════════════════════════════════════════════════════════════
# MODEL 2 — Ridge Regression
# ══════════════════════════════════════════════════════════════════════════════
print("Training Model 2: Ridge Regression …")
with mlflow.start_run(run_name="02_Ridge_Regression"):
    params = {"alpha": 10.0, "max_iter": 1000}
    mlflow.log_params(params)
    mlflow.log_param("sample_size", len(X_train))
    mlflow.log_param("features", NUM_FEATURES + CAT_FEATURES)
    mlflow.log_param("preprocessor", "StandardScaler + OrdinalEncoder + median imputer")

    t = time.time()
    model = Pipeline([
        ("prep",  preprocessor),
        ("model", Ridge(**params)),
    ])
    model.fit(X_train, y_train)
    train_time = round(time.time() - t, 3)

    y_pred = model.predict(X_test)
    metrics = compute_metrics(y_test.values, y_pred)

    mlflow.log_metrics(metrics)
    mlflow.log_metric("train_time_s", train_time)
    mlflow.sklearn.log_model(model, "model", input_example=X_test.head(3))

    run_id = mlflow.active_run().info.run_id
    results.append({"Model": "Ridge Regression (a=10)", **metrics,
                    "train_time_s": train_time, "run_id": run_id})
    print(f"  MAE={metrics['mae']:,.0f}€  RMSE={metrics['rmse']:,.0f}€  "
          f"R²={metrics['r2']}  MAPE={metrics['mape']}%  [{train_time}s]")

# ══════════════════════════════════════════════════════════════════════════════
# MODEL 3 — LightGBM
# ══════════════════════════════════════════════════════════════════════════════
print("Training Model 3: LightGBM …")
with mlflow.start_run(run_name="03_LightGBM"):
    lgb_params = {
        "n_estimators":    800,
        "learning_rate":   0.05,
        "num_leaves":      127,
        "max_depth":       -1,
        "min_child_samples": 30,
        "subsample":       0.8,
        "colsample_bytree": 0.8,
        "reg_alpha":       0.1,
        "reg_lambda":      1.0,
        "n_jobs":          -1,
        "random_state":    RANDOM_STATE,
        "verbose":         -1,
    }
    mlflow.log_params(lgb_params)
    mlflow.log_param("sample_size", len(X_train))
    mlflow.log_param("features", NUM_FEATURES + CAT_FEATURES)
    mlflow.log_param("preprocessor", "median imputer + OrdinalEncoder")

    t = time.time()

    # Fit preprocessor on train, transform both splits
    X_train_lgb = lgb_preprocessor.fit_transform(X_train)
    X_test_lgb  = lgb_preprocessor.transform(X_test)

    lgb_model = lgb.LGBMRegressor(**lgb_params)
    lgb_model.fit(
        X_train_lgb, y_train,
        eval_set=[(X_test_lgb, y_test)],
        callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(0)],
    )
    train_time = round(time.time() - t, 3)

    y_pred = lgb_model.predict(X_test_lgb)
    metrics = compute_metrics(y_test.values, y_pred)

    mlflow.log_metrics(metrics)
    mlflow.log_metric("train_time_s", train_time)
    mlflow.log_metric("best_iteration", lgb_model.best_iteration_)
    mlflow.lightgbm.log_model(lgb_model, "model")

    # Feature importances
    feat_names = (
        NUM_FEATURES
        + [f"cat_{c}" for c in CAT_FEATURES]
    )
    importances = dict(zip(feat_names, lgb_model.feature_importances_))
    mlflow.log_dict(importances, "feature_importances.json")

    run_id = mlflow.active_run().info.run_id
    results.append({"Model": "LightGBM", **metrics,
                    "train_time_s": train_time, "run_id": run_id})
    print(f"  MAE={metrics['mae']:,.0f}€  RMSE={metrics['rmse']:,.0f}€  "
          f"R²={metrics['r2']}  MAPE={metrics['mape']}%  [{train_time}s]")
    print(f"  Best iteration: {lgb_model.best_iteration_}")

# ── Comparison table ───────────────────────────────────────────────────────────
print("\n" + "=" * 80)
print("EXPERIMENT COMPARISON")
print("=" * 80)

cmp = pd.DataFrame(results).set_index("Model")
display_cols = ["mae", "rmse", "r2", "mape", "log_mae", "log_rmse", "train_time_s"]
table = cmp[display_cols].copy()
table.columns = ["MAE (€)", "RMSE (€)", "R²", "MAPE (%)", "Log-MAE", "Log-RMSE", "Time (s)"]

# Highlight best values
print(table.to_string(
    float_format=lambda x: f"{x:,.4f}" if abs(x) < 10 else f"{x:,.0f}"
).encode("ascii", errors="replace").decode("ascii"))

# Improvement of LightGBM over baseline
baseline_mae  = cmp.loc["Baseline (Dummy median)", "mae"]
lgb_mae       = cmp.loc["LightGBM", "mae"]
improvement   = (baseline_mae - lgb_mae) / baseline_mae * 100
print(f"\nLightGBM MAE improvement over Baseline: {improvement:.1f}%")

# Save table to CSV
table.to_csv(r"C:\Users\USER\ml-project\comparison_table.csv")
print("\nComparison table saved -> comparison_table.csv")
print("MLflow UI: run  mlflow ui --backend-store-uri file:./mlruns  then open http://127.0.0.1:5000")
