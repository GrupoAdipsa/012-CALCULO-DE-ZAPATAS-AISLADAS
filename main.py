"""
main.py
Zapata Aislada – Isolated Footing Design Tool
Main entry point for console / script usage.

Example run:
    python main.py
"""

from __future__ import annotations

from core.anchorage import check_moment_transfer
from core.combinations import CombinationFactors, generate_combinations
from core.loads import LoadCase, LoadSet
from core.optimizer import (
    OptimizationConstraints,
    OptimizationObjective,
    optimize_footing,
)
from core.rc_design import MaterialProperties, design_footing
from core.report import generate_summary_dict, print_summary
from core.soil_pressure import (
    FootingGeometry,
    SoilProperties,
    analyze_pressure,
    find_critical_pressures,
)
from core.stability import StabilityParams, check_stability, find_critical_stability


def run_example() -> None:
    """
    Example: Design a footing for a 40×40 cm column.

    Applied loads at column base (service level):
      Dead  : N=800 kN,  Mx=50 kN·m, My=30 kN·m, Vx=20 kN, Vy=15 kN
      Live  : N=400 kN,  Mx=20 kN·m, My=15 kN·m, Vx=10 kN, Vy=8 kN
      Wind X: N=0 kN,    Vx=60 kN,   Mx=90 kN·m  (others zero)

    Soil  : qa=200 kPa, γ=18 kN/m³, Df=1.5 m
    Conc  : f'c=21 MPa, fy=420 MPa
    """

    # ------------------------------------------------------------------
    # 1. Define load cases
    # ------------------------------------------------------------------
    ls = LoadSet()
    ls.add_case(LoadCase("Dead",   N=800.0, Vx=20.0, Vy=15.0, Mx=50.0, My=30.0,  load_type="dead"))
    ls.add_case(LoadCase("Live",   N=400.0, Vx=10.0, Vy=8.0,  Mx=20.0, My=15.0,  load_type="live"))
    ls.add_case(LoadCase("Wind_X", N=0.0,   Vx=60.0, Vy=0.0,  Mx=90.0, My=0.0,   load_type="wind_x"))

    # ------------------------------------------------------------------
    # 2. Generate ACI / ASCE-7 combinations
    # ------------------------------------------------------------------
    factors = CombinationFactors.aci_asce7()
    ls = generate_combinations(ls, factors)
    print(f"\n{'='*60}")
    print(f"  Load combinations generated: {len(ls.combinations)}")
    print(f"    Service : {len(ls.get_service_combos())}")
    print(f"    Ultimate: {len(ls.get_ultimate_combos())}")

    # ------------------------------------------------------------------
    # 3. Define geometry, soil, materials
    # ------------------------------------------------------------------
    geom  = FootingGeometry(B=2.20, L=2.20, h=0.55, bx=0.40, by=0.40, cover=0.075)
    soil  = SoilProperties(qa=200.0, gamma_soil=18.0, Df=1.5)
    mats  = MaterialProperties(fc=21.0, fy=420.0)
    stab  = StabilityParams(mu_friction=0.45, FS_sliding_min=1.5, FS_overturning_min=1.5)

    # ------------------------------------------------------------------
    # 4. Pressure analysis (service combos for qa check)
    # ------------------------------------------------------------------
    service_combos  = ls.get_service_combos()
    ultimate_combos = ls.get_ultimate_combos()
    all_combos      = ls.combinations

    press_results = [
        analyze_pressure(c, geom, soil, allow_partial_contact=True)
        for c in all_combos
    ]

    critical_p = find_critical_pressures(press_results)
    max_pr     = critical_p["max_qmax"]

    print(f"\n  Critical pressure: {max_pr.combo_name}")
    print(f"    q_max = {max_pr.q_max:.1f} kPa  (qa = {soil.qa:.0f} kPa  "
          f"{'✓' if max_pr.passes_qa else '✗'})")
    print(f"    Full contact: {max_pr.full_contact}")

    # ------------------------------------------------------------------
    # 5. Stability (service combos)
    # ------------------------------------------------------------------
    stab_results = [
        check_stability(c, geom, soil, stab)
        for c in service_combos
    ]
    critical_s = find_critical_stability(stab_results)
    min_sl_x   = critical_s["min_FS_sliding_x"]
    min_ot_x   = critical_s["min_FS_overturning_x"]

    print(f"\n  Worst sliding X :  FS={min_sl_x.FS_sliding_x:.2f}  "
          f"({'✓' if min_sl_x.passes_sliding_x else '✗'})")
    print(f"  Worst OT X      :  FS={min_ot_x.FS_overturning_x:.2f}  "
          f"({'✓' if min_ot_x.passes_overturning_x else '✗'})")

    # ------------------------------------------------------------------
    # 6. RC design (critical ultimate combination)
    # ------------------------------------------------------------------
    import numpy as np
    ult_prs = [pr for pr, c in zip(press_results, all_combos)
               if c.combo_type == "ultimate"]
    crit_idx = int(np.argmax([pr.q_max for pr in ult_prs]))
    crit_combo = ultimate_combos[crit_idx]
    crit_pr    = ult_prs[crit_idx]

    design = design_footing(crit_combo, geom, soil, mats, crit_pr)

    print(f"\n  Design (combo: {crit_combo.name})")
    print(f"    dx={design.dx:.0f} mm, dy={design.dy:.0f} mm")
    print(f"    X: {design.bar_x} @ {design.spacing_x:.0f} mm  "
          f"(φMn={design.phi_Mn_x:.1f} kN·m/m >= Mu={design.Mu_x:.1f}  "
          f"{'✓' if design.passes_flexure_x else '✗'})")
    print(f"    Y: {design.bar_y} @ {design.spacing_y:.0f} mm  "
          f"(φMn={design.phi_Mn_y:.1f} kN·m/m >= Mu={design.Mu_y:.1f}  "
          f"{'✓' if design.passes_flexure_y else '✗'})")
    print(f"    1-way shear X: φVc={design.phi_Vc_x:.1f} >= Vu={design.Vu_x:.1f} kN/m  "
          f"{'✓' if design.passes_shear_x else '✗'}")
    print(f"    1-way shear Y: φVc={design.phi_Vc_y:.1f} >= Vu={design.Vu_y:.1f} kN/m  "
          f"{'✓' if design.passes_shear_y else '✗'}")
    print(f"    Punching:      φVc={design.phi_Vc2way:.1f} >= Vu={design.Vu2way:.1f} kN  "
          f"{'✓' if design.passes_punching else '✗'}")
    print(f"    OVERALL: {'PASS ✓' if design.passes_all else 'FAIL ✗'}")

    # ------------------------------------------------------------------
    # 7. Anchorage
    # ------------------------------------------------------------------
    max_m_combo = max(all_combos, key=lambda c: abs(c.Mx) + abs(c.My))
    pr_max_m    = press_results[all_combos.index(max_m_combo)]
    anch        = check_moment_transfer(max_m_combo, geom, mats, pr_max_m)

    print(f"\n  Anchorage ({max_m_combo.name})")
    print(f"    Development: ld_req={anch.ld_required:.0f} mm  "
          f"ld_avail={anch.ld_available:.0f} mm  "
          f"{'✓' if anch.passes_development else '✗'}")
    print(f"    Fixed base: {anch.can_be_fixed}")
    if anch.warnings:
        for w in anch.warnings:
            print(f"    ⚠ {w}")

    # ------------------------------------------------------------------
    # 8. Optional: quick optimization
    # ------------------------------------------------------------------
    print(f"\n{'='*60}")
    print("  Running optimization (B, L in [0.8, 3.5] m, h in [0.35, 0.90] m)…")

    constraints = OptimizationConstraints(
        B_min=0.80, B_max=3.50,
        L_min=0.80, L_max=3.50,
        h_min=0.35, h_max=0.90,
        step_B=0.15, step_L=0.15, step_h=0.10,
        force_square=True,
        allow_partial_contact=True,
    )
    obj_cfg = OptimizationObjective(objective="min_area")
    opt_res = optimize_footing(geom, ls, soil, mats, stab, constraints, obj_cfg)

    if opt_res.converged and opt_res.best_geometry:
        bg = opt_res.best_geometry
        print(f"  Best: B={bg.B:.2f} m, L={bg.L:.2f} m, h={bg.h:.2f} m  "
              f"(area={opt_res.objective_value:.2f} m²)")
        print(f"  Evaluated {opt_res.n_iterations}, feasible {opt_res.n_feasible}")
    else:
        print(f"  {opt_res.reason}")

    # ------------------------------------------------------------------
    # 9. Full report
    # ------------------------------------------------------------------
    summary = generate_summary_dict(
        geom, soil, mats, press_results, stab_results, design, anch, opt_res
    )
    print_summary(summary)


if __name__ == "__main__":
    run_example()
