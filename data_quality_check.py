"""
Data quality analysis for mycsvfile.csv (DVF - French real estate transactions).
Checks: missing values, duplicates, outliers (IQR method).
"""

import pandas as pd
import numpy as np
import json

CSV_PATH = r"C:\Users\USER\Downloads\mycsvfile.csv"

print("Loading dataset...")
df = pd.read_csv(
    CSV_PATH,
    sep=",",
    low_memory=False,
    decimal=",",         # French decimal format: "8000,00" -> 8000.0
    thousands=None,
)

print(f"Shape: {df.shape[0]:,} rows x {df.shape[1]} columns\n")

# ── 1. MISSING VALUES ──────────────────────────────────────────────────────────
print("=" * 60)
print("1. MISSING VALUES")
print("=" * 60)

missing = df.isnull().sum()
missing_pct = (missing / len(df) * 100).round(2)
missing_df = pd.DataFrame({
    "missing_count": missing,
    "missing_pct": missing_pct,
}).sort_values("missing_pct", ascending=False)

cols_with_missing = missing_df[missing_df["missing_count"] > 0]
print(cols_with_missing.to_string())
print(f"\nTotal columns with missing values: {len(cols_with_missing)}")
print(f"Total rows with at least one missing value: {df.isnull().any(axis=1).sum():,}")

# Critical columns that must not be null
critical_cols = ["Date mutation", "Nature mutation", "Valeur fonciere",
                 "Code postal", "Commune", "Code departement"]
print("\nCritical column nulls:")
for col in critical_cols:
    if col in df.columns:
        n = df[col].isnull().sum()
        print(f"  {col}: {n:,} nulls ({n/len(df)*100:.2f}%)")

# ── 2. DUPLICATES ──────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("2. DUPLICATES")
print("=" * 60)

full_dupes = df.duplicated().sum()
print(f"Fully duplicate rows: {full_dupes:,}")

# Key-level duplicates: same mutation should have same reference document
key_cols = [c for c in ["Reference document", "No plan", "Section",
                         "Code departement", "Code commune"] if c in df.columns]
key_dupes = df.duplicated(subset=key_cols).sum()
print(f"Duplicate on key cols {key_cols}: {key_dupes:,}")

# Same (Date mutation + Valeur fonciere + Commune + No plan) = same deal, same parcel
deal_key = [c for c in ["Date mutation", "Valeur fonciere", "Commune", "No plan", "Section"]
            if c in df.columns]
deal_dupes = df.duplicated(subset=deal_key).sum()
print(f"Duplicate on deal key {deal_key}: {deal_dupes:,}")

# ── 3. OUTLIERS (IQR) ─────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("3. OUTLIERS (IQR method, factor=1.5)")
print("=" * 60)

numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
print(f"Numeric columns: {numeric_cols}\n")

outlier_summary = {}
for col in numeric_cols:
    series = df[col].dropna()
    if len(series) == 0:
        continue
    q1, q3 = series.quantile(0.25), series.quantile(0.75)
    iqr = q3 - q1
    lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    n_out = ((series < lower) | (series > upper)).sum()
    pct = n_out / len(series) * 100
    outlier_summary[col] = {
        "q1": round(q1, 2), "q3": round(q3, 2), "iqr": round(iqr, 2),
        "lower_fence": round(lower, 2), "upper_fence": round(upper, 2),
        "outlier_count": int(n_out), "outlier_pct": round(pct, 2),
        "min": round(float(series.min()), 2), "max": round(float(series.max()), 2),
    }
    print(f"{col}:")
    print(f"  range=[{series.min():.2f}, {series.max():.2f}]  "
          f"IQR fences=[{lower:.2f}, {upper:.2f}]  "
          f"outliers={n_out:,} ({pct:.2f}%)")

# ── SAVE RESULTS ──────────────────────────────────────────────────────────────
results = {
    "shape": {"rows": int(df.shape[0]), "cols": int(df.shape[1])},
    "missing": {
        col: {"count": int(missing[col]), "pct": float(missing_pct[col])}
        for col in cols_with_missing.index
    },
    "critical_missing": {
        col: int(df[col].isnull().sum())
        for col in critical_cols if col in df.columns
    },
    "duplicates": {
        "full_duplicates": int(full_dupes),
        "key_duplicates": int(key_dupes),
        "deal_duplicates": int(deal_dupes),
    },
    "outliers": outlier_summary,
}

with open(r"C:\Users\USER\ml-project\quality_results.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)

print("\nResults saved to quality_results.json")
