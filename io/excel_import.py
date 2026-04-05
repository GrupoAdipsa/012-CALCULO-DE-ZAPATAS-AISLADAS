"""
io/excel_import.py
Import load combinations from Excel files.
Supports ETABS, SAP2000, Consteel, and generic column formats.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from core.loads import LoadCombination, LoadSet


# ---------------------------------------------------------------------------
# Software detection
# ---------------------------------------------------------------------------

def detect_software_format(df: pd.DataFrame) -> str:
    """
    Heuristically detect the structural analysis software that produced the file.

    Returns one of: "etabs", "sap2000", "consteel", "generic"
    """
    cols_lower = {str(c).lower() for c in df.columns}

    etabs_markers   = {"outputcase", "steptype", "stepnum"}
    sap2000_markers = {"case", "casetype", "steptype"}
    consteel_markers = {"lcomb", "fx", "fy", "fz", "mx", "my", "mz"}

    if etabs_markers & cols_lower:
        return "etabs"
    if sap2000_markers & cols_lower:
        return "sap2000"
    if consteel_markers & cols_lower:
        return "consteel"
    return "generic"


# ---------------------------------------------------------------------------
# Column name mappers
# ---------------------------------------------------------------------------

def map_etabs_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Map ETABS reaction table columns to the standard set:
    Combo, N, Vx, Vy, Mx, My.

    Typical ETABS joint-reaction columns (kN, kN·m):
      OutputCase → Combo
      F3 (vertical) → N
      F1 → Vx, F2 → Vy
      M1 → Mx (about 1-axis), M2 → My (about 2-axis)
    """
    rename = {
        "OutputCase": "Combo",
        "F1": "Vx",
        "F2": "Vy",
        "F3": "N",
        "M1": "Mx",
        "M2": "My",
        # alternate casing
        "outputcase": "Combo",
        "f1": "Vx",
        "f2": "Vy",
        "f3": "N",
        "m1": "Mx",
        "m2": "My",
    }
    df = df.rename(columns={c: rename[c] for c in df.columns if c in rename})
    # ETABS often gives reactions as negative downward — flip N sign
    if "N" in df.columns:
        df["N"] = -df["N"]
    return df


def map_sap2000_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Map SAP2000 joint-reaction export columns to standard format.

    Typical SAP2000 columns:
      Case → Combo
      F1/U1 → Vx, F2/U2 → Vy, F3/U3 → N
      M1/R1 → Mx, M2/R2 → My
    """
    rename = {
        "Case":  "Combo",
        "case":  "Combo",
        "F1":    "Vx",
        "F2":    "Vy",
        "F3":    "N",
        "M1":    "Mx",
        "M2":    "My",
        "U1":    "Vx",
        "U2":    "Vy",
        "U3":    "N",
        "R1":    "Mx",
        "R2":    "My",
    }
    df = df.rename(columns={c: rename[c] for c in df.columns if c in rename})
    # SAP2000 reactions are also negative-downward
    if "N" in df.columns:
        df["N"] = -df["N"]
    return df


# ---------------------------------------------------------------------------
# Main importer
# ---------------------------------------------------------------------------

def import_combinations_excel(
    filepath: str,
    sheet_name: int | str = 0,
    combo_col: str = "Combo",
    N_col: str = "N",
    Vx_col: str = "Vx",
    Vy_col: str = "Vy",
    Mx_col: str = "Mx",
    My_col: str = "My",
    combo_type_col: Optional[str] = None,
    default_combo_type: str = "ultimate",
) -> LoadSet:
    """
    Import load combinations from an Excel file.

    Parameters
    ----------
    filepath            : path to .xlsx / .xls file
    sheet_name          : sheet index or name
    combo_col           : column with combination names
    N/Vx/Vy/Mx/My_col  : column names for force components
    combo_type_col      : optional column indicating "service" or "ultimate"
    default_combo_type  : used when combo_type_col is absent

    Returns
    -------
    LoadSet with all rows imported as LoadCombination objects.
    """
    df = pd.read_excel(filepath, sheet_name=sheet_name)

    # Auto-detect and remap columns
    fmt = detect_software_format(df)
    if fmt == "etabs":
        df = map_etabs_columns(df)
    elif fmt == "sap2000":
        df = map_sap2000_columns(df)

    # Normalise column names
    df.columns = [str(c).strip() for c in df.columns]

    required = [combo_col, N_col, Vx_col, Vy_col, Mx_col, My_col]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(
            f"Required columns not found in sheet: {missing}. "
            f"Available: {list(df.columns)}"
        )

    load_set = LoadSet()
    for _, row in df.iterrows():
        name = str(row[combo_col]).strip()
        if not name or name.lower() in ("nan", "none", ""):
            continue

        combo_type = default_combo_type
        if combo_type_col and combo_type_col in df.columns:
            ct = str(row[combo_type_col]).lower().strip()
            if "service" in ct or "unfactored" in ct or "asd" in ct:
                combo_type = "service"
            else:
                combo_type = "ultimate"

        combo = LoadCombination(
            name=name,
            N=float(row[N_col]),
            Vx=float(row[Vx_col]),
            Vy=float(row[Vy_col]),
            Mx=float(row[Mx_col]),
            My=float(row[My_col]),
            combo_type=combo_type,
        )
        load_set.add_combination(combo)

    return load_set
