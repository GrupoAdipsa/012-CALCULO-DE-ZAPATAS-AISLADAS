"""
core/optimizer.py
Grid-search optimization of isolated footing dimensions (B, L, h).

Objective options:
  "min_area"          – minimise plan area B×L
  "min_volume"        – minimise concrete volume B×L×h
  "min_cost"          – minimise simplified concrete + steel cost
  "min_depth"         – minimise total thickness h
  "best_geotechnical" – maximise contact ratio (minimise eccentricity)
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from core.combinations import CombinationFactors, generate_combinations
from core.loads import LoadSet
from core.rc_design import MaterialProperties, design_footing
from core.soil_pressure import (
    FootingGeometry,
    PressureResult,
    SoilProperties,
    analyze_pressure,
    find_critical_pressures,
)
from core.stability import StabilityParams, StabilityResult, check_stability


# ---------------------------------------------------------------------------
# Constraints and objective
# ---------------------------------------------------------------------------

@dataclass
class OptimizationConstraints:
    B_min: float = 0.60
    B_max: float = 5.00
    L_min: float = 0.60
    L_max: float = 5.00
    h_min: float = 0.30
    h_max: float = 1.50
    Df_max: float = 3.00

    lock_B: bool = False
    lock_L: bool = False
    lock_h: bool = False

    max_L_to_B: Optional[float] = None

    allow_partial_contact: bool = True
    force_square: bool = False

    step_B: float = 0.05
    step_L: float = 0.05
    step_h: float = 0.05


@dataclass
class OptimizationObjective:
    objective: str = "min_area"     # see module docstring
    cost_concrete: float = 250.0    # $/m³
    cost_steel: float = 1500.0      # $/tonne


@dataclass
class OptimizationResult:
    best_geometry: Optional[FootingGeometry]
    objective_value: float
    n_iterations: int
    n_feasible: int
    all_results: List[Dict]
    feasible_results: List[Dict]
    converged: bool
    reason: str


# ---------------------------------------------------------------------------
# Single-design evaluator
# ---------------------------------------------------------------------------

def evaluate_design(
    B: float,
    L: float,
    h: float,
    load_set: LoadSet,
    soil: SoilProperties,
    materials: MaterialProperties,
    stability_params: StabilityParams,
    constraints: OptimizationConstraints,
    column_bx: float,
    column_by: float,
    cover: float = 0.075,
    gamma_concrete: float = 24.0,
) -> Tuple[bool, float, Dict]:
    """
    Check whether (B, L, h) satisfies all engineering constraints.

    Returns
    -------
    (is_feasible, objective_value, results_dict)

    Feasibility checks (in order):
    1. h >= max(B/5, L/5, 0.30)  – punching geometry rule of thumb
    2. Pressure check on ALL combinations (service and ultimate)
    3. Stability check on ALL service combinations
    4. RC design on critical ultimate combination
    5. Design passes_all
    """
    geom = FootingGeometry(B=B, L=L, h=h, bx=column_bx, by=column_by, cover=cover)
    results_dict: Dict[str, Any] = {"B": B, "L": L, "h": h}
    fail_reasons: List[str] = []

    # ---- Geometric pre-check ----------------------------------------
    h_min_geom = max(B / 5.0, L / 5.0, constraints.h_min)
    if h < h_min_geom * 0.95:
        results_dict["fail_reason"] = f"h too small (h_min_geom={h_min_geom:.2f})"
        return False, 1e12, results_dict

    # ---- Pressure analysis ------------------------------------------
    all_combos = load_set.combinations
    if not all_combos:
        results_dict["fail_reason"] = "No combinations available"
        return False, 1e12, results_dict

    press_results: List[PressureResult] = []
    for combo in all_combos:
        pr = analyze_pressure(
            combo, geom, soil, gamma_concrete,
            allow_partial_contact=constraints.allow_partial_contact,
            include_soil_weight=True,
        )
        press_results.append(pr)

    # Service pressure check (only service combos)
    service_prs = [
        pr for pr, c in zip(press_results, all_combos) if c.combo_type == "service"
    ]
    if service_prs and any(not pr.passes_qa for pr in service_prs):
        fail_reasons.append("qa exceeded")

    # Partial-contact check (if not allowed)
    if not constraints.allow_partial_contact:
        if any(not pr.full_contact for pr in service_prs):
            fail_reasons.append("partial contact")

    # ---- Stability check (service combos) ---------------------------
    service_combos = load_set.get_service_combos()
    stab_results: List[StabilityResult] = []
    for combo in service_combos:
        sr = check_stability(combo, geom, soil, stability_params, gamma_concrete)
        stab_results.append(sr)

    if stab_results and any(not sr.passes_all for sr in stab_results):
        fail_reasons.append("stability")

    # ---- RC design (critical ultimate combo) -------------------------
    ultimate_combos = load_set.get_ultimate_combos()
    ultimate_prs = [
        pr for pr, c in zip(press_results, all_combos) if c.combo_type == "ultimate"
    ]

    design_res = None
    if ultimate_combos and ultimate_prs:
        # Critical = maximum q_max among ultimate combos
        crit_idx = int(np.argmax([pr.q_max for pr in ultimate_prs]))
        crit_combo = ultimate_combos[crit_idx]
        crit_pr    = ultimate_prs[crit_idx]

        design_res = design_footing(
            crit_combo, geom, soil, materials, crit_pr,
            allow_partial_contact=constraints.allow_partial_contact,
        )
        if not design_res.passes_all:
            fail_reasons.append("rc_design")

    is_feasible = len(fail_reasons) == 0
    results_dict["fail_reasons"]  = fail_reasons
    results_dict["is_feasible"]   = is_feasible
    results_dict["press_results"] = press_results
    results_dict["stab_results"]  = stab_results
    results_dict["design_res"]    = design_res

    # ---- Objective --------------------------------------------------
    # Note: evaluate_design always uses OptimizationObjective() defaults here.
    # The actual objective is computed again in optimize_footing using the user's config.
    obj = _compute_objective(B, L, h, design_res, OptimizationObjective())
    results_dict["objective"] = obj

    return is_feasible, obj, results_dict


def _compute_objective(
    B: float,
    L: float,
    h: float,
    design_res,
    obj_config: OptimizationObjective,
) -> float:
    if obj_config.objective == "min_area":
        return B * L
    if obj_config.objective == "min_volume":
        return B * L * h
    if obj_config.objective == "min_cost":
        vol = B * L * h
        steel_kg = 0.0
        if design_res is not None:
            # Rough steel weight: As_x × L strips + As_y × B strips [mm²/m × m → mm²]
            rho_steel = 7850.0  # kg/m³
            As_x_total = design_res.As_prov_x * B  # mm²
            As_y_total = design_res.As_prov_y * L
            vol_steel = (As_x_total + As_y_total) * (B * 1000.0) / 1e9  # rough m³
            steel_kg = vol_steel * rho_steel
        return (
            vol * obj_config.cost_concrete
            + steel_kg / 1000.0 * obj_config.cost_steel
        )
    if obj_config.objective == "min_depth":
        return h
    if obj_config.objective == "best_geotechnical":
        return B * L  # proxy: larger footprint → lower pressure
    return B * L  # default


# ---------------------------------------------------------------------------
# Grid-search optimizer
# ---------------------------------------------------------------------------

def optimize_footing(
    initial_geom: FootingGeometry,
    load_set: LoadSet,
    soil: SoilProperties,
    materials: MaterialProperties,
    stability_params: StabilityParams,
    constraints: OptimizationConstraints,
    objective: OptimizationObjective,
    gamma_concrete: float = 24.0,
) -> OptimizationResult:
    """
    Grid-search over (B, L, h) space within *constraints*.

    If lock_B, lock_L, or lock_h flags are set the corresponding variable
    is fixed at the initial_geom value.

    Algorithm
    ---------
    1. Build grids.
    2. Iterate; skip if geometric pre-conditions not met.
    3. Evaluate engineering feasibility.
    4. Track best feasible solution.
    5. Return OptimizationResult.
    """
    # Build grids
    if constraints.lock_B:
        B_vals = [initial_geom.B]
    else:
        B_vals = list(np.arange(
            constraints.B_min, constraints.B_max + 1e-9, constraints.step_B
        ))

    if constraints.lock_L:
        L_vals = [initial_geom.L]
    else:
        L_vals = list(np.arange(
            constraints.L_min, constraints.L_max + 1e-9, constraints.step_L
        ))

    if constraints.lock_h:
        h_vals = [initial_geom.h]
    else:
        h_vals = list(np.arange(
            constraints.h_min, constraints.h_max + 1e-9, constraints.step_h
        ))

    all_results: List[Dict] = []
    feasible_results: List[Dict] = []
    n_iter = 0
    best_obj = 1e18
    best_geom: Optional[FootingGeometry] = None

    for B, L, h in itertools.product(B_vals, L_vals, h_vals):
        # Geometric filter
        if constraints.force_square and abs(B - L) > 1e-6:
            continue
        if constraints.max_L_to_B is not None and L > constraints.max_L_to_B * B:
            continue

        n_iter += 1
        feasible, obj, res = evaluate_design(
            B, L, h,
            load_set, soil, materials, stability_params,
            constraints,
            column_bx=initial_geom.bx,
            column_by=initial_geom.by,
            cover=initial_geom.cover,
            gamma_concrete=gamma_concrete,
        )

        all_results.append(res)

        if feasible:
            feasible_results.append(res)
            # Use the already-computed objective from evaluate_design to avoid
            # double-computation with a potentially different objective config
            obj_val = _compute_objective(B, L, h, res.get("design_res"), objective)
            if obj_val < best_obj:
                best_obj = obj_val
                best_geom = FootingGeometry(
                    B=B, L=L, h=h,
                    bx=initial_geom.bx,
                    by=initial_geom.by,
                    cover=initial_geom.cover,
                    pedestal_height=initial_geom.pedestal_height,
                    ex=initial_geom.ex,
                    ey=initial_geom.ey,
                )

    if best_geom is not None:
        reason = f"Optimal solution found after {n_iter} iterations."
        converged = True
    else:
        converged = False
        # Summarise why no solution was found
        reasons = {}
        for r in all_results:
            for fr in r.get("fail_reasons", []):
                reasons[fr] = reasons.get(fr, 0) + 1
        reason = (
            f"No feasible solution found in {n_iter} iterations. "
            f"Failure summary: {reasons}. "
            "Try relaxing constraints or increasing soil qa / footing limits."
        )

    return OptimizationResult(
        best_geometry=best_geom,
        objective_value=best_obj if best_geom else 1e18,
        n_iterations=n_iter,
        n_feasible=len(feasible_results),
        all_results=all_results,
        feasible_results=feasible_results,
        converged=converged,
        reason=reason,
    )
