"""
core/soil_pressure.py
Contact pressure analysis for isolated footings.

Sign convention (SI, kN, m, kPa):
  N  – axial force positive = compression (downward)
  Mx – moment about X axis  (causes differential pressure in Y direction)
  My – moment about Y axis  (causes differential pressure in X direction)
  Vx, Vy – horizontal shears (used for stability, not pressure)

Footing plan:
  B = dimension in X direction
  L = dimension in Y direction
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np

from core.loads import LoadCombination


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class SoilProperties:
    qa: float                           # allowable bearing pressure [kPa]
    gamma_soil: float                   # unit weight of soil [kN/m³]
    Df: float                           # embedment depth [m]
    qu: Optional[float] = None          # ultimate bearing capacity [kPa] (optional)
    ks: Optional[float] = None          # subgrade modulus [kN/m³] (optional)
    water_table_depth: Optional[float] = None  # depth to water table [m]


@dataclass
class FootingGeometry:
    B: float                            # width in X [m]
    L: float                            # length in Y [m]
    h: float                            # total thickness [m]
    bx: float                           # column/pedestal dimension in X [m]
    by: float                           # column/pedestal dimension in Y [m]
    cover: float = 0.075                # clear cover [m]
    pedestal_height: Optional[float] = None  # height of pedestal [m] if any
    ex: float = 0.0                     # column eccentricity in X from footing centre [m]
    ey: float = 0.0                     # column eccentricity in Y from footing centre [m]


@dataclass
class PressureResult:
    combo_name: str
    q_max: float                        # maximum contact pressure [kPa]
    q_min: float                        # minimum contact pressure [kPa]
    eccentricity_x: float               # resultant eccentricity in X [m]
    eccentricity_y: float               # resultant eccentricity in Y [m]
    full_contact: bool                  # True = no tension zone
    effective_area: float               # effective contact area [m²]
    contact_ratio: float                # fraction of base area in contact (0–1)
    passes_qa: bool                     # True if q_max ≤ qa
    N_total: float                      # total vertical load including self-weight [kN]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def compute_total_load(
    combo: LoadCombination,
    geom: FootingGeometry,
    soil: SoilProperties,
    gamma_concrete: float = 24.0,
    include_soil_weight: bool = True,
) -> Tuple[float, float, float]:
    """
    Return (N_total, Mx_total, My_total).

    N_total = N_applied + W_footing + W_soil_above_footing

    Soil weight is computed as the weight of soil *above* the footing (excluding
    the footing volume itself).  That is, the soil block B×L×(Df-h) plus the
    contribution of the footing own weight B×L×h×γ_conc.

    Moments include transfer from horizontal shear using e = Df, plus any
    contribution from column eccentricity if ex/ey ≠ 0.
    """
    A = geom.B * geom.L

    # Self-weight of footing
    W_footing = A * geom.h * gamma_concrete

    # Weight of soil above footing
    W_soil = 0.0
    if include_soil_weight:
        soil_depth = max(soil.Df - geom.h, 0.0)
        W_soil = A * soil_depth * soil.gamma_soil

    N_total = combo.N + W_footing + W_soil

    # Additional moment from horizontal shear using e = Df (user convention).
    # Df is measured from the top of pedestal to ground level in this model.
    Mx_total = combo.Mx + combo.Vy * soil.Df + combo.N * geom.ey
    My_total = combo.My + combo.Vx * soil.Df + combo.N * geom.ex

    return N_total, Mx_total, My_total


def compute_eccentricities(
    N_total: float,
    Mx_total: float,
    My_total: float,
) -> Tuple[float, float]:
    """
    Return (ex, ey) where ex = My/N, ey = Mx/N.

    Raises ValueError if N_total ≤ 0 (uplift case).
    """
    if N_total <= 0.0:
        raise ValueError(
            f"N_total = {N_total:.3f} kN ≤ 0 — uplift condition. "
            "Stability must be checked separately."
        )
    ex = My_total / N_total
    ey = Mx_total / N_total
    return ex, ey


def check_full_contact(
    ex: float,
    ey: float,
    B: float,
    L: float,
) -> bool:
    """
    Kern condition: full contact when |ex| ≤ B/6 AND |ey| ≤ L/6.
    """
    return abs(ex) <= B / 6.0 and abs(ey) <= L / 6.0


def compute_pressures_full_contact(
    N_total: float,
    Mx_total: float,
    My_total: float,
    B: float,
    L: float,
) -> Tuple[float, float, float, float]:
    """
    Corner pressures for full-contact case.

    q = N/A ± Mx·(L/2)/Ix ± My·(B/2)/Iy

    Returns (q_max, q_min, q_avg, q_corner_xx_yy) where q_corner is
    the absolute magnitude of the combined bending term.
    """
    A = B * L
    Ix = B * L**3 / 12.0  # second moment about X axis [m⁴]
    Iy = L * B**3 / 12.0  # second moment about Y axis [m⁴]

    q_avg = N_total / A
    dq_x = abs(My_total) * (B / 2.0) / Iy   # pressure variation in X
    dq_y = abs(Mx_total) * (L / 2.0) / Ix   # pressure variation in Y

    q_max = q_avg + dq_x + dq_y
    q_min = q_avg - dq_x - dq_y
    q_corner = dq_x + dq_y

    return q_max, q_min, q_avg, q_corner


def compute_pressures_partial_contact(
    N_total: float,
    Mx_total: float,
    My_total: float,
    B: float,
    L: float,
) -> Tuple[float, float, float]:
    """
    Partial contact (tension zone present).  Uses Meyerhof simplified
    rectangular stress block.

    For the dominant eccentricity direction:
      Effective dimension = 3 * (half_dim - |e|)
      q_max = 2·N / (other_dim × eff_dim)

    For biaxial eccentricity the reduction is applied to both directions
    using the same simplified approach (conservative).

    Returns (q_max [kPa], effective_B [m], effective_L [m])
    """
    if N_total <= 0.0:
        return 0.0, 0.0, 0.0

    ex = My_total / N_total  # eccentricity in X
    ey = Mx_total / N_total  # eccentricity in Y

    # Effective dimensions (Meyerhof) — cannot be negative
    eff_B = max(3.0 * (B / 2.0 - abs(ex)), 0.01)
    eff_L = max(3.0 * (L / 2.0 - abs(ey)), 0.01)

    # Clamp to physical footing dimensions
    eff_B = min(eff_B, B)
    eff_L = min(eff_L, L)

    q_max = 2.0 * N_total / (eff_B * eff_L)

    return q_max, eff_B, eff_L


# ---------------------------------------------------------------------------
# Main public function
# ---------------------------------------------------------------------------

def analyze_pressure(
    combo: LoadCombination,
    geom: FootingGeometry,
    soil: SoilProperties,
    gamma_concrete: float = 24.0,
    allow_partial_contact: bool = True,
    include_soil_weight: bool = True,
) -> PressureResult:
    """
    Analyse contact pressures for a single combination.

    Procedure:
    1. Compute total vertical load (N + self-weight + soil).
    2. Compute eccentricities.
    3. Determine full / partial contact.
    4. Compute q_max, q_min.
    5. Check against allowable pressure.
    """
    A_total = geom.B * geom.L

    # --- Handle uplift (N_total ≤ 0) ---
    try:
        N_total, Mx_total, My_total = compute_total_load(
            combo, geom, soil, gamma_concrete, include_soil_weight
        )
        ex, ey = compute_eccentricities(N_total, Mx_total, My_total)
    except ValueError:
        # Uplift condition — record as failed
        N_total, _, _ = compute_total_load(
            combo, geom, soil, gamma_concrete, include_soil_weight
        )
        return PressureResult(
            combo_name=combo.name,
            q_max=0.0,
            q_min=0.0,
            eccentricity_x=0.0,
            eccentricity_y=0.0,
            full_contact=False,
            effective_area=0.0,
            contact_ratio=0.0,
            passes_qa=False,
            N_total=N_total,
        )

    full_contact = check_full_contact(ex, ey, geom.B, geom.L)

    if full_contact:
        q_max, q_min, _, _ = compute_pressures_full_contact(
            N_total, Mx_total, My_total, geom.B, geom.L
        )
        eff_area = A_total
        contact_ratio = 1.0
    else:
        if not allow_partial_contact:
            # Compute the actual partial-contact pressure for reporting, but
            # mark the combination as failed because partial contact is not allowed.
            q_max, eff_B, eff_L = compute_pressures_partial_contact(
                N_total, Mx_total, My_total, geom.B, geom.L
            )
            return PressureResult(
                combo_name=combo.name,
                q_max=q_max,
                q_min=0.0,
                eccentricity_x=ex,
                eccentricity_y=ey,
                full_contact=False,
                effective_area=eff_B * eff_L,
                contact_ratio=(eff_B * eff_L) / A_total,
                passes_qa=False,
                N_total=N_total,
            )

        q_max, eff_B, eff_L = compute_pressures_partial_contact(
            N_total, Mx_total, My_total, geom.B, geom.L
        )
        q_min = 0.0  # tension zone carries no stress
        eff_area = eff_B * eff_L
        contact_ratio = eff_area / A_total

    passes_qa = q_max <= soil.qa

    return PressureResult(
        combo_name=combo.name,
        q_max=q_max,
        q_min=q_min,
        eccentricity_x=ex,
        eccentricity_y=ey,
        full_contact=full_contact,
        effective_area=eff_area,
        contact_ratio=contact_ratio,
        passes_qa=passes_qa,
        N_total=N_total,
    )


def find_critical_pressures(results: List[PressureResult]) -> dict:
    """
    Find critical combinations from a list of PressureResult objects.

    Returns a dict with keys:
      'max_qmax'    – result with highest q_max
      'min_qmin'    – result with lowest q_min
      'max_ex'      – result with largest |eccentricity_x|
      'max_ey'      – result with largest |eccentricity_y|
      'min_contact' – result with smallest contact_ratio
    """
    if not results:
        raise ValueError("Empty results list.")

    return {
        "max_qmax":    max(results, key=lambda r: r.q_max),
        "min_qmin":    min(results, key=lambda r: r.q_min),
        "max_ex":      max(results, key=lambda r: abs(r.eccentricity_x)),
        "max_ey":      max(results, key=lambda r: abs(r.eccentricity_y)),
        "min_contact": min(results, key=lambda r: r.contact_ratio),
    }
