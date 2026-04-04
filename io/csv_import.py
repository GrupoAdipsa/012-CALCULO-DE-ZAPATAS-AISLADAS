"""
io/csv_import.py
Import load combinations from CSV files.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from core.loads import LoadCombination, LoadSet


def import_combinations_csv(
    filepath: str,
    separator: str = ",",
    combo_col: str = "Combo",
    N_col: str = "N",
    Vx_col: str = "Vx",
    Vy_col: str = "Vy",
    Mx_col: str = "Mx",
    My_col: str = "My",
    combo_type_col: Optional[str] = None,
    default_combo_type: str = "ultimate",
    **kwargs,
) -> LoadSet:
    """
    Import load combinations from a CSV file.

    The CSV must have at minimum the columns specified by the *_col parameters
    (or their default names: Combo, N, Vx, Vy, Mx, My).

    Parameters
    ----------
    filepath           : path to CSV file
    separator          : field delimiter (default ",")
    combo_col          : column with combination names
    N/Vx/Vy/Mx/My_col : column names for force/moment components [kN, kN·m]
    combo_type_col     : optional column for "service"/"ultimate" classification
    default_combo_type : fallback combo type if combo_type_col is absent
    **kwargs           : passed to pd.read_csv

    Returns
    -------
    LoadSet populated with LoadCombination objects from each row.
    """
    df = pd.read_csv(filepath, sep=separator, **kwargs)
    df.columns = [str(c).strip() for c in df.columns]

    required = [combo_col, N_col, Vx_col, Vy_col, Mx_col, My_col]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(
            f"Required columns not found: {missing}. "
            f"Available columns: {list(df.columns)}"
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
