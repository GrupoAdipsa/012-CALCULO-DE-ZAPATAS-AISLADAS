"""
core/stability.py
Sliding, overturning, and uplift stability checks for isolated footings.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from core.loads import LoadCombination
from core.soil_pressure import FootingGeometry, SoilProperties, compute_total_load


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class StabilityParams:
    mu_friction: float = 0.45           # concrete-soil friction coefficient
    passive_pressure: bool = False      # include passive earth pressure
    Kp: float = 3.0                     # Rankine passive pressure coefficient
    reduction_passive: float = 0.5      # reduction factor applied to passive force
    FS_sliding_min: float = 1.5         # minimum FS against sliding
    FS_overturning_min: float = 1.5     # minimum FS against overturning
    FS_uplift_min: float = 1.1          # minimum FS against uplift


@dataclass
class StabilityResult:
    combo_name: str
    FS_sliding_x: float                 # FS against sliding in X direction
    FS_sliding_y: float                 # FS against sliding in Y direction
    FS_overturning_x: float             # FS against overturning about X axis (due to Mx)
    FS_overturning_y: float             # FS against overturning about Y axis (due to My)
    FS_uplift: float                    # FS against uplift
    passes_sliding_x: bool
    passes_sliding_y: bool
    passes_overturning_x: bool
    passes_overturning_y: bool
    passes_uplift: bool
    passes_all: bool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_INF = 999.0  # sentinel "infinity" FS when the destabilising force is zero


def _safe_fs(stabilising: float, destabilising: float) -> float:
    """Return FS = stabilising / destabilising, clamped to _INF when denom ≈ 0."""
    if abs(destabilising) < 1e-6:
        return _INF
    return stabilising / destabilising


# ---------------------------------------------------------------------------
# Main check
# ---------------------------------------------------------------------------

def check_stability(
    combo: LoadCombination,
    geom: FootingGeometry,
    soil: SoilProperties,
    params: StabilityParams,
    gamma_concrete: float = 24.0,
) -> StabilityResult:
    """
    Evaluate sliding, overturning, and uplift for a single load combination.

    Sliding
    -------
    Resisting force  = μ · N_total + F_passive
    Passive force (per side, if enabled) = 0.5 · Kp · γ_soil · Df² · L  (X dir)
                                           0.5 · Kp · γ_soil · Df² · B  (Y dir)
    FS_sliding_x = F_resist_x / |Vx|
    FS_sliding_y = F_resist_y / |Vy|

    Overturning
    -----------
    About X axis (destabilising = Mx + Vy·h):
      M_stabilising = N_total · (L/2)
      FS_OTX = M_stabilising / |M_destabilising_x|

    About Y axis (destabilising = My + Vx·h):
      M_stabilising = N_total · (B/2)
      FS_OTY = M_stabilising / |M_destabilising_y|

    Uplift
    ------
    Only relevant when applied N < 0.
    FS_uplift = W_total / |N_applied|  (when N_applied < 0)
    """
    N_total, Mx_total, My_total = compute_total_load(
        combo, geom, soil, gamma_concrete, include_soil_weight=True
    )

    # ------------------------------------------------------------------
    # Passive earth pressure (optional)
    # ------------------------------------------------------------------
    Fp_x = Fp_y = 0.0
    if params.passive_pressure:
        # Passive force acting on the embedded portion of the footing
        p_passive = 0.5 * params.Kp * soil.gamma_soil * soil.Df ** 2
        Fp_x = p_passive * geom.L * params.reduction_passive
        Fp_y = p_passive * geom.B * params.reduction_passive

    # ------------------------------------------------------------------
    # Sliding
    # ------------------------------------------------------------------
    friction_force = params.mu_friction * max(N_total, 0.0)

    resist_x = friction_force + Fp_x
    resist_y = friction_force + Fp_y

    FS_sliding_x = _safe_fs(resist_x, abs(combo.Vx))
    FS_sliding_y = _safe_fs(resist_y, abs(combo.Vy))

    # ------------------------------------------------------------------
    # Overturning
    # ------------------------------------------------------------------
    # About X axis — destabilising moment = Mx (incl. shear arm) about base
    M_dest_x = abs(Mx_total)
    M_dest_y = abs(My_total)

    M_stab_x = N_total * (geom.L / 2.0)   # stabilising about X (N acts over L/2)
    M_stab_y = N_total * (geom.B / 2.0)   # stabilising about Y (N acts over B/2)

    FS_overturning_x = _safe_fs(max(M_stab_x, 0.0), M_dest_x)
    FS_overturning_y = _safe_fs(max(M_stab_y, 0.0), M_dest_y)

    # ------------------------------------------------------------------
    # Uplift
    # ------------------------------------------------------------------
    if combo.N < 0.0:
        FS_uplift = _safe_fs(N_total, abs(combo.N))
    else:
        FS_uplift = _INF  # no uplift demand

    # ------------------------------------------------------------------
    # Boolean checks
    # ------------------------------------------------------------------
    passes_sx = FS_sliding_x >= params.FS_sliding_min
    passes_sy = FS_sliding_y >= params.FS_sliding_min
    passes_ox = FS_overturning_x >= params.FS_overturning_min
    passes_oy = FS_overturning_y >= params.FS_overturning_min
    passes_up = FS_uplift >= params.FS_uplift_min

    return StabilityResult(
        combo_name=combo.name,
        FS_sliding_x=FS_sliding_x,
        FS_sliding_y=FS_sliding_y,
        FS_overturning_x=FS_overturning_x,
        FS_overturning_y=FS_overturning_y,
        FS_uplift=FS_uplift,
        passes_sliding_x=passes_sx,
        passes_sliding_y=passes_sy,
        passes_overturning_x=passes_ox,
        passes_overturning_y=passes_oy,
        passes_uplift=passes_up,
        passes_all=all([passes_sx, passes_sy, passes_ox, passes_oy, passes_up]),
    )


def find_critical_stability(results: List[StabilityResult]) -> dict:
    """
    Identify the worst (minimum FS) case in each category.

    Returns a dict with keys:
      'min_FS_sliding_x', 'min_FS_sliding_y',
      'min_FS_overturning_x', 'min_FS_overturning_y',
      'min_FS_uplift'
    Each value is the corresponding StabilityResult.
    """
    if not results:
        raise ValueError("Empty results list.")

    return {
        "min_FS_sliding_x":    min(results, key=lambda r: r.FS_sliding_x),
        "min_FS_sliding_y":    min(results, key=lambda r: r.FS_sliding_y),
        "min_FS_overturning_x":min(results, key=lambda r: r.FS_overturning_x),
        "min_FS_overturning_y":min(results, key=lambda r: r.FS_overturning_y),
        "min_FS_uplift":       min(results, key=lambda r: r.FS_uplift),
    }
