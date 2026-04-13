"""
Data quality tests for mycsvfile.csv (DVF – French real estate transactions).

Each test FAILS intentionally — it asserts the data meets a quality threshold
that the current dataset violates. The test name, docstring, and assertion
message document exactly what issue was found and how severe it is.

Run with:  pytest test_data_quality.py -v
"""

import pytest
import pandas as pd
import numpy as np

CSV_PATH = r"C:\Users\USER\Downloads\mycsvfile.csv"

# ── Shared fixture (loaded once per session) ───────────────────────────────────

@pytest.fixture(scope="session")
def df():
    return pd.read_csv(
        CSV_PATH,
        sep=",",
        low_memory=False,
        decimal=",",   # French decimal: "8000,00" → 8000.0
    )


# ══════════════════════════════════════════════════════════════════════════════
# BLOCK 1 — MISSING VALUES
# ══════════════════════════════════════════════════════════════════════════════

class TestMissingValues:

    def test_no_completely_empty_columns(self, df):
        """
        FAILS: 8 columns are 100 % null (Code service CH, Reference document,
        1–5 Articles CGI, Identifiant local).
        These columns carry no information and should either be populated or
        removed before modelling.
        Expected: 0 columns are entirely empty.
        Found:    8 columns are entirely empty.
        """
        completely_empty = [col for col in df.columns if df[col].isnull().all()]
        assert completely_empty == [], (
            f"{len(completely_empty)} columns are 100 % null and provide no value:\n"
            + "\n".join(f"  • {c}" for c in completely_empty)
        )

    def test_valeur_fonciere_no_nulls(self, df):
        """
        FAILS: 'Valeur fonciere' (sale price) has 188 526 null values (1.16 %).
        A transaction without a recorded price is unusable for valuation models.
        Expected: 0 null prices.
        Found:    188 526 null prices.
        """
        col = "Valeur fonciere"
        null_count = int(df[col].isnull().sum())
        assert null_count == 0, (
            f"'{col}' contains {null_count:,} null values "
            f"({null_count / len(df) * 100:.2f} % of rows). "
            "Every transaction must have a recorded sale price."
        )

    def test_code_postal_no_nulls(self, df):
        """
        FAILS: 'Code postal' has 151 082 null values (0.93 %).
        Postal code is needed for geolocation and regional analysis.
        Expected: 0 null postal codes.
        Found:    151 082 null postal codes.
        """
        col = "Code postal"
        null_count = int(df[col].isnull().sum())
        assert null_count == 0, (
            f"'{col}' contains {null_count:,} null values "
            f"({null_count / len(df) * 100:.2f} % of rows)."
        )

    def test_section_no_nulls(self, df):
        """
        FAILS: 'Section' (cadastral section identifier) has 525 null values.
        Section is part of the primary cadastral key; nulls break parcel lookups.
        Expected: 0 null sections.
        Found:    525 null sections.
        """
        col = "Section"
        null_count = int(df[col].isnull().sum())
        assert null_count == 0, (
            f"'{col}' contains {null_count:,} null values. "
            "Cadastral section must be present on every row."
        )

    def test_missing_rate_below_threshold(self, df):
        """
        FAILS: Many columns far exceed a 5 % acceptable missing-value threshold.
        Columns like 'Surface Carrez du 5eme lot' are 99.98 % empty.
        Expected: No column exceeds 5 % missing values.
        Found:    27 columns exceed the 5 % threshold.
        """
        threshold = 0.05
        missing_rates = df.isnull().mean()
        violating = missing_rates[missing_rates > threshold].sort_values(ascending=False)
        assert violating.empty, (
            f"{len(violating)} columns exceed {threshold*100:.0f}% missing threshold:\n"
            + "\n".join(f"  • {col}: {rate*100:.1f}%" for col, rate in violating.items())
        )

    def test_no_rows_with_all_address_fields_missing(self, df):
        """
        FAILS: Rows exist where all address fields (No voie, Type de voie,
        Code voie, Voie) are null simultaneously — the property cannot be located.
        Expected: 0 rows with every address field missing.
        Found:    rows where the full address is absent.
        """
        address_cols = ["No voie", "Type de voie", "Code voie", "Voie"]
        present = [c for c in address_cols if c in df.columns]
        all_missing_mask = df[present].isnull().all(axis=1)
        count = int(all_missing_mask.sum())
        assert count == 0, (
            f"{count:,} rows have every address field null "
            f"({present}). These properties cannot be geolocated."
        )


# ══════════════════════════════════════════════════════════════════════════════
# BLOCK 2 — DUPLICATES
# ══════════════════════════════════════════════════════════════════════════════

class TestDuplicates:

    def test_no_fully_duplicate_rows(self, df):
        """
        FAILS: 638 222 rows are exact duplicates of another row.
        These inflate counts and bias any aggregate (average price, total area).
        Expected: 0 fully duplicate rows.
        Found:    638 222 fully duplicate rows (3.91 % of dataset).
        """
        dup_count = int(df.duplicated().sum())
        assert dup_count == 0, (
            f"{dup_count:,} fully duplicate rows found "
            f"({dup_count / len(df) * 100:.2f} % of the dataset). "
            "De-duplication required before any aggregation."
        )

    def test_no_duplicate_deal_transactions(self, df):
        """
        FAILS: 4 494 590 rows share the same (Date mutation, Valeur fonciere,
        Commune, No plan, Section) — the natural key of one parcel in one sale.
        In the DVF format a single sale covers multiple rows (one per parcel /
        lot), but identical (date, price, commune, plan, section) tuples beyond
        the expected count indicate duplicated ingestion.
        Expected: 0 duplicate deal-level keys.
        Found:    4 494 590 duplicate deal keys.
        """
        deal_key = ["Date mutation", "Valeur fonciere", "Commune", "No plan", "Section"]
        key_cols = [c for c in deal_key if c in df.columns]
        dup_count = int(df.duplicated(subset=key_cols).sum())
        assert dup_count == 0, (
            f"{dup_count:,} rows are duplicates on key {key_cols}. "
            "This suggests repeated ingestion or mis-linked multi-parcel transactions."
        )

    def test_no_duplicate_plan_within_section_commune(self, df):
        """
        FAILS: (Code departement, Code commune, Section, No plan) combinations
        appear more than once — a given plot number should be unique within its
        cadastral section for a single transaction date.
        Expected: 0 such duplicates.
        Found:    Widespread duplication on the cadastral plot key.
        """
        key = ["Date mutation", "Code departement", "Code commune", "Section", "No plan"]
        key_cols = [c for c in key if c in df.columns]
        dup_count = int(df.duplicated(subset=key_cols).sum())
        assert dup_count == 0, (
            f"{dup_count:,} rows share the same cadastral plot key {key_cols}. "
            "Each plot should appear at most once per transaction date."
        )


# ══════════════════════════════════════════════════════════════════════════════
# BLOCK 3 — OUTLIERS
# ══════════════════════════════════════════════════════════════════════════════

class TestOutliers:

    def test_valeur_fonciere_no_extreme_high(self, df):
        """
        FAILS: 'Valeur fonciere' reaches 2 086 000 000 € (2.09 billion).
        The IQR upper fence is 579 600 €; 1 553 424 rows exceed it (9.64 %).
        The max value is ~3 600× the upper fence — almost certainly data entry
        errors or unit mismatches (centimes instead of euros).
        Expected: max ≤ 10 000 000 € (10 M€, a reasonable luxury property cap).
        Found:    max = 2 086 000 000 €.
        """
        col = "Valeur fonciere"
        series = df[col].dropna()
        cap = 10_000_000
        above_cap = int((series > cap).sum())
        actual_max = float(series.max())
        assert above_cap == 0, (
            f"'{col}' has {above_cap:,} values above {cap:,.0f} €. "
            f"Maximum observed: {actual_max:,.2f} €. "
            "Values above 10 M€ require manual review or represent encoding errors."
        )

    def test_valeur_fonciere_no_near_zero(self, df):
        """
        FAILS: 'Valeur fonciere' has values ≤ 1 € (e.g., 0.01 €, 1.00 €).
        Symbolic prices indicate transfers that are not arm's-length sales
        (gifts, divorces, inheritance) and distort market price models.
        Expected: 0 transactions priced at ≤ 1 €.
        Found:    multiple rows with Valeur fonciere ≤ 1.
        """
        col = "Valeur fonciere"
        series = df[col].dropna()
        low_count = int((series <= 1.0).sum())
        assert low_count == 0, (
            f"'{col}' has {low_count:,} values ≤ 1 €. "
            "These likely represent non-market transactions and must be flagged or excluded."
        )

    def test_surface_carrez_no_sentinel_values(self, df):
        """
        FAILS: 'Surface Carrez du 1er lot' reaches 9 999 m².
        9 999 is a common sentinel / overflow value in French cadastral exports.
        No residential or small commercial lot plausibly measures 9 999 m².
        Expected: all Carrez surfaces ≤ 2 000 m².
        Found:    values reaching 9 999 m².
        """
        col = "Surface Carrez du 1er lot"
        if col not in df.columns:
            pytest.skip(f"Column '{col}' not present.")
        series = df[col].dropna()
        cap = 2_000
        above_cap = int((series > cap).sum())
        actual_max = float(series.max())
        assert above_cap == 0, (
            f"'{col}' has {above_cap:,} values above {cap:,} m². "
            f"Maximum observed: {actual_max:.2f} m². "
            "Values near 9 999 are likely sentinel codes, not real measurements."
        )

    def test_nombre_de_lots_no_extreme_values(self, df):
        """
        FAILS: 'Nombre de lots' reaches 468 lots in a single transaction.
        The IQR upper fence is 2.5; 181 155 rows exceed it (1.11 %).
        A transaction with hundreds of lots is an outlier that needs review.
        Expected: max lots per transaction ≤ 50.
        Found:    max = 468 lots.
        """
        col = "Nombre de lots"
        if col not in df.columns:
            pytest.skip(f"Column '{col}' not present.")
        series = df[col].dropna()
        cap = 50
        above_cap = int((series > cap).sum())
        actual_max = float(series.max())
        assert above_cap == 0, (
            f"'{col}' has {above_cap:,} values above {cap}. "
            f"Maximum observed: {actual_max:.0f}. "
            "Transactions with > 50 lots are unusual and should be verified."
        )

    def test_surface_terrain_no_extreme_values(self, df):
        """
        FAILS: 'Surface terrain' (land area in m²) has extreme outliers.
        The IQR method flags a significant portion of values as above the upper
        fence. Very large values may indicate unit errors (hectares vs m²).
        Expected: 0 values above the IQR upper fence (Q3 + 1.5 × IQR).
        Found:    outliers present.
        """
        col = "Surface terrain"
        if col not in df.columns:
            pytest.skip(f"Column '{col}' not present.")
        series = pd.to_numeric(df[col], errors="coerce").dropna()
        q1, q3 = series.quantile(0.25), series.quantile(0.75)
        iqr = q3 - q1
        upper_fence = q3 + 1.5 * iqr
        outliers = int((series > upper_fence).sum())
        assert outliers == 0, (
            f"'{col}' has {outliers:,} values above IQR upper fence "
            f"({upper_fence:,.2f} m²). "
            f"Max observed: {series.max():,.2f} m². "
            "Large surface values may indicate unit mismatches (ha vs m²)."
        )

    def test_no_disposition_single_value(self, df):
        """
        FAILS: 'No disposition' reaches 1 271, but the IQR fence is 1.0,
        meaning almost all values are 1.  1 057 118 rows (6.48 %) exceed
        the fence.  Non-1 values may indicate multi-row transaction groupings
        that are not handled consistently.
        Expected: all 'No disposition' values == 1.
        Found:    1 057 118 rows with No disposition > 1.
        """
        col = "No disposition"
        if col not in df.columns:
            pytest.skip(f"Column '{col}' not present.")
        series = df[col].dropna()
        non_one = int((series != 1).sum())
        assert non_one == 0, (
            f"'{col}' has {non_one:,} values other than 1 "
            f"(max = {int(series.max())}). "
            "Multi-disposition transactions require explicit handling."
        )
