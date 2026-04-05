"""
core/rc_design.py
Reinforced-concrete design of isolated footings per ACI 318-19 (SI units).

Units throughout this module (unless stated otherwise):
  Forces : kN
  Moments: kN·m
  Lengths: m for geometry, mm for rebar / section design
  Stress : MPa
  Areas  : mm² (for steel), m² (for footing plan)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

from core.loads import LoadCombination
from core.soil_pressure import FootingGeometry, PressureResult, SoilProperties


# ---------------------------------------------------------------------------
# Material and rebar data
# ---------------------------------------------------------------------------

@dataclass
class MaterialProperties:
    fc: float                       # concrete f'c [MPa]
    fy: float                       # steel fy [MPa]
    gamma_concrete: float = 24.0    # unit weight [kN/m³]
    units: str = "SI"               # "SI" or "imperial"
    Es: float = 200_000.0           # steel modulus [MPa]
    phi_flexure: float = 0.90
    phi_shear: float = 0.75
    phi_bearing: float = 0.65


@dataclass
class RebarData:
    diameter: float     # bar diameter [mm]
    area: float         # bar cross-sectional area [mm²]
    name: str           # designation e.g. "#4", "Ø16"


# Standard metric US rebar (ASTM A615)
REBAR_DATABASE: Dict[str, RebarData] = {
    "#3":  RebarData( 9.525,  71.26, "#3"),
    "#4":  RebarData(12.700, 129.00, "#4"),
    "#5":  RebarData(15.875, 200.00, "#5"),
    "#6":  RebarData(19.050, 284.00, "#6"),
    "#7":  RebarData(22.225, 387.00, "#7"),
    "#8":  RebarData(25.400, 510.00, "#8"),
    "#9":  RebarData(28.575, 645.00, "#9"),
    "#10": RebarData(32.260, 819.00, "#10"),
}


# ---------------------------------------------------------------------------
# Design result
# ---------------------------------------------------------------------------

@dataclass
class DesignResult:
    # Flexure – X direction (steel running in X, bending in Y plane)
    Mu_x: float             # design moment [kN·m/m]
    As_req_x: float         # required area [mm²/m]
    As_prov_x: float        # provided area [mm²/m]
    bar_x: str
    spacing_x: float        # bar spacing [mm]
    phi_Mn_x: float         # flexural capacity [kN·m/m]
    passes_flexure_x: bool

    # Flexure – Y direction
    Mu_y: float
    As_req_y: float
    As_prov_y: float
    bar_y: str
    spacing_y: float
    phi_Mn_y: float
    passes_flexure_y: bool

    # One-way shear – X direction (critical section at d from column face in X)
    Vu_x: float             # design shear [kN/m]
    phi_Vc_x: float         # shear capacity [kN/m]
    passes_shear_x: bool

    # One-way shear – Y direction
    Vu_y: float
    phi_Vc_y: float
    passes_shear_y: bool

    # Two-way (punching) shear
    Vu2way: float           # total punching shear [kN]
    phi_Vc2way: float       # punching capacity [kN]
    passes_punching: bool

    # Effective depths
    dx: float               # effective depth for X-direction steel [mm]
    dy: float               # effective depth for Y-direction steel [mm]

    passes_all: bool


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def effective_depth(
    h: float,
    cover: float,
    bar_d: float,
    layer: int = 1,
) -> float:
    """
    Effective depth in mm.

    Parameters
    ----------
    h     : footing thickness [m]
    cover : clear cover [m]
    bar_d : bar diameter [mm]
    layer : 1 = outermost (bottom) layer, 2 = second layer
    """
    h_mm    = h * 1000.0
    cov_mm  = cover * 1000.0
    d = h_mm - cov_mm - bar_d / 2.0 - (layer - 1) * bar_d
    return max(d, 1.0)


def _beta1(fc: float) -> float:
    """ACI 318-19 Table 22.2.2.4.3 – rectangular stress-block factor β₁."""
    if fc <= 28.0:
        return 0.85
    return max(0.85 - 0.05 * (fc - 28.0) / 7.0, 0.65)


# ---------------------------------------------------------------------------
# Flexure design
# ---------------------------------------------------------------------------

def design_flexure_ACI(
    Mu: float,
    b: float = 1000.0,
    d: float = 500.0,
    fc: float = 21.0,
    fy: float = 420.0,
    phi: float = 0.90,
    rho_min_override: Optional[float] = None,
) -> Tuple[float, float]:
    """
    Design flexure per ACI 318-19.

    Parameters (SI, mm, MPa, kN·m/m)
    -----------
    Mu  : factored moment per unit width [kN·m/m]
    b   : strip width [mm]  (1000 for per-metre design)
    d   : effective depth [mm]
    fc  : [MPa]
    fy  : [MPa]
    phi : strength reduction factor

    Returns
    -------
    (As_required [mm²/m], rho_required)

    Notes
    -----
    Iterative solution of: Mu = φ·As·fy·(d - a/2)
    where a = As·fy / (0.85·f'c·b).

    Minimum steel per ACI 318-19 §9.6.1.2 (slabs):
      As_min = max(0.0018·b·h, 3√f'c/fy·b·d, 200/fy·b·d)
    (we use the slab/footing provision — 0.0018·b·h for Grade 420 / 60 ksi)
    """
    Mu_Nmm = Mu * 1.0e6  # convert kN·m/m → N·mm/m

    h_approx = d / 0.9  # approximate total depth for As_min

    # Minimum steel (ACI 318-19 §9.6.1.2 for slabs/footings)
    if rho_min_override is not None:
        As_min = rho_min_override * b * d
    else:
        # ACI 318-19 §9.6.1.2 (beam) and §8.6.1.2 / §13.3.3.2 (slab/footing)
        # SI units: fy in MPa; "200/fy" is the imperial form → use 1.4/fy in SI
        As_min = max(
            0.0018 * b * h_approx,          # temperature & shrinkage (slab/footing)
            0.25 * math.sqrt(fc) / fy * b * d,  # ACI 318-19 §9.6.1.2a
            1.4 / fy * b * d,               # ACI 318-19 §9.6.1.2b (SI equivalent of 200/fy psi)
        )

    if Mu_Nmm <= 0.0:
        return As_min, As_min / (b * d)

    # Iterative solution
    As = Mu_Nmm / (phi * fy * 0.9 * d)  # initial estimate (a ≈ 0.1d)
    for _ in range(20):
        a = As * fy / (0.85 * fc * b)
        As_new = Mu_Nmm / (phi * fy * (d - a / 2.0))
        if abs(As_new - As) < 0.01:
            As = As_new
            break
        As = As_new

    As_req = max(As, As_min)
    rho = As_req / (b * d)

    return As_req, rho


# ---------------------------------------------------------------------------
# Shear checks
# ---------------------------------------------------------------------------

def check_one_way_shear_ACI(
    Vu: float,
    b: float = 1000.0,
    d: float = 500.0,
    fc: float = 21.0,
    phi: float = 0.75,
    As: float = 0.0,
    rho_w: Optional[float] = None,
) -> Tuple[float, bool]:
    """
    One-way (beam) shear per ACI 318-19 Table 22.5.5.1.

    Simplified:  Vc = 0.17·λ·√f'c·bw·d  [N]  (λ=1 for normal weight)

    When rho_w is provided or As > 0 the detailed formula is used:
      Vc = (0.66·λ·(ρ_w)^(1/3)·√f'c + Nu/(6·Ag)) · bw · d

    Parameters
    ----------
    Vu   : factored shear [kN/m]
    b    : width [mm]
    d    : effective depth [mm]
    fc   : [MPa]
    phi  : 0.75
    As   : provided steel area [mm²/m]
    rho_w: optional; if None computed from As and b·d

    Returns
    -------
    (phi_Vc [kN/m], passes)
    """
    Vu_N = Vu * 1000.0  # kN/m → N/m

    rho = rho_w if rho_w is not None else (As / (b * d) if d > 0 else 0.0)
    rho = max(rho, 1e-6)

    # ACI 318-19 Eq. 22.5.5.1 (detailed, no axial compression)
    vc = 0.66 * 1.0 * (rho ** (1.0 / 3.0)) * math.sqrt(fc)  # [MPa]
    # Minimum simplified baseline
    vc_simple = 0.17 * math.sqrt(fc)
    vc = max(vc, vc_simple)

    Vc_N = vc * b * d  # [N/m] for 1-m strip
    phi_Vc_kN = phi * Vc_N / 1000.0  # [kN/m]

    return phi_Vc_kN, Vu <= phi_Vc_kN


def check_punching_shear_ACI(
    Vu_punching: float,
    c1: float,
    c2: float,
    d: float,
    fc: float,
    phi: float = 0.75,
    Mu_unbalanced: float = 0.0,
    alpha_s: int = 40,
) -> Tuple[float, bool]:
    """
    Two-way (punching) shear per ACI 318-19 §22.6.5.

    Critical perimeter at d/2 from column face:
      bo = 2·(c1 + d) + 2·(c2 + d)

    Three limits (ACI 318-19 Table 22.6.5.2):
      vc1 = 0.33·√f'c                            basic
      vc2 = (0.17 + 0.083·β_col)·√f'c           aspect ratio
      vc3 = (0.083·αs·d/bo + 0.17)·√f'c         column location

    vc = min(vc1, vc2, vc3)
    φVc = φ · vc · bo · d  [kN]

    Parameters (mm, MPa, kN)
    ----------
    Vu_punching   : net punching shear force [kN]
    c1, c2        : column dimensions [mm]
    d             : average effective depth [mm]
    alpha_s       : 40 interior, 30 edge, 20 corner
    """
    bo = 2.0 * (c1 + d) + 2.0 * (c2 + d)  # [mm]

    beta_col = max(c1, c2) / min(c1, c2) if min(c1, c2) > 0 else 1.0

    vc1 = 0.33 * math.sqrt(fc)
    vc2 = (0.17 + 0.083 * beta_col) * math.sqrt(fc)
    vc3 = (0.083 * alpha_s * d / bo + 0.17) * math.sqrt(fc)

    vc = min(vc1, vc2, vc3)  # [MPa]

    Vc_N = vc * bo * d          # [N]
    phi_Vc_kN = phi * Vc_N / 1000.0  # [kN]

    return phi_Vc_kN, Vu_punching <= phi_Vc_kN


# ---------------------------------------------------------------------------
# Rebar selection
# ---------------------------------------------------------------------------

def select_rebar(
    As_req: float,
    available_bars: Optional[List[str]] = None,
    s_max: float = 450.0,
    s_min: float = 75.0,
) -> Tuple[str, float, float]:
    """
    Select bar size and spacing for a given required area [mm²/m].

    Strategy: for each bar size (ascending diameter), compute spacing:
      s = 1000 · A_bar / As_req
    Accept the first bar where s_min ≤ s ≤ s_max.
    If no single bar satisfies, use the largest available bar at s_min.

    Returns
    -------
    (bar_name, spacing [mm], As_provided [mm²/m])
    """
    bars = available_bars or list(REBAR_DATABASE.keys())
    # Sort by diameter ascending
    bars_sorted = sorted(bars, key=lambda b: REBAR_DATABASE[b].diameter)

    best_bar = bars_sorted[-1]
    best_s   = s_min
    for bar_name in bars_sorted:
        rebar = REBAR_DATABASE[bar_name]
        s = 1000.0 * rebar.area / As_req
        if s_min <= s <= s_max:
            best_bar = bar_name
            best_s   = s
            break
        if s < s_min:
            # Spacing too tight — try larger bar
            continue

    rebar    = REBAR_DATABASE[best_bar]
    spacing  = min(max(1000.0 * rebar.area / As_req, s_min), s_max)
    As_prov  = 1000.0 * rebar.area / spacing

    return best_bar, spacing, As_prov


# ---------------------------------------------------------------------------
# Main design function
# ---------------------------------------------------------------------------

def design_footing(
    critical_combo: LoadCombination,
    geom: FootingGeometry,
    soil: SoilProperties,
    materials: MaterialProperties,
    pressure_result: PressureResult,
    allow_partial_contact: bool = True,
) -> DesignResult:
    """
    Full RC design of isolated footing.

    Procedure
    ---------
    1. Net upward design pressure = q_u (from pressure_result.q_max).
       For conservative design we use uniform q_u = q_max over the whole area.
    2. Design flexure at column faces.
    3. Check one-way shear at d from column face.
    4. Check two-way (punching) shear at d/2 from column face.
    """
    fc  = materials.fc
    fy  = materials.fy
    phi_f = materials.phi_flexure
    phi_v = materials.phi_shear

    # Geometry in mm
    B_mm  = geom.B * 1000.0
    L_mm  = geom.L * 1000.0
    bx_mm = geom.bx * 1000.0
    by_mm = geom.by * 1000.0

    # Effective depths (two layers of steel, X steel on outside)
    bar_d_est = REBAR_DATABASE["#6"].diameter  # 19 mm estimate for initial depth
    dx = effective_depth(geom.h, geom.cover, bar_d_est, layer=1)
    dy = effective_depth(geom.h, geom.cover, bar_d_est, layer=2)
    d_avg = (dx + dy) / 2.0

    # ------------------------------------------------------------------
    # Net upward design pressure [kN/m²]
    # ------------------------------------------------------------------
    # Use q_max as uniform design pressure (conservative per ACI 15.5.2)
    qu = pressure_result.q_max  # [kPa]

    # Subtract weight of footing and soil above (already in the combination),
    # but for the structural design we use only the soil reaction (net upward).
    # ACI 318-19 §13.3.1.1: use factored net upward pressure (qu_net).
    # Self-weight of footing itself creates no net moment/shear at critical sections.
    # Therefore: qu_net = qu (the full factored bearing pressure, since self-weight
    # downward and reaction upward cancel in structural design).
    qu_net = qu  # [kPa = kN/m²]

    # ------------------------------------------------------------------
    # Flexure – X direction
    # Cantilever arm from face of column to edge of footing
    # ------------------------------------------------------------------
    cx_x = (geom.B - geom.bx) / 2.0  # cantilever arm in X [m]
    Mu_x_per_m = qu_net * cx_x ** 2 / 2.0  # [kN·m/m]

    As_req_x, _ = design_flexure_ACI(Mu_x_per_m, 1000.0, dx, fc, fy, phi_f)
    bar_x, spacing_x, As_prov_x = select_rebar(As_req_x)

    # Flexural capacity check
    a_x = As_prov_x * fy / (0.85 * fc * 1000.0)  # [mm]
    phi_Mn_x = phi_f * As_prov_x * fy * (dx - a_x / 2.0) / 1.0e6  # [kN·m/m]

    # ------------------------------------------------------------------
    # Flexure – Y direction
    # ------------------------------------------------------------------
    cx_y = (geom.L - geom.by) / 2.0  # cantilever arm in Y [m]
    Mu_y_per_m = qu_net * cx_y ** 2 / 2.0  # [kN·m/m]

    As_req_y, _ = design_flexure_ACI(Mu_y_per_m, 1000.0, dy, fc, fy, phi_f)
    bar_y, spacing_y, As_prov_y = select_rebar(As_req_y)

    a_y = As_prov_y * fy / (0.85 * fc * 1000.0)
    phi_Mn_y = phi_f * As_prov_y * fy * (dy - a_y / 2.0) / 1.0e6

    # ------------------------------------------------------------------
    # One-way shear – X (critical section at dx from column face)
    # ------------------------------------------------------------------
    cv_x = cx_x - dx / 1000.0  # shear arm [m]  (dx in m)
    Vu_x = qu_net * max(cv_x, 0.0)  # [kN/m]
    phi_Vc_x, passes_sx = check_one_way_shear_ACI(
        Vu_x, 1000.0, dx, fc, phi_v, As_prov_x
    )

    # One-way shear – Y
    cv_y = cx_y - dy / 1000.0
    Vu_y = qu_net * max(cv_y, 0.0)
    phi_Vc_y, passes_sy = check_one_way_shear_ACI(
        Vu_y, 1000.0, dy, fc, phi_v, As_prov_y
    )

    # ------------------------------------------------------------------
    # Punching shear
    # Critical perimeter at d_avg/2 from column face
    # ------------------------------------------------------------------
    # Loaded area inside critical perimeter
    c1_p = bx_mm + d_avg  # critical perimeter column dim in X [mm]
    c2_p = by_mm + d_avg  # critical perimeter column dim in Y [mm]

    # Net punching force = total reaction minus pressure inside critical perimeter
    A_crit = (c1_p / 1000.0) * (c2_p / 1000.0)  # [m²]
    Vu2way = critical_combo.N - qu_net * A_crit  # [kN] (net upward load)
    Vu2way = max(Vu2way, 0.0)

    phi_Vc2way, passes_punch = check_punching_shear_ACI(
        Vu2way, bx_mm, by_mm, d_avg, fc, phi_v
    )

    passes_all = (
        phi_Mn_x >= Mu_x_per_m
        and phi_Mn_y >= Mu_y_per_m
        and passes_sx
        and passes_sy
        and passes_punch
    )

    return DesignResult(
        Mu_x=Mu_x_per_m,
        As_req_x=As_req_x,
        As_prov_x=As_prov_x,
        bar_x=bar_x,
        spacing_x=spacing_x,
        phi_Mn_x=phi_Mn_x,
        passes_flexure_x=(phi_Mn_x >= Mu_x_per_m),
        Mu_y=Mu_y_per_m,
        As_req_y=As_req_y,
        As_prov_y=As_prov_y,
        bar_y=bar_y,
        spacing_y=spacing_y,
        phi_Mn_y=phi_Mn_y,
        passes_flexure_y=(phi_Mn_y >= Mu_y_per_m),
        Vu_x=Vu_x,
        phi_Vc_x=phi_Vc_x,
        passes_shear_x=passes_sx,
        Vu_y=Vu_y,
        phi_Vc_y=phi_Vc_y,
        passes_shear_y=passes_sy,
        Vu2way=Vu2way,
        phi_Vc2way=phi_Vc2way,
        passes_punching=passes_punch,
        dx=dx,
        dy=dy,
        passes_all=passes_all,
    )
