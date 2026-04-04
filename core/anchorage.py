"""
core/anchorage.py
Moment transfer and anchorage checks at the column-footing interface.

All calculations per ACI 318-19.
Units: mm, MPa, kN, kN·m.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional

from core.loads import LoadCombination
from core.rc_design import REBAR_DATABASE, MaterialProperties, RebarData
from core.soil_pressure import FootingGeometry, PressureResult


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------

@dataclass
class AnchorageResult:
    Mu_transfer: float          # moment to transfer at interface [kN·m]
    Vn_transfer: float          # nominal shear-friction capacity [kN]
    phi_Vn_transfer: float      # design shear-friction capacity [kN]
    passes_shear_friction: bool

    ld_required: float          # required development length [mm]
    ld_available: float         # available embedment depth [mm]
    passes_development: bool

    can_be_fixed: bool          # True if conditions allow fixed-base assumption
    warnings: List[str]

    theta_estimated: float      # simplified rotation estimate [rad]
    notes: str


# ---------------------------------------------------------------------------
# Development length
# ---------------------------------------------------------------------------

def compute_development_length_ACI(
    bar: RebarData,
    fc: float,
    fy: float,
    cover: float,           # clear cover [mm]
    lambda_factor: float = 1.0,
) -> float:
    """
    Tension development length per ACI 318-19 §25.5.2 (simplified formula).

    ld = (fy · ψ_t · ψ_e · ψ_s) / (1.1 · λ · √f'c · (cb + Ktr)/db) · db

    Simplified (uncoated, bottom, normal-weight, no transverse steel):
      ψ_t = 1.0 (bottom bar)
      ψ_e = 1.0 (uncoated)
      ψ_s = 0.8 for #6 and smaller, 1.0 for #7 and larger (diameter-based)
      (cb + Ktr)/db capped at 2.5
      cb = cover + db/2

    Returns ld [mm], minimum 300 mm.
    """
    db = bar.diameter  # [mm]

    psi_t = 1.0
    psi_e = 1.0
    psi_s = 0.8 if db <= 19.05 else 1.0  # #6 = 19.05 mm

    cb = cover + db / 2.0  # [mm]
    Ktr = 0.0              # conservative, no transverse confinement

    confinement = min((cb + Ktr) / db, 2.5)
    if confinement < 1e-6:
        confinement = 1.0

    ld = (fy * psi_t * psi_e * psi_s) / (1.1 * lambda_factor * math.sqrt(fc) * confinement) * db
    return max(ld, 300.0)


# ---------------------------------------------------------------------------
# Shear friction
# ---------------------------------------------------------------------------

def _shear_friction_capacity(
    Avf: float,     # area of interface reinforcement [mm²]
    fy: float,      # [MPa]
    fc: float,      # [MPa]
    mu_sf: float,   # shear-friction coefficient (1.4 for normal concrete-to-concrete)
    phi: float,     # 0.75
    Ac: float,      # contact area [mm²]
) -> float:
    """
    ACI 318-19 §22.9.4 shear-friction:
      Vn = min(Avf · fy · μ, 0.2·f'c·Ac, (3.3 + 0.08·f'c)·Ac, 11·Ac) [N]
    Returns phi_Vn [kN].
    """
    Vn1 = Avf * fy * mu_sf
    Vn2 = 0.2 * fc * Ac
    Vn3 = (3.3 + 0.08 * fc) * Ac
    Vn4 = 11.0 * Ac  # MPa × mm² = N (≈ 11 MPa limit)
    Vn = min(Vn1, Vn2, Vn3, Vn4)
    return phi * Vn / 1000.0  # → kN


# ---------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------

def check_moment_transfer(
    combo: LoadCombination,
    geom: FootingGeometry,
    materials: MaterialProperties,
    pressure_result: PressureResult,
    bar_size: str = "#6",
    n_bars: int = 4,
) -> AnchorageResult:
    """
    Check moment transfer between column/pedestal and footing per ACI 318-19.

    Steps
    -----
    1. Shear friction at construction joint (base of column).
    2. Development length of dowel bars.
    3. Evaluate feasibility of fixed-base assumption.
    4. Estimate simplified column base rotation.
    5. Issue warnings as appropriate.

    Parameters
    ----------
    combo          : governing (usually maximum moment) load combination
    geom           : footing geometry
    materials      : material properties
    pressure_result: pressure analysis result for the same combo
    bar_size       : size of dowel bars (default "#6")
    n_bars         : number of dowel bars
    """
    warnings: List[str] = []

    fc  = materials.fc
    fy  = materials.fy
    phi_v = materials.phi_shear

    bar = REBAR_DATABASE.get(bar_size, REBAR_DATABASE["#6"])
    cover_mm = geom.cover * 1000.0

    # ------------------------------------------------------------------
    # Interface geometry
    # ------------------------------------------------------------------
    bx_mm = geom.bx * 1000.0
    by_mm = geom.by * 1000.0
    Ac_interface = bx_mm * by_mm  # [mm²]

    # ------------------------------------------------------------------
    # 1. Shear friction
    # ------------------------------------------------------------------
    Avf = n_bars * bar.area  # [mm²]
    mu_sf = 1.4              # ACI Table 22.9.4.2 – concrete cast against hardened concrete (roughened)

    # Total shear at base
    V_total = math.hypot(combo.Vx, combo.Vy)  # [kN]

    phi_Vn_sf = _shear_friction_capacity(Avf, fy, fc, mu_sf, phi_v, Ac_interface)
    passes_sf = V_total <= phi_Vn_sf

    if not passes_sf:
        warnings.append(
            f"Shear friction FAILS: Vu={V_total:.1f} kN > φVn={phi_Vn_sf:.1f} kN. "
            "Increase number/size of dowels or roughen interface."
        )

    # ------------------------------------------------------------------
    # 2. Development length
    # ------------------------------------------------------------------
    ld_req = compute_development_length_ACI(bar, fc, fy, cover_mm)

    # Available embedment = footing thickness - top cover - pedestal height (if any)
    ped_h_mm = (geom.pedestal_height or 0.0) * 1000.0
    h_mm     = geom.h * 1000.0
    ld_avail = h_mm - cover_mm - ped_h_mm

    passes_dev = ld_avail >= ld_req
    if not passes_dev:
        warnings.append(
            f"Development length FAILS: ld_req={ld_req:.0f} mm > available={ld_avail:.0f} mm. "
            "Increase footing depth or use hooks."
        )

    # ------------------------------------------------------------------
    # 3. Fixed-base feasibility
    # ------------------------------------------------------------------
    # Moment transferred at interface
    Mu_transfer = math.hypot(combo.Mx, combo.My)  # [kN·m]

    # Approximate moment capacity via couple of tension/compression bars
    d_couple = 0.8 * max(bx_mm, by_mm)  # approximate lever arm [mm]
    Mn_bars  = n_bars / 2.0 * bar.area * fy * d_couple / 1.0e6  # [kN·m]
    phi_Mn_bars = phi_v * Mn_bars

    can_be_fixed = (
        passes_dev
        and passes_sf
        and Mu_transfer <= phi_Mn_bars
        and pressure_result.contact_ratio >= 0.8
    )

    if not can_be_fixed:
        if Mu_transfer > phi_Mn_bars:
            warnings.append(
                f"Moment transfer capacity φMn={phi_Mn_bars:.1f} kN·m < Mu={Mu_transfer:.1f} kN·m. "
                "Fixed-base assumption is NOT justified."
            )
        if pressure_result.contact_ratio < 0.8:
            warnings.append(
                f"Contact ratio={pressure_result.contact_ratio:.2f} < 0.80. "
                "Significant tensile zone — fixed base assumption is questionable."
            )

    # ------------------------------------------------------------------
    # 4. Rotation estimate (simplified elastic)
    # ------------------------------------------------------------------
    # θ = M · h_footing / (E_c · I_effective)
    # I_effective = 0.35 · I_gross for cracked section estimate
    # E_c = 4700 · √f'c  [MPa]  (ACI 318-19 §19.2.2.1)
    Ec     = 4700.0 * math.sqrt(fc)  # [MPa]
    I_gross = bx_mm * (by_mm ** 3) / 12.0  # [mm⁴] about bending axis
    I_eff   = 0.35 * I_gross
    M_Nmm   = Mu_transfer * 1.0e6  # [N·mm]
    h_mm_c  = geom.h * 1000.0      # [mm]

    if Ec * I_eff > 0:
        theta = M_Nmm * h_mm_c / (Ec * I_eff)
    else:
        theta = 0.0

    # ------------------------------------------------------------------
    # Notes
    # ------------------------------------------------------------------
    notes = (
        f"Combo: {combo.name}. "
        f"Dowels: {n_bars}×{bar_size} (Avf={Avf:.0f} mm²). "
        f"ld_req={ld_req:.0f} mm, ld_avail={ld_avail:.0f} mm. "
        f"Fixed base: {'YES' if can_be_fixed else 'NO'}. "
        f"Rotation estimate: {theta*1000:.3f} mrad."
    )

    return AnchorageResult(
        Mu_transfer=Mu_transfer,
        Vn_transfer=phi_Vn_sf / phi_v,
        phi_Vn_transfer=phi_Vn_sf,
        passes_shear_friction=passes_sf,
        ld_required=ld_req,
        ld_available=ld_avail,
        passes_development=passes_dev,
        can_be_fixed=can_be_fixed,
        warnings=warnings,
        theta_estimated=theta,
        notes=notes,
    )
