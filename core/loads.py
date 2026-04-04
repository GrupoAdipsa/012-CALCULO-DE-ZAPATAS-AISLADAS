"""
core/loads.py
Data models for load cases and combinations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List
import pandas as pd


VALID_LOAD_TYPES = (
    "dead", "live", "roof_live",
    "wind_x", "wind_y",
    "seismic_x", "seismic_y",
    "other",
)

VALID_COMBO_TYPES = ("service", "ultimate")


@dataclass
class LoadCase:
    """Single load case with all force/moment components.

    Coordinate convention (SI units, kN, kN·m):
      N  – axial force, positive = compression (downward)
      Vx – shear in X direction [kN]
      Vy – shear in Y direction [kN]
      Mx – bending moment about X axis [kN·m]  (causes pressure variation in Y)
      My – bending moment about Y axis [kN·m]  (causes pressure variation in X)
    """

    name: str
    N: float
    Vx: float
    Vy: float
    Mx: float
    My: float
    load_type: str = "other"

    def __post_init__(self) -> None:
        if self.load_type not in VALID_LOAD_TYPES:
            raise ValueError(
                f"Invalid load_type '{self.load_type}'. "
                f"Must be one of {VALID_LOAD_TYPES}."
            )

    def scale(self, factor: float) -> "LoadCase":
        """Return a new LoadCase with all components multiplied by *factor*."""
        return LoadCase(
            name=self.name,
            N=self.N * factor,
            Vx=self.Vx * factor,
            Vy=self.Vy * factor,
            Mx=self.Mx * factor,
            My=self.My * factor,
            load_type=self.load_type,
        )


@dataclass
class LoadCombination:
    """Pre-computed (or imported) load combination."""

    name: str
    N: float
    Vx: float
    Vy: float
    Mx: float
    My: float
    combo_type: str  # "service" or "ultimate"

    def __post_init__(self) -> None:
        if self.combo_type not in VALID_COMBO_TYPES:
            raise ValueError(
                f"Invalid combo_type '{self.combo_type}'. "
                f"Must be one of {VALID_COMBO_TYPES}."
            )


class LoadSet:
    """Container for load cases and pre-computed combinations."""

    def __init__(self) -> None:
        self._cases: List[LoadCase] = []
        self._combinations: List[LoadCombination] = []

    # ------------------------------------------------------------------ #
    # Mutation helpers
    # ------------------------------------------------------------------ #

    def add_case(self, case: LoadCase) -> None:
        """Append a load case to the collection."""
        if not isinstance(case, LoadCase):
            raise TypeError(f"Expected LoadCase, got {type(case).__name__}")
        self._cases.append(case)

    def add_combination(self, combo: LoadCombination) -> None:
        """Append a pre-computed combination."""
        if not isinstance(combo, LoadCombination):
            raise TypeError(
                f"Expected LoadCombination, got {type(combo).__name__}"
            )
        self._combinations.append(combo)

    # ------------------------------------------------------------------ #
    # Accessors
    # ------------------------------------------------------------------ #

    @property
    def cases(self) -> List[LoadCase]:
        return list(self._cases)

    @property
    def combinations(self) -> List[LoadCombination]:
        return list(self._combinations)

    def get_case_by_type(self, load_type: str) -> List[LoadCase]:
        """Return all cases with the given load_type."""
        return [c for c in self._cases if c.load_type == load_type]

    def get_service_combos(self) -> List[LoadCombination]:
        """Return only service-level combinations."""
        return [c for c in self._combinations if c.combo_type == "service"]

    def get_ultimate_combos(self) -> List[LoadCombination]:
        """Return only strength/ultimate combinations."""
        return [c for c in self._combinations if c.combo_type == "ultimate"]

    # ------------------------------------------------------------------ #
    # DataFrame export
    # ------------------------------------------------------------------ #

    def to_dataframe(self) -> pd.DataFrame:
        """Return all combinations as a pandas DataFrame."""
        rows = []
        for combo in self._combinations:
            rows.append(
                {
                    "name": combo.name,
                    "combo_type": combo.combo_type,
                    "N [kN]": combo.N,
                    "Vx [kN]": combo.Vx,
                    "Vy [kN]": combo.Vy,
                    "Mx [kN·m]": combo.Mx,
                    "My [kN·m]": combo.My,
                }
            )
        return pd.DataFrame(rows)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"LoadSet(cases={len(self._cases)}, "
            f"combinations={len(self._combinations)})"
        )
