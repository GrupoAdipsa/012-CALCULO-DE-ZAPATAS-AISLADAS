"""
ui/streamlit_app.py
Streamlit web application for isolated footing design.

Run with:
    streamlit run ui/streamlit_app.py
"""

from __future__ import annotations

import io
import sys
import os

# Ensure project root is on path when running from ui/ directory
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pandas as pd
import streamlit as st

from core.anchorage import check_moment_transfer
from core.combinations import CombinationFactors, generate_combinations
from core.loads import LoadCase, LoadCombination, LoadSet
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

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Zapata Aislada – Footing Design",
    page_icon="🏗️",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Session state helpers
# ---------------------------------------------------------------------------

def _init_state() -> None:
    defaults: dict = {
        "page": "Inputs",
        "soil": None,
        "geom": None,
        "materials": None,
        "load_set": LoadSet(),
        "press_results": [],
        "stab_results": [],
        "design_result": None,
        "anch_result": None,
        "opt_result": None,
        "summary": None,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


_init_state()

# ---------------------------------------------------------------------------
# Sidebar navigation
# ---------------------------------------------------------------------------

st.sidebar.title("🏗️ Zapata Aislada")
st.sidebar.markdown("---")

pages = ["Inputs", "Loads", "Analysis", "Optimization", "Results"]
selected_page = st.sidebar.radio("Navigation", pages, key="page_radio")
st.session_state["page"] = selected_page

st.sidebar.markdown("---")
st.sidebar.caption("ACI 318-19 / ASCE-7 | SI units")

# ============================================================
# PAGE 1 – INPUTS
# ============================================================

if selected_page == "Inputs":
    st.title("1 · Project Inputs")

    col1, col2, col3 = st.columns(3)

    # ---- Soil properties -------------------------------------------
    with col1:
        st.subheader("Soil Properties")
        qa    = st.number_input("Allowable bearing capacity qa [kPa]", 50.0, 1000.0, 200.0, 10.0)
        gamma = st.number_input("Soil unit weight γ [kN/m³]", 14.0, 22.0, 18.0, 0.5)
        Df    = st.number_input("Embedment depth Df [m]", 0.3, 5.0, 1.5, 0.1)
        st.session_state["soil"] = SoilProperties(qa=qa, gamma_soil=gamma, Df=Df)

    # ---- Footing geometry ------------------------------------------
    with col2:
        st.subheader("Footing Geometry (initial)")
        B  = st.number_input("Width B [m]",  0.5, 8.0, 2.0, 0.05)
        L  = st.number_input("Length L [m]", 0.5, 8.0, 2.0, 0.05)
        h  = st.number_input("Thickness h [m]", 0.3, 2.0, 0.5, 0.05)
        bx = st.number_input("Column dimension bx [m]", 0.2, 1.5, 0.4, 0.05)
        by = st.number_input("Column dimension by [m]", 0.2, 1.5, 0.4, 0.05)
        cov = st.number_input("Clear cover [m]", 0.05, 0.15, 0.075, 0.005)
        st.session_state["geom"] = FootingGeometry(B=B, L=L, h=h, bx=bx, by=by, cover=cov)

    # ---- Materials -------------------------------------------------
    with col3:
        st.subheader("Material Properties")
        fc  = st.number_input("f'c [MPa]", 17.0, 70.0, 21.0, 1.0)
        fy  = st.number_input("fy [MPa]", 280.0, 600.0, 420.0, 10.0)
        phi_f = st.number_input("φ flexure", 0.80, 0.95, 0.90, 0.01)
        phi_v = st.number_input("φ shear",   0.60, 0.85, 0.75, 0.01)
        st.session_state["materials"] = MaterialProperties(
            fc=fc, fy=fy, phi_flexure=phi_f, phi_shear=phi_v
        )

    st.success("Inputs saved. Proceed to **Loads** →")


# ============================================================
# PAGE 2 – LOADS
# ============================================================

elif selected_page == "Loads":
    st.title("2 · Load Input")

    tab1, tab2, tab3 = st.tabs(["Manual load cases", "Manual combinations", "File upload"])

    with tab1:
        st.subheader("Add basic load case")
        c1, c2 = st.columns(2)
        with c1:
            lc_name  = st.text_input("Case name", "Dead")
            lc_type  = st.selectbox("Load type",
                ["dead","live","roof_live","wind_x","wind_y","seismic_x","seismic_y","other"])
            lc_N  = st.number_input("N [kN]",  value=800.0)
            lc_Vx = st.number_input("Vx [kN]", value=20.0)
        with c2:
            lc_Vy = st.number_input("Vy [kN]", value=15.0)
            lc_Mx = st.number_input("Mx [kN·m]", value=50.0)
            lc_My = st.number_input("My [kN·m]", value=30.0)

        if st.button("➕ Add load case"):
            case = LoadCase(lc_name, lc_N, lc_Vx, lc_Vy, lc_Mx, lc_My, lc_type)
            st.session_state["load_set"].add_case(case)
            st.success(f"Case '{lc_name}' added.")

        if st.button("⚡ Generate ACI/ASCE-7 combinations from cases"):
            if not st.session_state["load_set"].cases:
                st.error("Add at least one load case first.")
            else:
                factors = CombinationFactors.aci_asce7()
                st.session_state["load_set"] = generate_combinations(
                    st.session_state["load_set"], factors
                )
                st.success(
                    f"Generated {len(st.session_state['load_set'].combinations)} combinations."
                )

        # Show existing cases
        cases = st.session_state["load_set"].cases
        if cases:
            st.dataframe(
                pd.DataFrame([
                    {"name": c.name, "type": c.load_type,
                     "N": c.N, "Vx": c.Vx, "Vy": c.Vy, "Mx": c.Mx, "My": c.My}
                    for c in cases
                ])
            )

    with tab2:
        st.subheader("Add manual combination")
        c1, c2, c3 = st.columns(3)
        with c1:
            mc_name  = st.text_input("Combo name", "U-Manual")
            mc_type  = st.selectbox("Combo type", ["ultimate","service"])
            mc_N     = st.number_input("N [kN]",   value=1200.0, key="mc_N")
            mc_Vx    = st.number_input("Vx [kN]",  value=30.0,   key="mc_Vx")
        with c2:
            mc_Vy    = st.number_input("Vy [kN]",  value=22.0,   key="mc_Vy")
            mc_Mx    = st.number_input("Mx [kN·m]",value=75.0,   key="mc_Mx")
            mc_My    = st.number_input("My [kN·m]",value=45.0,   key="mc_My")

        if st.button("➕ Add combination"):
            combo = LoadCombination(mc_name, mc_N, mc_Vx, mc_Vy, mc_Mx, mc_My, mc_type)
            st.session_state["load_set"].add_combination(combo)
            st.success(f"Combination '{mc_name}' added.")

    with tab3:
        st.subheader("Import from file")
        uploaded = st.file_uploader("Upload .xlsx or .csv", type=["xlsx","csv"])
        if uploaded is not None:
            try:
                if uploaded.name.endswith(".xlsx"):
                    from io.excel_import import import_combinations_excel
                    import io as _io
                    tmp_ls = import_combinations_excel(_io.BytesIO(uploaded.read()))
                    for combo in tmp_ls.combinations:
                        st.session_state["load_set"].add_combination(combo)
                    st.success(f"Imported {len(tmp_ls.combinations)} combinations from file.")
                elif uploaded.name.endswith(".csv"):
                    from io.csv_import import import_combinations_csv
                    import io as _io
                    tmp_ls = import_combinations_csv(_io.StringIO(uploaded.read().decode()))
                    for combo in tmp_ls.combinations:
                        st.session_state["load_set"].add_combination(combo)
                    st.success(f"Imported {len(tmp_ls.combinations)} combinations from file.")
            except Exception as e:
                st.error(str(e))

    # Show combinations table
    combos = st.session_state["load_set"].combinations
    if combos:
        st.subheader(f"Current combinations ({len(combos)})")
        st.dataframe(st.session_state["load_set"].to_dataframe())


# ============================================================
# PAGE 3 – ANALYSIS
# ============================================================

elif selected_page == "Analysis":
    st.title("3 · Analysis")

    soil  = st.session_state.get("soil")
    geom  = st.session_state.get("geom")
    mats  = st.session_state.get("materials")
    ls    = st.session_state.get("load_set")

    if not (soil and geom and mats):
        st.warning("Complete Inputs first.")
        st.stop()

    if not ls or not ls.combinations:
        st.warning("Add load combinations in the Loads page.")
        st.stop()

    # Stability params
    with st.expander("Stability parameters"):
        mu_f  = st.number_input("Friction coefficient μ",  0.20, 0.80, 0.45, 0.05)
        fs_sl = st.number_input("Min FS sliding",   1.0, 3.0, 1.5, 0.1)
        fs_ot = st.number_input("Min FS overturning", 1.0, 3.0, 1.5, 0.1)
        allow_pc = st.checkbox("Allow partial contact", True)

    stab_params = StabilityParams(
        mu_friction=mu_f,
        FS_sliding_min=fs_sl,
        FS_overturning_min=fs_ot,
    )

    if st.button("▶ Run Analysis", type="primary"):
        combos = ls.combinations

        press_results = [
            analyze_pressure(c, geom, soil,
                             allow_partial_contact=allow_pc)
            for c in combos
        ]
        stab_results = [
            check_stability(c, geom, soil, stab_params)
            for c in ls.get_service_combos()
        ]

        # Design on critical ultimate combo
        ult_combos = ls.get_ultimate_combos()
        ult_prs    = [pr for pr, c in zip(press_results, combos)
                      if c.combo_type == "ultimate"]
        design_res = None
        if ult_combos and ult_prs:
            import numpy as np
            idx = int(np.argmax([pr.q_max for pr in ult_prs]))
            design_res = design_footing(ult_combos[idx], geom, soil, mats, ult_prs[idx])

        # Anchorage
        all_combos_max = max(combos, key=lambda c: abs(c.Mx) + abs(c.My))
        pr_max = press_results[combos.index(all_combos_max)]
        anch = check_moment_transfer(all_combos_max, geom, mats, pr_max)

        st.session_state["press_results"] = press_results
        st.session_state["stab_results"]  = stab_results
        st.session_state["design_result"] = design_res
        st.session_state["anch_result"]   = anch

        if design_res:
            summary = generate_summary_dict(
                geom, soil, mats, press_results, stab_results, design_res, anch
            )
            st.session_state["summary"] = summary

        st.success("Analysis complete.")

    # ---- Display results -------------------------------------------
    if st.session_state["press_results"]:
        st.subheader("Contact Pressure Results")
        pr_data = []
        for pr in st.session_state["press_results"]:
            pr_data.append({
                "Combo": pr.combo_name,
                "N_total [kN]": round(pr.N_total, 1),
                "q_max [kPa]": round(pr.q_max, 1),
                "q_min [kPa]": round(pr.q_min, 1),
                "ex [m]": round(pr.eccentricity_x, 3),
                "ey [m]": round(pr.eccentricity_y, 3),
                "Full contact": "✓" if pr.full_contact else "✗",
                "Contact ratio": round(pr.contact_ratio, 3),
                "Passes qa": "✓" if pr.passes_qa else "✗",
            })
        st.dataframe(pd.DataFrame(pr_data))

    if st.session_state["stab_results"]:
        st.subheader("Stability Results")
        sr_data = []
        for sr in st.session_state["stab_results"]:
            sr_data.append({
                "Combo": sr.combo_name,
                "FS_slid_x": round(sr.FS_sliding_x, 2),
                "FS_slid_y": round(sr.FS_sliding_y, 2),
                "FS_OT_x":   round(sr.FS_overturning_x, 2),
                "FS_OT_y":   round(sr.FS_overturning_y, 2),
                "FS_uplift": round(sr.FS_uplift, 2),
                "Passes all": "✓" if sr.passes_all else "✗",
            })
        st.dataframe(pd.DataFrame(sr_data))

    dr = st.session_state.get("design_result")
    if dr:
        st.subheader("Structural Design Summary")
        c1, c2 = st.columns(2)
        with c1:
            st.metric("dx [mm]", f"{dr.dx:.0f}")
            st.metric("Mu_x [kN·m/m]", f"{dr.Mu_x:.2f}")
            st.metric("Bar X", f"{dr.bar_x} @ {dr.spacing_x:.0f} mm")
            st.metric("φMn_x [kN·m/m]", f"{dr.phi_Mn_x:.2f}")
            st.metric("Shear X – φVc", f"{dr.phi_Vc_x:.1f} ≥ {dr.Vu_x:.1f} kN/m",
                      delta="OK" if dr.passes_shear_x else "FAIL")
        with c2:
            st.metric("dy [mm]", f"{dr.dy:.0f}")
            st.metric("Mu_y [kN·m/m]", f"{dr.Mu_y:.2f}")
            st.metric("Bar Y", f"{dr.bar_y} @ {dr.spacing_y:.0f} mm")
            st.metric("φMn_y [kN·m/m]", f"{dr.phi_Mn_y:.2f}")
            st.metric("Punching – φVc", f"{dr.phi_Vc2way:.1f} ≥ {dr.Vu2way:.1f} kN",
                      delta="OK" if dr.passes_punching else "FAIL")

        overall = "✅ PASS" if dr.passes_all else "❌ FAIL"
        st.subheader(f"Overall design: {overall}")


# ============================================================
# PAGE 4 – OPTIMIZATION
# ============================================================

elif selected_page == "Optimization":
    st.title("4 · Optimization")

    soil = st.session_state.get("soil")
    geom = st.session_state.get("geom")
    mats = st.session_state.get("materials")
    ls   = st.session_state.get("load_set")

    if not (soil and geom and mats and ls and ls.combinations):
        st.warning("Complete Inputs and Loads first.")
        st.stop()

    st.subheader("Optimization constraints")
    c1, c2, c3 = st.columns(3)
    with c1:
        B_min  = st.number_input("B_min [m]", 0.5, 3.0, 0.6, 0.1)
        B_max  = st.number_input("B_max [m]", 1.0, 8.0, 4.0, 0.1)
        L_min  = st.number_input("L_min [m]", 0.5, 3.0, 0.6, 0.1)
        L_max  = st.number_input("L_max [m]", 1.0, 8.0, 4.0, 0.1)
    with c2:
        h_min  = st.number_input("h_min [m]", 0.3, 1.0, 0.3, 0.05)
        h_max  = st.number_input("h_max [m]", 0.5, 2.0, 1.2, 0.05)
        step_B = st.number_input("Step B [m]", 0.05, 0.5, 0.10, 0.05)
        step_L = st.number_input("Step L [m]", 0.05, 0.5, 0.10, 0.05)
        step_h = st.number_input("Step h [m]", 0.05, 0.3, 0.10, 0.05)
    with c3:
        force_sq   = st.checkbox("Force square (B=L)", False)
        allow_pc   = st.checkbox("Allow partial contact", True)
        objective  = st.selectbox("Objective",
            ["min_area", "min_volume", "min_cost", "min_depth", "best_geotechnical"])
        lock_h     = st.checkbox(f"Lock h = {geom.h} m", False)

    if st.button("▶ Run Optimization", type="primary"):
        constraints = OptimizationConstraints(
            B_min=B_min, B_max=B_max, L_min=L_min, L_max=L_max,
            h_min=h_min, h_max=h_max,
            step_B=step_B, step_L=step_L, step_h=step_h,
            force_square=force_sq,
            allow_partial_contact=allow_pc,
            lock_h=lock_h,
        )
        obj_cfg = OptimizationObjective(objective=objective)
        stab_params = StabilityParams()

        with st.spinner("Running grid search…"):
            opt_res = optimize_footing(
                geom, ls, soil, mats, stab_params, constraints, obj_cfg
            )
        st.session_state["opt_result"] = opt_res

    opt = st.session_state.get("opt_result")
    if opt:
        if opt.converged and opt.best_geometry:
            bg = opt.best_geometry
            st.success(
                f"✅ Optimal solution: B={bg.B:.2f} m, L={bg.L:.2f} m, h={bg.h:.2f} m  "
                f"(objective={opt.objective_value:.3f})"
            )
            st.info(opt.reason)
        else:
            st.error(f"❌ No feasible solution found.\n\n{opt.reason}")

        st.subheader(f"Iterations: {opt.n_iterations}  |  Feasible: {opt.n_feasible}")
        if opt.feasible_results:
            feas_df = pd.DataFrame([
                {"B": r["B"], "L": r["L"], "h": r["h"], "objective": round(r.get("objective", 0), 3)}
                for r in opt.feasible_results
            ])
            st.dataframe(feas_df.sort_values("objective").head(20))


# ============================================================
# PAGE 5 – RESULTS
# ============================================================

elif selected_page == "Results":
    st.title("5 · Results & Export")

    summary = st.session_state.get("summary")
    if summary is None:
        st.warning("Run Analysis first.")
        st.stop()

    st.json(summary, expanded=False)

    st.subheader("Export")
    fmt = st.selectbox("Format", ["Excel (.xlsx)", "PDF (.pdf)", "Word (.docx)"])

    if st.button("⬇ Download report"):
        buf = io.BytesIO()
        try:
            if fmt.startswith("Excel"):
                from core.report import export_to_excel
                # Write to a temp path in cwd
                export_to_excel(summary, "report_output.xlsx")
                with open("report_output.xlsx", "rb") as f:
                    buf.write(f.read())
                st.download_button("Download Excel", data=buf.getvalue(),
                                   file_name="footing_report.xlsx")
            elif fmt.startswith("PDF"):
                from core.report import export_to_pdf
                export_to_pdf(summary, "report_output.pdf")
                with open("report_output.pdf", "rb") as f:
                    buf.write(f.read())
                st.download_button("Download PDF", data=buf.getvalue(),
                                   file_name="footing_report.pdf")
            elif fmt.startswith("Word"):
                from core.report import export_to_docx
                export_to_docx(summary, "report_output.docx")
                with open("report_output.docx", "rb") as f:
                    buf.write(f.read())
                st.download_button("Download Word", data=buf.getvalue(),
                                   file_name="footing_report.docx")
        except Exception as e:
            st.error(f"Export error: {e}")
