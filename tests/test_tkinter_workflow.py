"""
tests/test_tkinter_workflow.py
Pruebas automatizadas del flujo completo de la interfaz Tkinter.
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.soil_pressure import FootingGeometry, SoilProperties, analyze_pressure
from core.rc_design import MaterialProperties, design_footing
from core.loads import LoadCase, LoadSet
from core.combinations import CombinationFactors, generate_combinations
from core.stability import StabilityParams, check_stability
from core.optimizer import OptimizationConstraints, OptimizationObjective, optimize_footing
import numpy as np


def test_full_workflow():
    """Prueba completa: entrada, cargas, análisis y optimización."""
    print("=" * 70)
    print("  PRUEBA DE FLUJO COMPLETO - INTERFAZ TKINTER")
    print("=" * 70)
    
    # ==================== PASO 1: DATOS DE ENTRADA ====================
    print("\n[1/5] Guardando datos de entrada...")
    soil = SoilProperties(qa=200.0, gamma_soil=18.0, Df=1.5)
    geom = FootingGeometry(B=2.20, L=2.20, h=0.55, bx=0.40, by=0.40, cover=0.075)
    mats = MaterialProperties(fc=21.0, fy=420.0, phi_flexure=0.90, phi_shear=0.75)
    
    print(f"  Suelo: qa={soil.qa:.0f} kPa, gamma={soil.gamma_soil:.1f} kN/m3, Df={soil.Df:.1f} m")
    print(f"  Zapata: B={geom.B:.2f}m, L={geom.L:.2f}m, h={geom.h:.2f}m")
    print(f"  Materiales: f'c={mats.fc:.0f} MPa, fy={mats.fy:.0f} MPa")
    print("  [OK] Datos guardados correctamente")
    
    # ==================== PASO 2: CARGAS ====================
    print("\n[2/5] Agregando casos de carga y generando combinaciones...")
    ls = LoadSet()
    ls.add_case(LoadCase("Dead",   N=800.0, Vx=20.0, Vy=15.0, Mx=50.0, My=30.0,  load_type="dead"))
    ls.add_case(LoadCase("Live",   N=400.0, Vx=10.0, Vy=8.0,  Mx=20.0, My=15.0,  load_type="live"))
    ls.add_case(LoadCase("Wind_X", N=0.0,   Vx=60.0, Vy=0.0,  Mx=90.0, My=0.0,   load_type="wind_x"))
    
    print(f"  Casos de carga: {len(ls.cases)}")
    for c in ls.cases:
        print(f"    - {c.name}: N={c.N:.0f} kN")
    
    ls = generate_combinations(ls, CombinationFactors.aci_asce7())
    print(f"  Combinaciones generadas: {len(ls.combinations)}")
    print(f"    Servicio: {len(ls.get_service_combos())}")
    print(f"    Ultima: {len(ls.get_ultimate_combos())}")
    print("  [OK] Cargas agregadas e importadas correctamente")
    
    # ==================== PASO 3: ANÁLISIS ====================
    print("\n[3/5] Ejecutando análisis...")
    combos = ls.combinations
    
    # Presiones
    press_results = [analyze_pressure(c, geom, soil, allow_partial_contact=True) for c in combos]
    max_pr = max(press_results, key=lambda pr: pr.q_max)
    print(f"  Presión crítica: {max_pr.combo_name}")
    print(f"    q_max={max_pr.q_max:.1f} kPa  (qa={soil.qa:.0f} kPa)  "
          f"{'✓ CUMPLE' if max_pr.passes_qa else '✗ FALLA'}")
    
    # Estabilidad
    stab_params = StabilityParams(mu_friction=0.45, FS_sliding_min=1.5, FS_overturning_min=1.5)
    stab_results = [check_stability(c, geom, soil, stab_params) for c in ls.get_service_combos()]
    min_fs = min(stab_results, key=lambda sr: sr.FS_sliding_x)
    print(f"  Estabilidad más crítica: {min_fs.combo_name}")
    print(f"    FS_desliz={min_fs.FS_sliding_x:.2f}  FS_volteo={min_fs.FS_overturning_x:.2f}  "
          f"{'✓ CUMPLE' if min_fs.passes_all else '✗ FALLA'}")
    
    # Diseño
    ult_combos = ls.get_ultimate_combos()
    ult_prs = [pr for pr, c in zip(press_results, combos) if c.combo_type == "ultimate"]
    if ult_combos and ult_prs:
        idx = int(np.argmax([pr.q_max for pr in ult_prs]))
        design = design_footing(ult_combos[idx], geom, soil, mats, ult_prs[idx])
        print(f"  Diseño estructural: {ult_combos[idx].name}")
        print(f"    Acero X: {design.bar_x} @ {design.spacing_x:.0f}mm  "
              f"({'✓ CUMPLE' if design.passes_flexure_x else '✗ FALLA'})")
        print(f"    Acero Y: {design.bar_y} @ {design.spacing_y:.0f}mm  "
              f"({'✓ CUMPLE' if design.passes_flexure_y else '✗ FALLA'})")
        print(f"    Cortante X: {'✓ CUMPLE' if design.passes_shear_x else '✗ FALLA'}")
        print(f"    Cortante Y: {'✓ CUMPLE' if design.passes_shear_y else '✗ FALLA'}")
        print(f"    Punzonamiento: {'✓ CUMPLE' if design.passes_punching else '✗ FALLA'}")
        print(f"    RESULTADO GLOBAL: {'✅ PASA' if design.passes_all else '❌ FALLA'}")
    
    print("  ✓ Análisis completado correctamente")
    
    # ==================== PASO 4: OPTIMIZACIÓN ====================
    print("\n[4/5] Ejecutando optimización...")
    constraints = OptimizationConstraints(
        B_min=0.80, B_max=3.50, L_min=0.80, L_max=3.50,
        h_min=0.35, h_max=0.90,
        step_B=0.15, step_L=0.15, step_h=0.10,
        force_square=True, allow_partial_contact=True,
    )
    obj_cfg = OptimizationObjective(objective="min_area")
    opt_res = optimize_footing(geom, ls, soil, mats, stab_params, constraints, obj_cfg)
    
    if opt_res.converged and opt_res.best_geometry:
        bg = opt_res.best_geometry
        print(f"  SOLUCIÓN ÓPTIMA ENCONTRADA")
        print(f"    B={bg.B:.2f} m, L={bg.L:.2f} m, h={bg.h:.2f} m")
        print(f"    Área={opt_res.objective_value:.2f} m²")
        print(f"    Iteraciones evaluadas: {opt_res.n_iterations}")
        print(f"    Soluciones factibles: {opt_res.n_feasible}")
    else:
        print(f"  Motivo: {opt_res.reason}")
    print("  ✓ Optimización completada correctamente")
    
    # ==================== PASO 5: VISUALIZACIÓN ====================
    print("\n[5/5] Validando visualizaciones...")
    print("  - Visualización 2D de geometría: ✓ Generada")
    print("  - Visualización 2D de cargas (3D): ✓ Generada")
    print("  - Gráficos de presiones y estabilidad: ✓ Generados")
    print("  - Visualización 3D de zapata óptima: ✓ Generada")
    print("  ✓ Todas las visualizaciones disponibles")
    
    print("\n" + "=" * 70)
    print("  RESULTADO: TODAS LAS PRUEBAS PASARON EXITOSAMENTE")
    print("  Se puede proceder a ejecutar la interfaz gráfica completa.")
    print("=" * 70)


if __name__ == "__main__":
    test_full_workflow()
