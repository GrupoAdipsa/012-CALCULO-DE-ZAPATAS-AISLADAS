"""
ui/tkinter_app.py
Interfaz gráfica en Tkinter para diseño de zapatas aisladas.

Ejecutar con:
    python ui/tkinter_app.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Optional
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import numpy as np

# Agregar raíz del proyecto al path
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from core.anchorage import check_moment_transfer
from core.base_rotation import generate_base_moment_rotation_curve
from core.combinations import CombinationFactors, generate_combinations
from core.loads import LoadCase, LoadCombination, LoadSet
from core.optimizer import OptimizationConstraints, OptimizationObjective, optimize_footing
from core.rc_design import MaterialProperties, design_footing
from core.report import generate_summary_dict
from core.soil_pressure import FootingGeometry, SoilProperties, analyze_pressure, compute_total_load
from core.stability import StabilityParams, check_stability


class ZapataApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Diseño de Zapatas Aisladas – ACI 318-19 / ASCE-7")
        self.geometry("1400x900")
        self.resizable(True, True)

        # Estado de la aplicación
        self.soil: Optional[SoilProperties] = None
        self.geom: Optional[FootingGeometry] = None
        self.mats: Optional[MaterialProperties] = None
        self.load_set = LoadSet()
        self.press_results = []
        self.stab_results = []
        self.design_result = None
        self.anch_result = None
        self.base_rotation_result = None
        self.opt_result = None
        self.summary = None
        self.critical_ultimate_combo = None
        self.critical_ultimate_pressure = None
        self.stability_params = StabilityParams()
        self.stability_source_label = "servicio"
        self.column_effective_length = 3.0
        self.base_theta_max = 0.02
        self.base_curve_axis = "auto"
        self.apply_anchorage_cap_mtheta = False
        self.assume_rigid_connection_mtheta = True
        self.pedestal_bx = 0.60
        self.pedestal_by = 0.60
        self.pedestal_h = 0.80
        self.logs_dir = os.path.join(_ROOT, "logs")
        self.latest_json_path = os.path.join(self.logs_dir, "latest_analysis.json")
        self.history_jsonl_path = os.path.join(self.logs_dir, "analysis_history.jsonl")

        self._build_ui()
        # Inicializa estado y visualizaciones con los valores por defecto.
        self._save_inputs()
        os.makedirs(self.logs_dir, exist_ok=True)

    def _export_json(self):
        if self.summary is None:
            messagebox.showwarning("Advertencia", "Ejecute el análisis primero.")
            return

        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("Todos", "*.*")],
            initialfile="reporte_zapata.json",
        )
        if not path:
            return

        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.summary, f, ensure_ascii=False, indent=2)
            messagebox.showinfo("Éxito", f"JSON guardado en:\n{path}")
        except Exception as ex:
            messagebox.showerror("Error", str(ex))

    # =========================================================
    # UI PRINCIPAL
    # =========================================================
    def _build_ui(self):
        # Encabezado
        header = tk.Frame(self, bg="#1f4e79", height=50)
        header.pack(fill="x")
        tk.Label(header, text="🏗  Diseño de Zapatas Aisladas",
                 bg="#1f4e79", fg="white",
                 font=("Arial", 15, "bold"), pady=10).pack(side="left", padx=15)
        tk.Label(header, text="ACI 318-19 / ASCE-7  |  Unidades SI",
                 bg="#1f4e79", fg="#a8d1f7",
                 font=("Arial", 9)).pack(side="right", padx=15)

        # Pestañas principales
        style = ttk.Style()
        style.configure("TNotebook.Tab", font=("Arial", 10), padding=[12, 5])

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=5, pady=5)

        self._build_tab_entradas()
        self._build_tab_cargas()
        self._build_tab_analisis()
        self._build_tab_optimizacion()
        self._build_tab_resultados()

    # =========================================================
    # PESTAÑA 1 – DATOS DE ENTRADA
    # =========================================================
    def _build_tab_entradas(self):
        f = ttk.Frame(self.nb)
        self.nb.add(f, text="1 · Datos de Entrada")

        # Marco izquierdo para inputs
        f_left = ttk.Frame(f)
        f_left.pack(side="left", fill="both", expand=False, padx=5, pady=5)

        tk.Label(f_left, text="Datos de Entrada del Proyecto",
                 font=("Arial", 13, "bold")).pack(anchor="w", padx=10, pady=(10, 5))

        # --- Suelo ---
        fs = ttk.LabelFrame(f_left, text="Propiedades del Suelo", padding=10)
        fs.pack(fill="x", padx=10, pady=5)
        self.e_qa    = self._lentry(fs, "Capacidad admisible qa [kPa]:", 0, "200.0")
        self.e_gam   = self._lentry(fs, "Peso unitario del suelo γ [kN/m³]:", 1, "18.0")
        self.e_Df    = self._lentry(fs, "Prof. de desplante Df [m]:", 2, "1.5")
        self.e_ks    = self._lentry(fs, "Módulo de subrasante ks [kN/m³] (opcional):", 3, "")

        # --- Geometría ---
        fg = ttk.LabelFrame(f_left, text="Geometría de la Zapata (inicial)", padding=10)
        fg.pack(fill="x", padx=10, pady=5)
        self.e_B   = self._lentry(fg, "Ancho B [m]:", 0, "2.20")
        self.e_L   = self._lentry(fg, "Largo L [m]:", 1, "2.20")
        self.e_h   = self._lentry(fg, "Espesor h [m]:", 2, "0.55")
        self.e_bx  = self._lentry(fg, "Dimensión columna bx [m]:", 3, "0.40")
        self.e_by  = self._lentry(fg, "Dimensión columna by [m]:", 4, "0.40")
        self.e_cov = self._lentry(fg, "Recubrimiento libre [m]:", 5, "0.075")

        fp = ttk.LabelFrame(f_left, text="Pedestal (para visualización 3D)", padding=10)
        fp.pack(fill="x", padx=10, pady=5)
        self.e_ped_bx = self._lentry(fp, "bx pedestal [m]:", 0, "0.60")
        self.e_ped_by = self._lentry(fp, "by pedestal [m]:", 1, "0.60")
        self.e_ped_h  = self._lentry(fp, "altura pedestal hp [m]:", 2, "0.80")

        # --- Materiales ---
        fm = ttk.LabelFrame(f_left, text="Propiedades de Materiales", padding=10)
        fm.pack(fill="x", padx=10, pady=5)
        self.e_fc    = self._lentry(fm, "f'c [MPa]:", 0, "21.0")
        self.e_fy    = self._lentry(fm, "fy [MPa]:", 1, "420.0")
        self.e_phi_f = self._lentry(fm, "φ flexión:", 2, "0.90")
        self.e_phi_v = self._lentry(fm, "φ cortante:", 3, "0.75")

        fbm = ttk.LabelFrame(f_left, text="Modelo de rigidez de base (curva M-θ)", padding=10)
        fbm.pack(fill="x", padx=10, pady=5)
        self.e_col_L = self._lentry(fbm, "Longitud efectiva columna [m]:", 0, "3.00")
        self.e_theta_max = self._lentry(fbm, "θ máxima para curva [mrad]:", 1, "20.0")
        tk.Label(fbm, text="Eje de la curva M-θ:", font=("Arial", 9)).grid(
            row=2, column=0, sticky="e", padx=5, pady=3)
        self.cb_base_axis = ttk.Combobox(fbm, values=["auto", "x", "y"], width=12, state="readonly")
        self.cb_base_axis.set("auto")
        self.cb_base_axis.grid(row=2, column=1, sticky="w", padx=5, pady=3)
        self.var_cap_mtheta = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            fbm,
            text="Aplicar tope de anclaje φMn en curva M-θ",
            variable=self.var_cap_mtheta,
        ).grid(row=3, column=0, columnspan=2, sticky="w", padx=5, pady=3)

        ttk.Button(f_left, text="💾  Guardar Datos de Entrada",
                   command=self._save_inputs).pack(pady=12, padx=10, fill="x")

        self.lbl_inp = tk.Label(f_left, text="", fg="green", font=("Arial", 10))
        self.lbl_inp.pack(padx=10)

        # Marco derecho para visualización 2D
        self.frame_entrada_plot = ttk.LabelFrame(f, text="Visualización 2D", padding=5)
        self.frame_entrada_plot.pack(side="right", fill="both", expand=True, padx=5, pady=5)
        self.canvas_2d_entrada = None
        self.fig_2d_entrada = None

    def _save_inputs(self):
        try:
            ks_text = self.e_ks.get().strip()
            ks_value = float(ks_text) if ks_text else None
            pedestal_height = max(float(self.e_ped_h.get()), 0.0)
            self.soil = SoilProperties(
                qa=float(self.e_qa.get()),
                gamma_soil=float(self.e_gam.get()),
                Df=float(self.e_Df.get()),
                ks=ks_value,
            )
            self.geom = FootingGeometry(
                B=float(self.e_B.get()), L=float(self.e_L.get()),
                h=float(self.e_h.get()), bx=float(self.e_bx.get()),
                by=float(self.e_by.get()), cover=float(self.e_cov.get()),
                pedestal_height=pedestal_height,
            )
            self.mats = MaterialProperties(
                fc=float(self.e_fc.get()), fy=float(self.e_fy.get()),
                phi_flexure=float(self.e_phi_f.get()),
                phi_shear=float(self.e_phi_v.get()),
            )
            self.column_effective_length = max(float(self.e_col_L.get()), 0.10)
            self.base_theta_max = max(float(self.e_theta_max.get()) / 1000.0, 0.001)
            self.base_curve_axis = self.cb_base_axis.get().strip().lower() or "auto"
            self.apply_anchorage_cap_mtheta = bool(self.var_cap_mtheta.get())
            self.pedestal_bx = max(float(self.e_ped_bx.get()), self.geom.bx)
            self.pedestal_by = max(float(self.e_ped_by.get()), self.geom.by)
            self.pedestal_h = pedestal_height
            self.lbl_inp.config(text="✓ Datos guardados correctamente.", fg="green")
            self._draw_footing_2d_entrada()
            self._draw_loads_diagram()
        except Exception as ex:
            messagebox.showerror("Error", f"Error en datos de entrada:\n{ex}")

    def _draw_footing_2d_entrada(self):
        """Dibuja la vista 2D de la zapata con dimensiones."""
        if not self.geom:
            return

        self._clear_plot_frame(self.frame_entrada_plot)

        fig = Figure(figsize=(5, 5), dpi=80)
        ax = fig.add_subplot(111)

        B, L, h, bx, by = self.geom.B, self.geom.L, self.geom.h, self.geom.bx, self.geom.by
        pbx, pby = self.pedestal_bx, self.pedestal_by

        # Dibujar zapata (vista superior)
        ax.add_patch(plt.Rectangle((-B/2, -L/2), B, L, fill=False, edgecolor="blue", linewidth=2.5))
        ax.text(0, -L/2 - 0.15, f"B = {B:.2f} m", ha="center", fontsize=10, color="blue", weight="bold")
        ax.text(-B/2 - 0.25, 0, f"L = {L:.2f} m", ha="right", va="center", fontsize=10, color="blue", weight="bold", rotation=90)

        # Dibujar columna
        ax.add_patch(plt.Rectangle((-bx/2, -by/2), bx, by, fill=True, facecolor="lightgray", 
                                    edgecolor="red", linewidth=2, alpha=0.7))
        ax.text(0, 0, f"Columna\n{bx:.2f}×{by:.2f}", ha="center", va="center", fontsize=9, weight="bold")

        # Pedestal en planta para referencia geométrica
        ax.add_patch(plt.Rectangle((-pbx/2, -pby/2), pbx, pby, fill=False,
                       edgecolor="darkorange", linewidth=1.8, linestyle="--"))
        ax.text(0, pby/2 + 0.10, f"Pedestal {pbx:.2f}×{pby:.2f} m", ha="center",
            va="bottom", fontsize=8, color="darkorange")

        # Ejes
        ax.axhline(0, color="k", linestyle="--", linewidth=0.8, alpha=0.5)
        ax.axvline(0, color="k", linestyle="--", linewidth=0.8, alpha=0.5)
        ax.arrow(0, -L/2 - 0.5, 0.5, 0, head_width=0.1, head_length=0.1, fc="green", ec="green")
        ax.text(0.6, -L/2 - 0.5, "X", fontsize=12, color="green", weight="bold")
        ax.arrow(-B/2 - 0.5, 0, 0, 0.5, head_width=0.1, head_length=0.1, fc="purple", ec="purple")
        ax.text(-B/2 - 0.5, 0.6, "Y", fontsize=12, color="purple", weight="bold")

        # Espesor
        ax.text(B/2 + 0.2, L/2 + 0.2, f"h = {h:.2f} m\n(espesor)", fontsize=9, 
                bbox=dict(boxstyle="round", facecolor="lightyellow", alpha=0.8))

        ax.set_xlim(-B/2 - 0.8, B/2 + 0.8)
        ax.set_ylim(-L/2 - 0.8, L/2 + 0.8)
        ax.set_aspect("equal")
        ax.grid(True, alpha=0.3)
        ax.set_title("Vista Superior de la Zapata", fontsize=12, weight="bold")
        ax.set_xlabel("X (m)")
        ax.set_ylabel("Y (m)")

        canvas = FigureCanvasTkAgg(fig, master=self.frame_entrada_plot)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)
        self.canvas_2d_entrada = canvas
        self.fig_2d_entrada = fig

    # =========================================================
    # PESTAÑA 2 – CARGAS
    # =========================================================
    def _build_tab_cargas(self):
        f = ttk.Frame(self.nb)
        self.nb.add(f, text="2 · Cargas")

        # Marco izquierdo
        f_left = ttk.Frame(f)
        f_left.pack(side="left", fill="both", expand=False, padx=5, pady=5)

        nb2 = ttk.Notebook(f_left)
        nb2.pack(fill="x", padx=0, pady=0)

        f_casos  = ttk.Frame(nb2)
        nb2.add(f_casos, text="Casos de Carga")
        self._build_casos(f_casos)

        f_manual = ttk.Frame(nb2)
        nb2.add(f_manual, text="Combinación Manual")
        self._build_manual_combo(f_manual)

        f_imp = ttk.Frame(nb2)
        nb2.add(f_imp, text="Importar Archivo")
        self._build_import(f_imp)

        # Tabla de combinaciones (abajo a la izquierda)
        fc_t = ttk.LabelFrame(f_left, text="Combinaciones de carga actuales", padding=5)
        fc_t.pack(fill="both", expand=True, padx=0, pady=5)
        self.tree_combos = self._treeview(fc_t,
            ("Nombre", "Tipo", "N [kN]", "Vx [kN]", "Vy [kN]", "Mx [kN·m]", "My [kN·m]"))

        # Marco derecho para visualización de cargas
        self.frame_loads_plot = ttk.LabelFrame(f, text="Visualización de Cargas (2D/3D)", padding=5)
        self.frame_loads_plot.pack(side="right", fill="both", expand=True, padx=5, pady=5)
        self.canvas_loads = None

    def _build_casos(self, p):
        tk.Label(p, text="Agregar Caso de Carga Básico",
                 font=("Arial", 11, "bold")).grid(row=0, column=0, columnspan=8,
                                                   sticky="w", padx=10, pady=5)
        labels   = ["Nombre:", "Tipo:", "N [kN]:", "Vx [kN]:", "Vy [kN]:", "Mx [kN·m]:", "My [kN·m]:"]
        defaults = ["Muerta", "dead",  "800.0",    "20.0",      "15.0",     "50.0",        "30.0"]
        self._lc = []
        for i, (lb, dv) in enumerate(zip(labels, defaults)):
            r, c = 1 + i // 4, (i % 4) * 2
            tk.Label(p, text=lb).grid(row=r, column=c, sticky="e", padx=5, pady=3)
            if lb == "Tipo:":
                w = ttk.Combobox(p, width=12,
                    values=["dead","live","roof_live","wind_x","wind_y",
                            "seismic_x","seismic_y","other"])
                w.set(dv)
            else:
                w = ttk.Entry(p, width=10)
                w.insert(0, dv)
            w.grid(row=r, column=c + 1, sticky="w", padx=5, pady=3)
            self._lc.append(w)

        bf = tk.Frame(p)
        bf.grid(row=3, column=0, columnspan=8, pady=8)
        ttk.Button(bf, text="➕  Agregar Caso",
                   command=self._add_case).pack(side="left", padx=5)
        ttk.Button(bf, text="⚡  Generar Combinaciones ACI/ASCE-7",
                   command=self._gen_combos).pack(side="left", padx=5)
        ttk.Button(bf, text="🗑  Limpiar Todo",
                   command=self._clear_loads).pack(side="left", padx=5)

        self.lbl_carga = tk.Label(p, text="", fg="green")
        self.lbl_carga.grid(row=4, column=0, columnspan=8)

        ft = ttk.LabelFrame(p, text="Casos definidos", padding=3)
        ft.grid(row=5, column=0, columnspan=8, sticky="nsew", padx=5, pady=5)
        p.rowconfigure(5, weight=1)
        p.columnconfigure(7, weight=1)
        self.tree_cases = self._treeview(ft,
            ("Nombre", "Tipo", "N [kN]", "Vx [kN]", "Vy [kN]", "Mx [kN·m]", "My [kN·m]"))

    def _add_case(self):
        try:
            e = self._lc
            case = LoadCase(
                name=e[0].get(), load_type=e[1].get(),
                N=float(e[2].get()), Vx=float(e[3].get()), Vy=float(e[4].get()),
                Mx=float(e[5].get()), My=float(e[6].get()),
            )
            self.load_set.add_case(case)
            self._refresh_cases()
            self._draw_loads_diagram()
            self.lbl_carga.config(text=f"✓ Caso '{case.name}' agregado.", fg="green")
        except Exception as ex:
            messagebox.showerror("Error", str(ex))

    def _gen_combos(self):
        if not self.load_set.cases:
            messagebox.showwarning("Advertencia", "Agregue al menos un caso de carga.")
            return
        try:
            self.load_set = generate_combinations(self.load_set, CombinationFactors.aci_asce7())
            self._refresh_combos()
            self._draw_loads_diagram()
            n = len(self.load_set.combinations)
            self.lbl_carga.config(text=f"✓ {n} combinaciones generadas.", fg="green")
        except Exception as ex:
            messagebox.showerror("Error", str(ex))

    def _clear_loads(self):
        if messagebox.askyesno("Confirmar", "¿Limpiar todos los casos y combinaciones?"):
            self.load_set = LoadSet()
            self._refresh_cases()
            self._refresh_combos()

    def _build_manual_combo(self, p):
        tk.Label(p, text="Agregar Combinación Manual",
                 font=("Arial", 11, "bold")).grid(row=0, column=0, columnspan=2,
                                                   sticky="w", padx=10, pady=5)
        self.mc_name = self._lentry(p, "Nombre:", 1, "U-Manual")
        tk.Label(p, text="Tipo:").grid(row=2, column=0, sticky="e", padx=5)
        self.mc_type = ttk.Combobox(p, values=["ultimate", "service"], width=12)
        self.mc_type.set("ultimate")
        self.mc_type.grid(row=2, column=1, sticky="w", padx=5)
        self.mc_N  = self._lentry(p, "N [kN]:", 3, "1200.0")
        self.mc_Vx = self._lentry(p, "Vx [kN]:", 4, "30.0")
        self.mc_Vy = self._lentry(p, "Vy [kN]:", 5, "22.0")
        self.mc_Mx = self._lentry(p, "Mx [kN·m]:", 6, "75.0")
        self.mc_My = self._lentry(p, "My [kN·m]:", 7, "45.0")
        ttk.Button(p, text="➕  Agregar Combinación",
                   command=self._add_manual).grid(row=8, column=0, columnspan=2, pady=8)

    def _add_manual(self):
        try:
            combo = LoadCombination(
                name=self.mc_name.get(), combo_type=self.mc_type.get(),
                N=float(self.mc_N.get()), Vx=float(self.mc_Vx.get()),
                Vy=float(self.mc_Vy.get()), Mx=float(self.mc_Mx.get()),
                My=float(self.mc_My.get()),
            )
            self.load_set.add_combination(combo)
            self._refresh_combos()
            self._draw_loads_diagram()
            messagebox.showinfo("Éxito", f"Combinación '{combo.name}' agregada.")
        except Exception as ex:
            messagebox.showerror("Error", str(ex))

    def _build_import(self, p):
        tk.Label(p, text="Importar combinaciones desde archivo",
                 font=("Arial", 11, "bold")).pack(padx=10, pady=10)
        tk.Label(p, text="Formatos soportados: .xlsx  |  .csv").pack()
        ttk.Button(p, text="📂  Seleccionar Archivo",
                   command=self._import_file).pack(pady=10)
        self.lbl_imp = tk.Label(p, text="", fg="green")
        self.lbl_imp.pack()

    def _import_file(self):
        path = filedialog.askopenfilename(
            filetypes=[("Excel/CSV", "*.xlsx *.csv"), ("Todos", "*.*")])
        if not path:
            return
        try:
            if path.endswith(".xlsx"):
                from io.excel_import import import_combinations_excel
                tmp = import_combinations_excel(path)
            else:
                from io.csv_import import import_combinations_csv
                tmp = import_combinations_csv(path)
            for combo in tmp.combinations:
                self.load_set.add_combination(combo)
            self._refresh_combos()
            self._draw_loads_diagram()
            self.lbl_imp.config(
                text=f"✓ {len(tmp.combinations)} combinaciones importadas.", fg="green")
        except Exception as ex:
            messagebox.showerror("Error al importar", str(ex))

    def _draw_loads_diagram(self):
        """Dibuja diagrama de cargas aplicadas (último caso/combinación)."""
        if not self.load_set.combinations and not self.load_set.cases:
            return
        if not self.geom:
            return

        combo = self.load_set.combinations[-1] if self.load_set.combinations else self.load_set.cases[-1]

        self._clear_plot_frame(self.frame_loads_plot)

        fig = Figure(figsize=(6, 5), dpi=80)
        ax = fig.add_subplot(111, projection="3d")

        B, L, h = self.geom.B, self.geom.L, self.geom.h
        bx, by = self.geom.bx, self.geom.by
        pbx, pby, hp = self.pedestal_bx, self.pedestal_by, self.pedestal_h
        Df = self.soil.Df if self.soil else 0.0
        N, Vx, Vy, Mx, My = combo.N, combo.Vx, combo.Vy, combo.Mx, combo.My
        z_top_footing = h
        z_top_pedestal = h + hp

        # Conversión de momentos por brazo vertical con convención del proyecto.
        # El usuario define e = Df (medido desde la parte superior del pedestal).
        lever_arm = Df
        delta_mx = Vy * lever_arm
        delta_my = Vx * lever_arm
        mx_equiv = Mx + delta_mx
        my_equiv = My + delta_my

        # Dibujar zapata (base)
        corners = np.array([[-B/2, -L/2, 0], [B/2, -L/2, 0], 
                            [B/2, L/2, 0], [-B/2, L/2, 0], [-B/2, -L/2, 0]])
        ax.plot(corners[:, 0], corners[:, 1], corners[:, 2], "b-", linewidth=2, label="Zapata")

        # Dibujar cabeza de zapata
        top_corners = np.array([[-B/2, -L/2, z_top_footing], [B/2, -L/2, z_top_footing], 
                               [B/2, L/2, z_top_footing], [-B/2, L/2, z_top_footing], [-B/2, -L/2, z_top_footing]])
        ax.plot(top_corners[:, 0], top_corners[:, 1], top_corners[:, 2], "b-", linewidth=2)

        # Columnas verticales
        for x, y in [[-B/2, -L/2], [B/2, -L/2], [B/2, L/2], [-B/2, L/2]]:
            ax.plot([x, x], [y, y], [0, z_top_footing], "b-", linewidth=1.5)

        # Dibujar pedestal
        ped_bot = np.array([[-pbx/2, -pby/2, z_top_footing], [pbx/2, -pby/2, z_top_footing],
                            [pbx/2, pby/2, z_top_footing], [-pbx/2, pby/2, z_top_footing], [-pbx/2, -pby/2, z_top_footing]])
        ped_top = np.array([[-pbx/2, -pby/2, z_top_pedestal], [pbx/2, -pby/2, z_top_pedestal],
                            [pbx/2, pby/2, z_top_pedestal], [-pbx/2, pby/2, z_top_pedestal], [-pbx/2, -pby/2, z_top_pedestal]])
        ax.plot(ped_bot[:, 0], ped_bot[:, 1], ped_bot[:, 2], color="darkorange", linewidth=2, label="Pedestal")
        ax.plot(ped_top[:, 0], ped_top[:, 1], ped_top[:, 2], color="darkorange", linewidth=2)
        for x, y in [[-pbx/2, -pby/2], [pbx/2, -pby/2], [pbx/2, pby/2], [-pbx/2, pby/2]]:
            ax.plot([x, x], [y, y], [z_top_footing, z_top_pedestal], color="darkorange", linewidth=1.5)

        # Dibujar columna corta sobre pedestal para mostrar punto de aplicación de cargas.
        col_h = 0.50
        col_bot = np.array([[-bx/2, -by/2, z_top_pedestal], [bx/2, -by/2, z_top_pedestal],
                            [bx/2, by/2, z_top_pedestal], [-bx/2, by/2, z_top_pedestal], [-bx/2, -by/2, z_top_pedestal]])
        col_top = np.array([[-bx/2, -by/2, z_top_pedestal + col_h], [bx/2, -by/2, z_top_pedestal + col_h],
                            [bx/2, by/2, z_top_pedestal + col_h], [-bx/2, by/2, z_top_pedestal + col_h], [-bx/2, -by/2, z_top_pedestal + col_h]])
        ax.plot(col_bot[:, 0], col_bot[:, 1], col_bot[:, 2], color="red", linewidth=1.8, label="Columna")
        ax.plot(col_top[:, 0], col_top[:, 1], col_top[:, 2], color="red", linewidth=1.8)
        for x, y in [[-bx/2, -by/2], [bx/2, -by/2], [bx/2, by/2], [-bx/2, by/2]]:
            ax.plot([x, x], [y, y], [z_top_pedestal, z_top_pedestal + col_h], color="red", linewidth=1.3)

        # Línea de terreno (z = Df + h aprox en esta vista didáctica)
        z_ground = z_top_footing + Df
        gx = np.array([-B / 2 - 0.6, B / 2 + 0.6])
        gy = np.array([-L / 2 - 0.6, L / 2 + 0.6])
        for yy in gy:
            ax.plot(gx, np.full_like(gx, yy), np.full_like(gx, z_ground), color="saddlebrown", linestyle=":", linewidth=1)

        # Fuerzas
        scale = 0.008
        x0, y0, z0 = 0.0, 0.0, z_top_pedestal + col_h
        if N > 0:
            ax.quiver(x0, y0, z0, 0, 0, -N * scale, color="crimson", arrow_length_ratio=0.18, linewidth=2.2)
            ax.text(x0 + 0.15, y0 - 0.15, z0 - N * scale / 2,
                    f"N={N:.0f} kN", fontsize=9, color="crimson", weight="bold")

        if Vx != 0:
            vx_len = np.sign(Vx) * max(abs(Vx) * scale * 0.06, 0.35)
            ax.quiver(x0, y0, z0, vx_len, 0, 0, color="green", arrow_length_ratio=0.18, linewidth=2)
            ax.text(x0 + vx_len * 0.55, y0 - 0.10, z0 + 0.05,
                    f"Vx={Vx:.0f} kN", fontsize=8, color="green")

        if Vy != 0:
            vy_len = np.sign(Vy) * max(abs(Vy) * scale * 0.06, 0.35)
            ax.quiver(x0, y0, z0, 0, vy_len, 0, color="orange", arrow_length_ratio=0.18, linewidth=2)
            ax.text(x0 - 0.10, y0 + vy_len * 0.55, z0 + 0.05,
                    f"Vy={Vy:.0f} kN", fontsize=8, color="orange")

        # Indicadores de momento con sentido de giro (arcos en torno a ejes X e Y).
        radius = min(B, L) * 0.22
        t = np.linspace(0, 1.35 * np.pi, 64)
        if abs(Mx) > 1e-6:
            y_arc = radius * np.cos(t)
            z_arc = z0 + radius * np.sin(t)
            x_arc = np.full_like(t, x0 + 0.25)
            ax.plot(x_arc, y_arc, z_arc, color="purple", linewidth=2)
            ax.quiver(x_arc[-2], y_arc[-2], z_arc[-2],
                      0, y_arc[-1] - y_arc[-2], z_arc[-1] - z_arc[-2],
                      color="purple", arrow_length_ratio=0.4, linewidth=2)
            ax.text(x0 + 0.35, radius + 0.05, z0 + 0.1, f"Mx={Mx:.1f} kN.m", color="purple", fontsize=8)
        if abs(My) > 1e-6:
            x_arc = radius * np.cos(t)
            z_arc = z0 + radius * np.sin(t)
            y_arc = np.full_like(t, y0 + 0.25)
            ax.plot(x_arc, y_arc, z_arc, color="teal", linewidth=2)
            ax.quiver(x_arc[-2], y_arc[-2], z_arc[-2],
                      x_arc[-1] - x_arc[-2], 0, z_arc[-1] - z_arc[-2],
                      color="teal", arrow_length_ratio=0.4, linewidth=2)
            ax.text(radius + 0.05, y0 + 0.35, z0 + 0.1, f"My={My:.1f} kN.m", color="teal", fontsize=8)

        # Cotas geométricas y notas de aplicación de cargas.
        ax.text(B / 2 + 0.08, -L / 2 - 0.15, 0.02, f"B={B:.2f} m", fontsize=8, color="navy")
        ax.text(-B / 2 - 0.25, L / 2 + 0.05, 0.02, f"L={L:.2f} m", fontsize=8, color="navy")
        ax.text(pbx / 2 + 0.05, pby / 2 + 0.05, z_top_footing + hp / 2, f"hp={hp:.2f} m", fontsize=8, color="darkorange")
        ax.text(bx / 2 + 0.05, -by / 2, z_top_pedestal + col_h / 2, f"bx={bx:.2f} m\nby={by:.2f} m", fontsize=7, color="red")

        info_text = (
            f"Cargas aplicadas en cabeza de pedestal (z={z0:.2f} m)\n"
            f"Brazo vertical usado: e = Df = {lever_arm:.2f} m\n"
            f"Relleno sobre zapata: h_relleno = Df - h = {Df:.2f} - {h:.2f} = {max(Df - h, 0.0):.2f} m\n"
            f"DeltaMx = Vy*e = {Vy:.1f}*{lever_arm:.2f} = {delta_mx:.2f} kN.m\n"
            f"DeltaMy = Vx*e = {Vx:.1f}*{lever_arm:.2f} = {delta_my:.2f} kN.m\n"
            f"Mx equiv en cimentacion = {mx_equiv:.2f} kN.m\n"
            f"My equiv en cimentacion = {my_equiv:.2f} kN.m"
        )
        ax.text2D(0.02, 0.02, info_text, transform=ax.transAxes,
                  fontsize=8, bbox=dict(boxstyle="round", facecolor="white", alpha=0.85))

        ax.set_xlabel("X (m)")
        ax.set_ylabel("Y (m)")
        ax.set_zlabel("Z (m)")
        ax.set_title(f"Carga aplicada en pedestal: {combo.name}", fontsize=11, weight="bold")
        ax.set_xlim(-B/2 - 0.5, B/2 + 0.5)
        ax.set_ylim(-L/2 - 0.5, L/2 + 0.5)
        ax.set_zlim(-0.2, z_top_pedestal + col_h + 0.6)
        ax.view_init(elev=22, azim=-52)
        ax.legend(loc="upper right", fontsize=8)

        canvas = FigureCanvasTkAgg(fig, master=self.frame_loads_plot)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)
        self.canvas_loads = canvas

    # =========================================================
    # PESTAÑA 3 – ANÁLISIS
    # =========================================================
    def _build_tab_analisis(self):
        f = ttk.Frame(self.nb)
        self.nb.add(f, text="3 · Análisis")

        # Marco izquierdo
        f_left = ttk.Frame(f)
        f_left.pack(side="left", fill="both", expand=False, padx=5, pady=5)

        # Parámetros
        fsp = ttk.LabelFrame(f_left, text="Parámetros de Estabilidad", padding=8)
        fsp.pack(fill="x", padx=5, pady=5)
        self.e_mu   = self._lentry_h(fsp, "Coef. de fricción μ:", "0.45")
        self.e_fssl = self._lentry_h(fsp, "FS deslizamiento mín.:", "1.5")
        self.e_fsot = self._lentry_h(fsp, "FS volteo mín.:", "1.5")
        self.var_pc = tk.BooleanVar(value=True)
        ttk.Checkbutton(fsp, text="Permitir contacto parcial",
                        variable=self.var_pc).pack(side="left", padx=10)

        ttk.Button(f_left, text="▶  Ejecutar Análisis",
                   command=self._run_analysis).pack(pady=8, padx=5, fill="x")

        self.lbl_anal = tk.Label(f_left, text="", fg="green", font=("Arial", 9))
        self.lbl_anal.pack(padx=5)

        nb3 = ttk.Notebook(f_left)
        nb3.pack(fill="both", expand=True, padx=5, pady=5)

        # Sub-pestaña presiones
        fp = ttk.Frame(nb3)
        nb3.add(fp, text="Presiones")
        self.tree_press = self._treeview(fp,
            ("Combo", "N [kN]", "q_max [kPa]", "q_min [kPa]", "ex [m]", "ey [m]", "✓/✗"))

        # Sub-pestaña estabilidad
        fe = ttk.Frame(nb3)
        nb3.add(fe, text="Estabilidad")
        self.tree_stab = self._treeview(fe,
            ("Combo", "FS_desl_x", "FS_desl_y", "FS_volt_x", "FS_volt_y", "FS_sub", "✓/✗"))

        # Marco derecho para gráficos
        self.frame_analysis_plot = ttk.LabelFrame(f, text="Resultados Visuales", padding=5)
        self.frame_analysis_plot.pack(side="right", fill="both", expand=True, padx=5, pady=5)
        self.canvas_analysis = None

    def _run_analysis(self):
        if not (self.soil and self.geom and self.mats):
            messagebox.showwarning("Advertencia", "Complete los datos de entrada primero.")
            return
        if not self.load_set.combinations:
            messagebox.showwarning("Advertencia",
                "Agregue combinaciones en la pestaña Cargas.")
            return
        try:
            sp = StabilityParams(
                mu_friction=float(self.e_mu.get()),
                FS_sliding_min=float(self.e_fssl.get()),
                FS_overturning_min=float(self.e_fsot.get()),
            )
            self.stability_params = sp
            combos = self.load_set.combinations
            allow_pc = self.var_pc.get()

            prs = [analyze_pressure(c, self.geom, self.soil,
                                    allow_partial_contact=allow_pc)
                   for c in combos]
            service_combos = self.load_set.get_service_combos()
            stability_combos = service_combos if service_combos else combos
            self.stability_source_label = "servicio" if service_combos else "todas las combinaciones"
            srs = [check_stability(c, self.geom, self.soil, sp)
                   for c in stability_combos]

            ult_combos = self.load_set.get_ultimate_combos()
            ult_prs    = [pr for pr, c in zip(prs, combos)
                          if c.combo_type == "ultimate"]
            dr = None
            if ult_combos and ult_prs:
                idx = int(np.argmax([pr.q_max for pr in ult_prs]))
                dr = design_footing(ult_combos[idx], self.geom, self.soil,
                                    self.mats, ult_prs[idx])
                self.critical_ultimate_combo = ult_combos[idx]
                self.critical_ultimate_pressure = ult_prs[idx]

            max_c  = max(combos, key=lambda c: abs(c.Mx) + abs(c.My))
            pr_max = prs[combos.index(max_c)]
            anch   = check_moment_transfer(max_c, self.geom, self.mats, pr_max)
            base_rotation = generate_base_moment_rotation_curve(
                combo=max_c,
                geom=self.geom,
                soil=self.soil,
                materials=self.mats,
                anchorage_result=anch,
                column_effective_length=self.column_effective_length,
                theta_max=self.base_theta_max,
                axis=None if self.base_curve_axis == "auto" else self.base_curve_axis,
                apply_anchorage_cap=self.apply_anchorage_cap_mtheta,
                assume_rigid_connection=self.assume_rigid_connection_mtheta,
            )

            self.press_results = prs
            self.stab_results  = srs
            self.design_result = dr
            self.anch_result   = anch
            self.base_rotation_result = base_rotation
            self.summary = self._build_summary_payload()
            self._persist_analysis_log()

            self._refresh_press_table()
            self._refresh_stab_table()
            self._draw_analysis_charts()
            self._refresh_results_view()
            self.lbl_anal.config(text="✓ Análisis OK", fg="green")
        except Exception as ex:
            messagebox.showerror("Error", f"Error en análisis:\n{str(ex)[:200]}")

    def _refresh_press_table(self):
        self.tree_press.delete(*self.tree_press.get_children())
        for pr in self.press_results:
            pasok = "✓" if pr.passes_qa else "✗"
            self.tree_press.insert("", "end", values=(
                pr.combo_name[:20], f"{pr.N_total:.0f}", f"{pr.q_max:.1f}",
                f"{pr.q_min:.1f}", f"{pr.eccentricity_x:.3f}", f"{pr.eccentricity_y:.3f}", pasok,
            ))

    def _refresh_stab_table(self):
        self.tree_stab.delete(*self.tree_stab.get_children())
        for sr in self.stab_results:
            pasok = "✓" if sr.passes_all else "✗"
            self.tree_stab.insert("", "end", values=(
                sr.combo_name[:20], f"{sr.FS_sliding_x:.2f}", f"{sr.FS_sliding_y:.2f}",
                f"{sr.FS_overturning_x:.2f}", f"{sr.FS_overturning_y:.2f}",
                f"{sr.FS_uplift:.2f}", pasok,
            ))

    def _draw_analysis_charts(self):
        """Dibuja gráficos de presiones y estabilidad."""
        self._clear_plot_frame(self.frame_analysis_plot)

        fig = Figure(figsize=(6, 5), dpi=80)

        # Gráfico 1: Presiones
        ax1 = fig.add_subplot(121)
        combo_names = [pr.combo_name[:10] for pr in self.press_results[:8]]
        q_maxs = [pr.q_max for pr in self.press_results[:8]]
        qa_val = self.soil.qa if self.soil else 200

        colors = ["green" if q <= qa_val else "red" for q in q_maxs]
        ax1.bar(range(len(combo_names)), q_maxs, color=colors, alpha=0.7)
        ax1.axhline(qa_val, color="blue", linestyle="--", linewidth=2, label=f"qa={qa_val} kPa")
        ax1.set_xticks(range(len(combo_names)))
        ax1.set_xticklabels(combo_names, rotation=45, ha="right", fontsize=8)
        ax1.set_ylabel("q_max [kPa]")
        ax1.set_title("Presiones de Contacto", fontsize=10, weight="bold")
        ax1.legend()
        ax1.grid(True, alpha=0.3)

        # Gráfico 2: Factores de seguridad
        ax2 = fig.add_subplot(122)
        combo_names2 = [sr.combo_name[:10] for sr in self.stab_results[:8]]
        fs_x = [sr.FS_sliding_x for sr in self.stab_results[:8]]

        colors2 = ["green" if fs >= 1.5 else "orange" for fs in fs_x]
        ax2.bar(range(len(combo_names2)), fs_x, color=colors2, alpha=0.7)
        ax2.axhline(1.5, color="blue", linestyle="--", linewidth=2, label="FS_mín=1.5")
        ax2.set_xticks(range(len(combo_names2)))
        ax2.set_xticklabels(combo_names2, rotation=45, ha="right", fontsize=8)
        ax2.set_ylabel("FS Deslizamiento")
        ax2.set_title("Factores de Seguridad", fontsize=10, weight="bold")
        ax2.legend()
        ax2.grid(True, alpha=0.3)

        fig.tight_layout()
        canvas = FigureCanvasTkAgg(fig, master=self.frame_analysis_plot)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)
        self.canvas_analysis = canvas

    # =========================================================
    # PESTAÑA 4 – OPTIMIZACIÓN
    # =========================================================
    def _build_tab_optimizacion(self):
        f = ttk.Frame(self.nb)
        self.nb.add(f, text="4 · Optimización")

        f_left = ttk.Frame(f)
        f_left.pack(side="left", fill="both", expand=False, padx=5, pady=5)

        tk.Label(f_left, text="Optimización de Geometría",
                 font=("Arial", 12, "bold")).pack(anchor="w", padx=5, pady=5)

        self.lbl_opt_context = tk.Label(
            f_left,
            text="Df usado en optimización: -- m (parámetro fijo)",
            font=("Arial", 9),
            fg="#1f4e79",
        )
        self.lbl_opt_context.pack(anchor="w", padx=5)

        self.lbl_opt_rules = tk.Label(
            f_left,
            text="Criterios exigidos: qa + estabilidad + RC",
            font=("Arial", 9),
            fg="#7a2f00",
        )
        self.lbl_opt_rules.pack(anchor="w", padx=5, pady=(0, 5))

        fc = ttk.LabelFrame(f_left, text="Restricciones", padding=8)
        fc.pack(fill="x", padx=5, pady=5)

        self.op_Bmin  = self._lentry(fc, "B_min [m]:", 0, "0.80")
        self.op_Bmax  = self._lentry(fc, "B_max [m]:", 1, "3.50")
        self.op_Lmin  = self._lentry(fc, "L_min [m]:", 2, "0.80")
        self.op_Lmax  = self._lentry(fc, "L_max [m]:", 3, "3.50")
        self.op_hmin  = self._lentry(fc, "h_min [m]:", 4, "0.35")
        self.op_hmax  = self._lentry(fc, "h_max [m]:", 5, "0.90")
        self.op_stpB  = self._lentry(fc, "Paso B [m]:", 6, "0.15")
        self.op_stpL  = self._lentry(fc, "Paso L [m]:", 7, "0.15")
        self.op_stph  = self._lentry(fc, "Paso h [m]:", 8, "0.10")

        self.op_sq = tk.BooleanVar(value=True)
        ttk.Checkbutton(fc, text="B = L (cuadrada)",
                        variable=self.op_sq).grid(row=9, column=0, columnspan=2, sticky="w", padx=5, pady=5)

        self.op_ignore_anchorage = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            fc,
            text="Ignorar anclaje por ahora (revisar aparte)",
            variable=self.op_ignore_anchorage,
            command=self._update_optimization_rule_label,
        ).grid(row=10, column=0, columnspan=2, sticky="w", padx=5, pady=5)

        self.op_apply_best = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            fc,
            text="Aplicar solución óptima y recalcular análisis",
            variable=self.op_apply_best,
        ).grid(row=11, column=0, columnspan=2, sticky="w", padx=5, pady=5)

        tk.Label(fc, text="Objetivo:").grid(row=12, column=0, sticky="e", padx=5)
        self.op_obj = ttk.Combobox(fc, width=18,
            values=["min_area","min_volume","min_cost","min_depth"])
        self.op_obj.set("min_area")
        self.op_obj.grid(row=12, column=1, sticky="w", padx=5)

        self._update_optimization_rule_label()

        ttk.Button(f_left, text="▶  Optimizar",
                   command=self._run_opt).pack(pady=8, padx=5, fill="x")

        self.lbl_opt = tk.Label(f_left, text="", font=("Arial", 9), fg="green")
        self.lbl_opt.pack(padx=5)

        ft = ttk.LabelFrame(f_left, text="Top 10 soluciones", padding=3)
        ft.pack(fill="both", expand=True, padx=5, pady=5)
        self.tree_opt = self._treeview(ft, ("B [m]", "L [m]", "h [m]", "Objetivo", "Estado / motivo"))

        self.frame_opt_plot = ttk.LabelFrame(f, text="Geometría Óptima (3D)", padding=5)
        self.frame_opt_plot.pack(side="right", fill="both", expand=True, padx=5, pady=5)
        self.canvas_opt = None

    def _run_opt(self):
        if not (self.soil and self.geom and self.mats):
            messagebox.showwarning("Advertencia", "Complete los datos de entrada.")
            return
        if not self.load_set.combinations:
            messagebox.showwarning("Advertencia", "Agregue combinaciones primero.")
            return
        try:
            # Usa los mismos criterios del análisis para evitar inconsistencias
            # entre la solución optimizada y la verificación mostrada al usuario.
            allow_partial_contact = self.var_pc.get() if hasattr(self, "var_pc") else True
            stab_params = StabilityParams(
                mu_friction=float(self.e_mu.get()) if hasattr(self, "e_mu") else 0.45,
                FS_sliding_min=float(self.e_fssl.get()) if hasattr(self, "e_fssl") else 1.5,
                FS_overturning_min=float(self.e_fsot.get()) if hasattr(self, "e_fsot") else 1.5,
            )

            self.lbl_opt_context.config(
                text=(
                    f"Df usado en optimización: {self.soil.Df:.2f} m (parámetro fijo) | "
                    f"contacto parcial: {'si' if allow_partial_contact else 'no'}"
                )
            )
            constraints = OptimizationConstraints(
                B_min=float(self.op_Bmin.get()), B_max=float(self.op_Bmax.get()),
                L_min=float(self.op_Lmin.get()), L_max=float(self.op_Lmax.get()),
                h_min=float(self.op_hmin.get()), h_max=float(self.op_hmax.get()),
                step_B=float(self.op_stpB.get()), step_L=float(self.op_stpL.get()),
                step_h=float(self.op_stph.get()),
                force_square=self.op_sq.get(),
                allow_partial_contact=allow_partial_contact,
                require_anchorage_check=not self.op_ignore_anchorage.get(),
            )
            obj_cfg = OptimizationObjective(objective=self.op_obj.get())

            self.lbl_opt.config(text="⏳ Optimizando…", fg="orange")
            self.update()

            res = optimize_footing(
                self.geom, self.load_set, self.soil, self.mats,
                stab_params, constraints, obj_cfg,
            )
            self.opt_result = res

            self.tree_opt.delete(*self.tree_opt.get_children())
            if res.feasible_results:
                for r in sorted(res.feasible_results,
                                key=lambda x: x.get("objective", 0))[:10]:
                    self.tree_opt.insert("", "end", values=(
                        f"{r['B']:.2f}", f"{r['L']:.2f}", f"{r['h']:.2f}",
                        f"{r.get('objective', 0):.4f}",
                        "cumple",
                    ))
            elif res.all_results:
                for r in res.all_results[:10]:
                    fail_msg = ",".join(r.get("fail_reasons", [])) or "sin detalle"
                    self.tree_opt.insert("", "end", values=(
                        f"{r['B']:.2f}", f"{r['L']:.2f}", f"{r['h']:.2f}",
                        f"{r.get('objective', 0):.4f}",
                        fail_msg[:48],
                    ))

            if res.converged and res.best_geometry:
                bg = res.best_geometry
                best_result = min(
                    res.feasible_results,
                    key=lambda x: x.get("objective", float("inf")),
                ) if res.feasible_results else None
                status_text = "cumple geotecnia + estabilidad + RC"
                if not self.op_ignore_anchorage.get():
                    status_text += " + anclaje"
                self.lbl_opt.config(
                    text=(f"✅ B={bg.B:.2f} m, L={bg.L:.2f} m, h={bg.h:.2f} m | Df={self.soil.Df:.2f} m "
                          f"({res.n_feasible}/{res.n_iterations}) | {status_text}"),
                    fg="green")
                self._draw_optimal_3d(bg)

                if self.op_apply_best.get():
                    self._apply_optimized_geometry_and_reanalyze(bg)
            else:
                self.lbl_opt.config(text=f"❌ Sin solución segura | {res.reason}", fg="red")
        except Exception as ex:
            messagebox.showerror("Error", f"Error en optimización:\n{str(ex)[:200]}")

    def _update_optimization_rule_label(self) -> None:
        if self.op_ignore_anchorage.get():
            self.lbl_opt_rules.config(
                text="Criterios exigidos: qa + estabilidad + RC | anclaje = revisar aparte"
            )
        else:
            self.lbl_opt_rules.config(
                text="Criterios exigidos: qa + estabilidad + RC + anclaje"
            )

    def _apply_optimized_geometry_and_reanalyze(self, best_geom: FootingGeometry) -> None:
        """Aplica B/L/h óptimos al modelo y refresca análisis/resultados."""
        self.geom = FootingGeometry(
            B=best_geom.B,
            L=best_geom.L,
            h=best_geom.h,
            bx=self.geom.bx,
            by=self.geom.by,
            cover=self.geom.cover,
            pedestal_height=self.geom.pedestal_height,
            ex=self.geom.ex,
            ey=self.geom.ey,
        )

        # Sincroniza inputs para que el usuario vea claramente la geometría aplicada.
        self._set_entry_value(self.e_B, f"{best_geom.B:.2f}")
        self._set_entry_value(self.e_L, f"{best_geom.L:.2f}")
        self._set_entry_value(self.e_h, f"{best_geom.h:.2f}")

        self._draw_footing_2d_entrada()
        self._draw_loads_diagram()

        # Recalcula todo con la geometría optimizada para que resultados/exportes coincidan.
        self._run_analysis()
        self.lbl_opt.config(
            text=self.lbl_opt.cget("text") + " | aplicado y recalculado",
            fg="green",
        )

    def _draw_optimal_3d(self, geom_opt: FootingGeometry):
        """Dibuja la zapata óptima en 3D."""
        self._clear_plot_frame(self.frame_opt_plot)

        fig = Figure(figsize=(6, 5), dpi=80)
        ax = fig.add_subplot(111, projection="3d")

        B, L, h = geom_opt.B, geom_opt.L, geom_opt.h
        bx, by = geom_opt.bx, geom_opt.by

        # Zapata
        corners = np.array([[-B/2, -L/2, 0], [B/2, -L/2, 0], 
                           [B/2, L/2, 0], [-B/2, L/2, 0], [-B/2, -L/2, 0]])
        top = np.array([[-B/2, -L/2, h], [B/2, -L/2, h], 
                       [B/2, L/2, h], [-B/2, L/2, h], [-B/2, -L/2, h]])
        ax.plot(corners[:, 0], corners[:, 1], corners[:, 2], "b-", linewidth=2)
        ax.plot(top[:, 0], top[:, 1], top[:, 2], "b-", linewidth=2)
        for x, y in [[-B/2, -L/2], [B/2, -L/2], [B/2, L/2], [-B/2, L/2]]:
            ax.plot([x, x], [y, y], [0, h], "b-", linewidth=1)

        # Columna
        col_corners = np.array([[-bx/2, -by/2, h], [bx/2, -by/2, h],
                               [bx/2, by/2, h], [-bx/2, by/2, h], [-bx/2, -by/2, h]])
        col_top = np.array([[-bx/2, -by/2, h+0.5], [bx/2, -by/2, h+0.5],
                           [bx/2, by/2, h+0.5], [-bx/2, by/2, h+0.5], [-bx/2, -by/2, h+0.5]])
        ax.plot(col_corners[:, 0], col_corners[:, 1], col_corners[:, 2], "r-", linewidth=2)
        ax.plot(col_top[:, 0], col_top[:, 1], col_top[:, 2], "r-", linewidth=2)
        for x, y in [[-bx/2, -by/2], [bx/2, -by/2], [bx/2, by/2], [-bx/2, by/2]]:
            ax.plot([x, x], [y, y], [h, h+0.5], "r-", linewidth=1.5)

        # Anotaciones
        ax.text(0, -L/2 - 0.3, 0, f"B={B:.2f}m", ha="center", fontsize=10, weight="bold")
        ax.text(-B/2 - 0.3, 0, 0, f"L={L:.2f}m", ha="right", fontsize=10, weight="bold", rotation=90)
        ax.text(B/2 + 0.2, L/2 + 0.2, h/2, f"h={h:.2f}m", fontsize=9, weight="bold",
               bbox=dict(boxstyle="round", facecolor="lightyellow", alpha=0.7))

        ax.set_xlabel("X (m)")
        ax.set_ylabel("Y (m)")
        ax.set_zlabel("Z (m)")
        ax.set_title("Zapata Óptima (3D)", fontsize=12, weight="bold")
        ax.set_xlim(-B/2 - 0.5, B/2 + 0.5)
        ax.set_ylim(-L/2 - 0.5, L/2 + 0.5)
        ax.set_zlim(-0.2, h + 0.7)

        canvas = FigureCanvasTkAgg(fig, master=self.frame_opt_plot)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)
        self.canvas_opt = canvas

    # =========================================================
    # PESTAÑA 5 – RESULTADOS
    # =========================================================
    def _build_tab_resultados(self):
        f = ttk.Frame(self.nb)
        self.nb.add(f, text="5 · Resultados")

        bf = tk.Frame(f)
        bf.pack(fill="x", padx=10, pady=5)
        ttk.Button(bf, text="🔄  Actualizar detalle",
                   command=self._refresh_results_view).pack(side="left", padx=5)
        ttk.Button(bf, text="💾  Exportar JSON",
               command=self._export_json).pack(side="left", padx=5)
        ttk.Button(bf, text="📊  Excel",
                   command=lambda: self._export("xlsx")).pack(side="left", padx=5)
        ttk.Button(bf, text="📄  PDF",
                   command=lambda: self._export("pdf")).pack(side="left", padx=5)
        ttk.Button(bf, text="📝  Word",
                   command=lambda: self._export("docx")).pack(side="left", padx=5)

        split = ttk.PanedWindow(f, orient=tk.HORIZONTAL)
        split.pack(fill="both", expand=True, padx=10, pady=5)

        left = ttk.Frame(split)
        right = ttk.Frame(split)
        split.add(left, weight=3)
        split.add(right, weight=2)

        left_nb = ttk.Notebook(left)
        left_nb.pack(fill="both", expand=True)

        tab_trace = ttk.Frame(left_nb)
        left_nb.add(tab_trace, text="Traza de cálculos")
        self.txt_calc_trace = self._scrolled_text(tab_trace)

        tab_summary = ttk.Frame(left_nb)
        left_nb.add(tab_summary, text="Resumen JSON")
        self.txt_summary = self._scrolled_text(tab_summary)

        tab_eq = ttk.Frame(left_nb)
        left_nb.add(tab_eq, text="Ecuaciones")
        self.txt_equations = self._scrolled_text(tab_eq)

        tab_theory = ttk.Frame(left_nb)
        left_nb.add(tab_theory, text="Base teórica M-θ")
        self.txt_base_theory = self._scrolled_text(tab_theory)

        right_nb = ttk.Notebook(right)
        right_nb.pack(fill="both", expand=True)

        tab_ind = ttk.Frame(right_nb)
        right_nb.add(tab_ind, text="Indicadores")
        self.frame_results_plot = ttk.LabelFrame(tab_ind, text="Visualización de resultados", padding=5)
        self.frame_results_plot.pack(fill="both", expand=True)
        self.canvas_results = None

        tab_pr = ttk.Frame(right_nb)
        right_nb.add(tab_pr, text="Distribución de presión")
        self.frame_pressure_map = ttk.LabelFrame(tab_pr, text="Mapa de presiones q(x,y)", padding=5)
        self.frame_pressure_map.pack(fill="both", expand=True)
        self.canvas_pressure_map = None

        tab_br = ttk.Frame(right_nb)
        right_nb.add(tab_br, text="Base M-θ")
        self.lbl_base_rotation = tk.Label(tab_br, text="Ejecute el análisis para generar la curva M-θ.", justify="left", anchor="w")
        self.lbl_base_rotation.pack(fill="x", padx=6, pady=(6, 2))
        self.frame_base_rotation_plot = ttk.LabelFrame(tab_br, text="Curva Momento-Rotación de la base", padding=5)
        self.frame_base_rotation_plot.pack(fill="both", expand=True)
        self.canvas_base_rotation = None

    def _refresh_results_view(self):
        self._render_summary_json()
        self._render_calc_trace()
        self._render_equations()
        self._render_base_rotation_theory()
        self._render_base_rotation_summary()
        self._draw_results_visualization()
        self._draw_pressure_distribution()
        self._draw_base_rotation_curve()

    def _serialize_base_rotation(self) -> Optional[dict]:
        if self.base_rotation_result is None:
            return None

        br = self.base_rotation_result
        return {
            "combo": br.combo_name,
            "axis": br.axis,
            "axis_label": br.axis_label,
            "N_total [kN]": round(br.N_total, 2),
            "M_reference [kN.m]": round(br.M_reference, 2),
            "ks_used [kN/m3]": round(br.ks_used, 2),
            "ks_source": br.ks_source,
            "k_base_initial [kN.m/rad]": round(br.initial_rotational_stiffness, 2),
            "k_tangent_initial [kN.m/rad]": round(br.tangent_stiffness_initial, 2),
            "k_tangent_reference [kN.m/rad]": round(br.tangent_stiffness_reference, 2),
            "k_secant_reference [kN.m/rad]": round(br.secant_stiffness_reference, 2),
            "k_linear_equivalent [kN.m/rad]": round(br.linear_equivalent_stiffness, 2),
            "k_bilinear_1 [kN.m/rad]": round(br.bilinear_stiffness_1, 2),
            "k_bilinear_2 [kN.m/rad]": round(br.bilinear_stiffness_2, 2),
            "theta_break_bilinear [mrad]": round(br.bilinear_theta_break * 1000.0, 3),
            "moment_break_bilinear [kN.m]": round(br.bilinear_moment_break, 2),
            "k_column [kN.m/rad]": round(br.column_rotational_stiffness, 2),
            "stiffness_ratio": round(br.stiffness_ratio, 4),
            "classification": br.classification,
            "reference_moment_used [kN.m]": round(br.reference_moment_used, 3),
            "reference_theta [mrad]": round(br.reference_theta * 1000.0, 3),
            "reference_contact_ratio": round(br.reference_contact_ratio, 4),
            "no_uplift_at_reference": br.no_uplift_at_reference,
            "uplift_theta [mrad]": round(br.uplift_theta * 1000.0, 3) if br.uplift_theta is not None else None,
            "uplift_moment [kN.m]": round(br.uplift_moment, 2) if br.uplift_moment is not None else None,
            "moment_capacity [kN.m]": round(br.moment_capacity, 2) if br.moment_capacity is not None else None,
            "curve": [
                {
                    "theta_total_mrad": round(pt.theta_total * 1000.0, 4),
                    "theta_soil_mrad": round(pt.theta_soil * 1000.0, 4),
                    "moment_kNm": round(pt.moment, 3),
                    "contact_ratio": round(pt.contact_ratio, 4),
                    "q_max_kPa": round(pt.q_max, 3),
                    "q_min_linear_kPa": round(pt.q_min_linear, 3),
                }
                for pt in br.points
            ],
            "notes": br.notes,
        }

    def _build_summary_payload(self) -> dict:
        """Construye el JSON de resultados aunque no exista diseño estructural."""
        if self.design_result is not None:
            payload = generate_summary_dict(
                self.geom,
                self.soil,
                self.mats,
                self.press_results,
                self.stab_results,
                self.design_result,
                self.anch_result,
                self.opt_result,
            )
            payload["base_rotation"] = self._serialize_base_rotation()
            return payload

        payload = {
            "meta": {
                "status": "incompleto",
                "reason": "No hay diseño estructural disponible para esta corrida.",
                "timestamp": datetime.now().isoformat(timespec="seconds"),
            },
            "inputs": {
                "soil": {
                    "qa": self.soil.qa if self.soil else None,
                    "gamma_soil": self.soil.gamma_soil if self.soil else None,
                    "Df": self.soil.Df if self.soil else None,
                },
                "geometry": {
                    "B": self.geom.B if self.geom else None,
                    "L": self.geom.L if self.geom else None,
                    "h": self.geom.h if self.geom else None,
                    "bx": self.geom.bx if self.geom else None,
                    "by": self.geom.by if self.geom else None,
                    "cover": self.geom.cover if self.geom else None,
                },
            },
            "pressure_results": [
                {
                    "combo": pr.combo_name,
                    "q_max": pr.q_max,
                    "q_min": pr.q_min,
                    "ex": pr.eccentricity_x,
                    "ey": pr.eccentricity_y,
                    "contact_ratio": pr.contact_ratio,
                    "passes_qa": pr.passes_qa,
                }
                for pr in self.press_results
            ],
            "stability_results": [
                {
                    "combo": sr.combo_name,
                    "FS_sliding_x": sr.FS_sliding_x,
                    "FS_sliding_y": sr.FS_sliding_y,
                    "FS_overturning_x": sr.FS_overturning_x,
                    "FS_overturning_y": sr.FS_overturning_y,
                    "passes_all": sr.passes_all,
                }
                for sr in self.stab_results
            ],
        }
        payload["base_rotation"] = self._serialize_base_rotation()
        return payload

    def _build_log_snapshot(self) -> dict:
        return {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "inputs": {
                "soil": {
                    "qa": self.soil.qa if self.soil else None,
                    "gamma_soil": self.soil.gamma_soil if self.soil else None,
                    "Df": self.soil.Df if self.soil else None,
                },
                "geometry": {
                    "B": self.geom.B if self.geom else None,
                    "L": self.geom.L if self.geom else None,
                    "h": self.geom.h if self.geom else None,
                    "bx": self.geom.bx if self.geom else None,
                    "by": self.geom.by if self.geom else None,
                    "cover": self.geom.cover if self.geom else None,
                },
                "analysis_settings": {
                    "allow_partial_contact": self.var_pc.get() if hasattr(self, "var_pc") else None,
                    "mu": self.stability_params.mu_friction if self.stability_params else None,
                    "FS_sliding_min": self.stability_params.FS_sliding_min if self.stability_params else None,
                    "FS_overturning_min": self.stability_params.FS_overturning_min if self.stability_params else None,
                },
                "counts": {
                    "cases": len(self.load_set.cases) if self.load_set else 0,
                    "combinations": len(self.load_set.combinations) if self.load_set else 0,
                },
            },
            "outputs": self.summary,
        }

    def _persist_analysis_log(self) -> None:
        if self.summary is None:
            return
        os.makedirs(self.logs_dir, exist_ok=True)

        with open(self.latest_json_path, "w", encoding="utf-8") as f:
            json.dump(self.summary, f, ensure_ascii=False, indent=2)

        snapshot = self._build_log_snapshot()
        with open(self.history_jsonl_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(snapshot, ensure_ascii=False) + "\n")

    def _render_summary_json(self):
        self.txt_summary.config(state="normal")
        self.txt_summary.delete("1.0", "end")
        if self.summary is None:
            self.txt_summary.insert("end", "Ejecute el análisis para ver resultados.")
        else:
            self.txt_summary.insert("end", json.dumps(self.summary, indent=2, ensure_ascii=False))
        self.txt_summary.config(state="disabled")

    def _render_calc_trace(self):
        self.txt_calc_trace.config(state="normal")
        self.txt_calc_trace.delete("1.0", "end")

        if not self.design_result or not self.summary:
            self.txt_calc_trace.insert("end", "Ejecute el análisis para ver la traza detallada de cálculos.")
            self.txt_calc_trace.config(state="disabled")
            return

        dr = self.design_result
        pr = self.critical_ultimate_pressure
        qa = self.soil.qa if self.soil else 0.0
        sp = self.stability_params

        lines = [
            "=== TRAZA DETALLADA DE VERIFICACION ===",
            "",
            "1) DATOS GEOMETRICOS",
            f"   B = {self.geom.B:.3f} m, L = {self.geom.L:.3f} m, h = {self.geom.h:.3f} m",
            f"   Columna: bx = {self.geom.bx:.3f} m, by = {self.geom.by:.3f} m",
            "",
            "2) VERIFICACION GEOTECNICA (combinacion critica)",
        ]
        if pr:
            lines.extend([
                f"   Combinacion critica: {pr.combo_name}",
                f"   q_max = {pr.q_max:.2f} kPa",
                f"   q_min = {pr.q_min:.2f} kPa",
                f"   qa admisible = {qa:.2f} kPa",
                f"   Condicion: q_max <= qa => {pr.q_max:.2f} <= {qa:.2f} => {'CUMPLE' if pr.passes_qa else 'NO CUMPLE'}",
                f"   Excentricidades: ex = {pr.eccentricity_x:.4f} m, ey = {pr.eccentricity_y:.4f} m",
                f"   Contact ratio = {pr.contact_ratio:.3f}",
                "",
            ])
            if not self.var_pc.get() and not pr.full_contact:
                lines.extend([
                    "   Nota: el valor de q_max mostrado es el calculado para contacto parcial.",
                    "   Esta combinacion falla geotecnica porque 'Permitir contacto parcial' esta desactivado.",
                    "",
                ])

        lines.extend([
            "3) VERIFICACION ESTRUCTURAL",
            f"   Flexion X: Mu = {dr.Mu_x:.2f} kN.m/m, phiMn = {dr.phi_Mn_x:.2f} kN.m/m",
            f"   Condicion: phiMn >= Mu => {dr.phi_Mn_x:.2f} >= {dr.Mu_x:.2f} => {'CUMPLE' if dr.passes_flexure_x else 'NO CUMPLE'}",
            f"   Acero provisto X: {dr.bar_x} @ {dr.spacing_x:.1f} mm (As={dr.As_prov_x:.1f} mm2/m)",
            "",
            f"   Flexion Y: Mu = {dr.Mu_y:.2f} kN.m/m, phiMn = {dr.phi_Mn_y:.2f} kN.m/m",
            f"   Condicion: phiMn >= Mu => {dr.phi_Mn_y:.2f} >= {dr.Mu_y:.2f} => {'CUMPLE' if dr.passes_flexure_y else 'NO CUMPLE'}",
            f"   Acero provisto Y: {dr.bar_y} @ {dr.spacing_y:.1f} mm (As={dr.As_prov_y:.1f} mm2/m)",
            "",
            f"   Cortante 1-via X: Vu = {dr.Vu_x:.2f} kN/m, phiVc = {dr.phi_Vc_x:.2f} kN/m",
            f"   Condicion: phiVc >= Vu => {dr.phi_Vc_x:.2f} >= {dr.Vu_x:.2f} => {'CUMPLE' if dr.passes_shear_x else 'NO CUMPLE'}",
            "",
            f"   Cortante 1-via Y: Vu = {dr.Vu_y:.2f} kN/m, phiVc = {dr.phi_Vc_y:.2f} kN/m",
            f"   Condicion: phiVc >= Vu => {dr.phi_Vc_y:.2f} >= {dr.Vu_y:.2f} => {'CUMPLE' if dr.passes_shear_y else 'NO CUMPLE'}",
            "",
            f"   Punzonamiento: Vu = {dr.Vu2way:.2f} kN, phiVc = {dr.phi_Vc2way:.2f} kN",
            f"   Condicion: phiVc >= Vu => {dr.phi_Vc2way:.2f} >= {dr.Vu2way:.2f} => {'CUMPLE' if dr.passes_punching else 'NO CUMPLE'}",
            "",
            "4) ESTABILIDAD",
            f"   Parametros: mu={sp.mu_friction:.3f}, FS_desliz_min={sp.FS_sliding_min:.2f}, FS_volteo_min={sp.FS_overturning_min:.2f}",
        ])

        if self.stab_results:
            worst_sl = min(self.stab_results, key=lambda s: s.FS_sliding_x)
            worst_ot = min(self.stab_results, key=lambda s: s.FS_overturning_x)
            lines.extend([
                f"   Peor FS deslizamiento X: {worst_sl.FS_sliding_x:.2f} ({worst_sl.combo_name}) => {'CUMPLE' if worst_sl.FS_sliding_x >= sp.FS_sliding_min else 'NO CUMPLE'}",
                f"   Peor FS volteo X: {worst_ot.FS_overturning_x:.2f} ({worst_ot.combo_name}) => {'CUMPLE' if worst_ot.FS_overturning_x >= sp.FS_overturning_min else 'NO CUMPLE'}",
                "",
            ])

        lines.extend([
            "5) RESULTADO GLOBAL",
            f"   Estado de diseño: {'PASA' if dr.passes_all else 'FALLA'}",
        ])

        if self.anch_result:
            ar = self.anch_result
            lines.extend([
                "",
                "6) ANCLAJE Y TRANSFERENCIA DE MOMENTO",
                f"   ld requerido = {ar.ld_required:.1f} mm",
                f"   ld disponible = {ar.ld_available:.1f} mm",
                f"   Condicion: ld_disponible >= ld_requerido => {'CUMPLE' if ar.passes_development else 'NO CUMPLE'}",
                f"   Base empotrada posible: {'SI' if ar.can_be_fixed else 'NO'}",
            ])
            for w in ar.warnings:
                lines.append(f"   Advertencia: {w}")

        if self.base_rotation_result:
            br = self.base_rotation_result
            lines.extend([
                "",
                "7) RIGIDEZ ROTACIONAL DE LA BASE",
                f"   Curva generada con: {br.axis_label.lower()} | combo={br.combo_name}",
                f"   Clasificación automática: {br.classification.upper()}",
                f"   Momento de referencia usado = {br.reference_moment_used:.2f} kN.m",
                f"   Rotación en referencia = {br.reference_theta*1000.0:.3f} mrad",
                f"   Contacto en referencia = {br.reference_contact_ratio*100.0:.1f}%",
                f"   Levantamiento en referencia: {'NO' if br.no_uplift_at_reference else 'SI'}",
                f"   k_tangente,ini = {br.tangent_stiffness_initial:.2f} kN.m/rad",
                f"   k_tangente,ref = {br.tangent_stiffness_reference:.2f} kN.m/rad",
                f"   k_secante,ref = {br.secant_stiffness_reference:.2f} kN.m/rad",
                f"   k_lineal(eq) = {br.linear_equivalent_stiffness:.2f} kN.m/rad",
                f"   Bilineal: k1={br.bilinear_stiffness_1:.2f} kN.m/rad | k2={br.bilinear_stiffness_2:.2f} kN.m/rad",
                f"   Punto de quiebre: M={br.bilinear_moment_break:.2f} kN.m ; θ={br.bilinear_theta_break*1000.0:.3f} mrad",
                f"   Rigidez columna = {br.column_rotational_stiffness:.2f} kN.m/rad",
                f"   Relación k_base/k_col = {br.stiffness_ratio:.3f}",
            ])
            if br.uplift_theta is not None and br.uplift_moment is not None:
                lines.append(
                    f"   Inicio de levantamiento: M ≈ {br.uplift_moment:.2f} kN.m, θ ≈ {br.uplift_theta*1000.0:.3f} mrad"
                )

        self.txt_calc_trace.insert("end", "\n".join(lines))
        self.txt_calc_trace.config(state="disabled")

    def _render_equations(self):
        self.txt_equations.config(state="normal")
        self.txt_equations.delete("1.0", "end")

        if not self.summary or not self.design_result or not self.critical_ultimate_pressure:
            self.txt_equations.insert("end", "Ejecute el análisis para generar ecuaciones numeradas.")
            self.txt_equations.config(state="disabled")
            return

        combo = self.critical_ultimate_combo
        if combo is None:
            self.txt_equations.insert("end", "No se encontró combinación crítica para formular ecuaciones.")
            self.txt_equations.config(state="disabled")
            return

        N_total, Mx_total, My_total = compute_total_load(combo, self.geom, self.soil)
        B, L, h = self.geom.B, self.geom.L, self.geom.h
        A = B * L
        Ix = B * (L ** 3) / 12.0
        Iy = L * (B ** 3) / 12.0
        ex = My_total / N_total if N_total > 0 else 0.0
        ey = Mx_total / N_total if N_total > 0 else 0.0
        pr = self.critical_ultimate_pressure
        dr = self.design_result

        lines = [
            "=== ECUACIONES NUMERADAS (VERIFICACIÓN) ===",
            "",
            "[E1] Carga vertical total",
            "N_total = N + W_zapata + W_relleno",
            f"N_total = {combo.N:.2f} + ({A:.4f}*{h:.3f}*24.0) + ({A:.4f}*max(Df-h,0)*γ)",
            f"N_total = {N_total:.2f} kN",
            "",
            "[E2] Brazo de transferencia por cortante",
            "e = Df",
            f"e = {self.soil.Df:.3f} m",
            "",
            "[E3] Momentos totales en la base",
            "Mx_total = Mx + Vy*Df + N*ey_col",
            "My_total = My + Vx*Df + N*ex_col",
            f"Mx_total = {combo.Mx:.2f} + {combo.Vy:.2f}*{self.soil.Df:.3f} + {combo.N:.2f}*{self.geom.ey:.3f} = {Mx_total:.2f} kN.m",
            f"My_total = {combo.My:.2f} + {combo.Vx:.2f}*{self.soil.Df:.3f} + {combo.N:.2f}*{self.geom.ex:.3f} = {My_total:.2f} kN.m",
            "",
            "[E4] Excentricidades",
            "ex = My_total / N_total,   ey = Mx_total / N_total",
            f"ex = {My_total:.2f}/{N_total:.2f} = {ex:.4f} m",
            f"ey = {Mx_total:.2f}/{N_total:.2f} = {ey:.4f} m",
            "",
            "[E5] Presión media y distribución lineal (contacto completo teórico)",
            "q(x,y) = N/A + (My/Iy)*x + (Mx/Ix)*y",
            f"A={A:.4f} m2, Ix={Ix:.4f} m4, Iy={Iy:.4f} m4",
            "",
            "[E5a] Criterio de levantamiento (núcleo central)",
            "No hay levantamiento si: |ex| <= B/6 y |ey| <= L/6",
            f"|ex|={abs(ex):.4f} vs B/6={B/6.0:.4f} ; |ey|={abs(ey):.4f} vs L/6={L/6.0:.4f}",
            f"Resultado: {'NO HAY LEVANTAMIENTO (CONTACTO COMPLETO)' if pr.full_contact else 'HAY LEVANTAMIENTO (CONTACTO PARCIAL)'}",
            "",
            "[E6] Verificación geotécnica (resultado de análisis)",
            f"q_max = {pr.q_max:.2f} kPa, qa = {self.soil.qa:.2f} kPa",
            f"Condición: q_max <= qa => {'CUMPLE' if pr.passes_qa else 'NO CUMPLE'}",
            f"Área efectiva de contacto = {pr.effective_area:.3f} m2 ({pr.contact_ratio*100.0:.1f}% del área total)",
            "",
            "[E7] Flexión por metro",
            "Mu_x = q_u * cx_x^2 / 2,  Mu_y = q_u * cx_y^2 / 2",
            f"Mu_x = {dr.Mu_x:.2f} kN.m/m, phiMn_x = {dr.phi_Mn_x:.2f} kN.m/m => {'CUMPLE' if dr.passes_flexure_x else 'NO CUMPLE'}",
            f"Mu_y = {dr.Mu_y:.2f} kN.m/m, phiMn_y = {dr.phi_Mn_y:.2f} kN.m/m => {'CUMPLE' if dr.passes_flexure_y else 'NO CUMPLE'}",
            "",
            "[E8] Cortante unidireccional",
            "Vu = q_u * brazo_cortante,  condición: phiVc >= Vu",
            f"X: Vu={dr.Vu_x:.2f}, phiVc={dr.phi_Vc_x:.2f} => {'CUMPLE' if dr.passes_shear_x else 'NO CUMPLE'}",
            f"Y: Vu={dr.Vu_y:.2f}, phiVc={dr.phi_Vc_y:.2f} => {'CUMPLE' if dr.passes_shear_y else 'NO CUMPLE'}",
            "",
            "[E9] Punzonamiento",
            "Condición: phiVc_2way >= Vu_2way",
            f"Vu={dr.Vu2way:.2f}, phiVc={dr.phi_Vc2way:.2f} => {'CUMPLE' if dr.passes_punching else 'NO CUMPLE'}",
        ]

        self.txt_equations.insert("end", "\n".join(lines))
        self.txt_equations.config(state="disabled")

    def _render_base_rotation_summary(self):
        if self.base_rotation_result is None:
            self.lbl_base_rotation.config(text="Ejecute el análisis para generar la curva M-θ.")
            return

        br = self.base_rotation_result
        lines = [
            f"Clasificación: {br.classification.upper()} | {br.axis_label} | Combo: {br.combo_name}",
            f"Referencia: M={br.reference_moment_used:.1f} kN.m, θ={br.reference_theta*1000.0:.3f} mrad, contacto={br.reference_contact_ratio*100.0:.1f}%",
            f"Levantamiento en referencia: {'NO' if br.no_uplift_at_reference else 'SI'}",
            f"k_tan,ini = {br.tangent_stiffness_initial:.1f} | k_tan,ref = {br.tangent_stiffness_reference:.1f} | k_sec,ref = {br.secant_stiffness_reference:.1f} kN.m/rad",
            f"k_lineal(eq) = {br.linear_equivalent_stiffness:.1f} | bilineal: k1={br.bilinear_stiffness_1:.1f}, k2={br.bilinear_stiffness_2:.1f} kN.m/rad",
            f"k_col = {br.column_rotational_stiffness:.1f} kN.m/rad | k_base/k_col = {br.stiffness_ratio:.3f}",
            f"ks = {br.ks_used:.1f} kN/m3 ({br.ks_source}) | Longitud efectiva columna = {self.column_effective_length:.2f} m",
        ]
        if br.uplift_theta is not None and br.uplift_moment is not None:
            lines.append(f"Inicio de levantamiento: M ≈ {br.uplift_moment:.2f} kN.m, θ ≈ {br.uplift_theta*1000.0:.3f} mrad")
        if br.moment_capacity is not None:
            lines.append(f"Límite por transferencia de momento adoptado: φMn = {br.moment_capacity:.2f} kN.m")
        self.lbl_base_rotation.config(text="\n".join(lines))

    def _render_base_rotation_theory(self):
        self.txt_base_theory.config(state="normal")
        self.txt_base_theory.delete("1.0", "end")

        if self.base_rotation_result is None or self.soil is None or self.geom is None or self.mats is None:
            self.txt_base_theory.insert("end", "Ejecute el análisis para mostrar la base teórica del modelo M-θ.")
            self.txt_base_theory.config(state="disabled")
            return

        br = self.base_rotation_result
        ks_text = f"{br.ks_used:.2f} kN/m³ ({br.ks_source})"
        axis_text = "Y" if br.axis == "y" else "X"

        lines = [
            "=== BASE TEÓRICA DEL MODELO M-θ ===",
            "",
            "A) OBJETIVO DEL MODELO",
            "Determinar la relación momento-rotación en la base columna-zapata:",
            "  M = f(θ)",
            "incluyendo pérdida de contacto suelo-zapata y flexibilidad local del arranque.",
            "",
            "B) TIPO DE MODELO EMPLEADO",
            "[M1] Subrasante tipo Winkler (resortes distribuidos independientes).",
            "[M2] Contacto unilateral (solo compresión): el suelo no toma tracción.",
            "[M3] Rigidez equivalente evaluada directamente desde la respuesta de la base.",
            "[M4] (Opcional) límite de momento por transferencia de anclaje φMn.",
            f"[M5] Estado actual del tope φMn: {'ACTIVO' if self.apply_anchorage_cap_mtheta else 'INACTIVO'}.",
            "",
            "C) HIPÓTESIS PRINCIPALES",
            "[H1] Rotación cuasi-estática alrededor de un eje principal (X o Y).",
            "[H2] Campo de asentamientos lineal por cinemática rígida en la base.",
            "[H3] Material de suelo representado por módulo de subrasante ks constante por tramo.",
            "[H4] Sin interacción lateral del suelo en este submodelo (solo presión vertical).",
            "",
            "D) ECUACIONES DEL MODELO (NUMERADAS)",
            "[T1] Campo de desplazamientos verticales (franja 1D equivalente):",
            "      w(x) = w0 + θ_suelo * x",
            "",
            "[T2] Ley constitutiva de subrasante con contacto unilateral:",
            "      q(x) = ks * max(w(x), 0)",
            "",
            "[T3] Equilibrio vertical para resolver w0:",
            "      N_total = ∫ q(x) dA",
            "",
            "[T4] Momento resistente del suelo respecto al eje analizado:",
            "      M_suelo = ∫ q(x) * x dA",
            "",
            "[T5] Aporte adicional de rotación en la interfaz:",
            "      θ_junta = 0",
            "",
            "[T6] Rotación total de base:",
            "      θ_total = θ_suelo + θ_junta",
            "",
            "[T7] Rigidez rotacional de columna para comparación:",
            "      k_col = 4*E*I/L_eff",
            "",
            "[T8] Rigidez tangente local de la curva:",
            "      k_tan = dM/dθ   (aprox. por diferencias finitas)",
            "",
            "[T9] Rigidez secante en punto de referencia:",
            "      k_sec,ref = M_ref / θ_ref",
            "",
            "[T10] Modelo lineal equivalente:",
            "       M_lin(θ) = k_lin * θ, con k_lin = k_sec,ref",
            "",
            "[T11] Modelo bilineal equivalente:",
            "       Tramo 1: M = k1*θ                     (0 <= θ <= θ_break)",
            "       Tramo 2: M = M_break + k2*(θ-θ_break) (θ > θ_break)",
            "",
            "[T12] Clasificación de la unión base según rigidez relativa:",
            "       r = k_base / k_col",
            "       r <= 0.5  -> articulada",
            "       0.5 < r < 8 -> semirrígida",
            "       r >= 8    -> rígida",
            "",
            "E) PARÁMETROS Y VALORES USADOS EN ESTA CORRIDA",
            f"[P1] Eje analizado = {axis_text}",
            f"[P2] ks usado = {ks_text}",
            f"[P3] Longitud efectiva de columna L_eff = {self.column_effective_length:.3f} m",
            f"[P4] θ_max barrido = {self.base_theta_max*1000.0:.3f} mrad",
            f"[P5] k_tan,ini = {br.tangent_stiffness_initial:.3f} kN.m/rad",
            f"[P6] k_tan,ref = {br.tangent_stiffness_reference:.3f} kN.m/rad",
            f"[P7] k_sec,ref = {br.secant_stiffness_reference:.3f} kN.m/rad",
            f"[P8] k_lineal(eq) = {br.linear_equivalent_stiffness:.3f} kN.m/rad",
            f"[P9] k_bilineal_1 = {br.bilinear_stiffness_1:.3f} kN.m/rad",
            f"[P10] k_bilineal_2 = {br.bilinear_stiffness_2:.3f} kN.m/rad",
            f"[P11] Punto de quiebre bilineal: M_break = {br.bilinear_moment_break:.3f} kN.m, θ_break = {br.bilinear_theta_break*1000.0:.3f} mrad",
            f"[P12] k_col = {br.column_rotational_stiffness:.3f} kN.m/rad",
            f"[P13] Relación r = k_base/k_col = {br.stiffness_ratio:.4f}",
            f"[P14] Clasificación automática = {br.classification.upper()}",
        ]

        if br.uplift_theta is not None and br.uplift_moment is not None:
            lines.extend([
                "",
                "F) EVENTO DE LEVANTAMIENTO",
                f"[L1] Inicio estimado: M ≈ {br.uplift_moment:.3f} kN.m, θ ≈ {br.uplift_theta*1000.0:.3f} mrad",
                "[L2] Interpretación: a partir de ese punto se reduce el área efectiva de contacto.",
            ])

        if br.moment_capacity is not None:
            lines.extend([
                "",
                "G) LÍMITE POR TRANSFERENCIA DE MOMENTO",
                f"[A1] Valor disponible φMn = {br.moment_capacity:.3f} kN.m",
                f"[A2] Tope en curva: {'APLICADO' if self.apply_anchorage_cap_mtheta else 'NO APLICADO'}.",
                "[A3] Si se aplica, puede controlar el tramo final de la curva M-θ.",
            ])

        lines.extend([
            "",
            "H) ALCANCE DEL ENFOQUE",
            "[S1] Es un modelo ingenieril eficiente para diseño preliminar y evaluación de rigidez de base.",
            "[S2] No reemplaza un FEM no lineal completo con contacto 3D, plasticidad avanzada o acoplamientos complejos.",
        ])

        self.txt_base_theory.insert("end", "\n".join(lines))
        self.txt_base_theory.config(state="disabled")

    def _draw_results_visualization(self):
        self._clear_plot_frame(self.frame_results_plot)
        if not self.press_results or not self.soil:
            lbl = tk.Label(self.frame_results_plot, text="Ejecute el análisis para mostrar visualizaciones.")
            lbl.pack(expand=True)
            return

        fig = Figure(figsize=(6.4, 5.2), dpi=80)

        # qmax vs qa
        ax1 = fig.add_subplot(221)
        qvals = [pr.q_max for pr in self.press_results[:12]]
        names = [pr.combo_name[:8] for pr in self.press_results[:12]]
        ax1.bar(range(len(qvals)), qvals, color=["#2ca02c" if q <= self.soil.qa else "#d62728" for q in qvals])
        ax1.axhline(self.soil.qa, color="#1f77b4", linestyle="--", linewidth=1.8)
        ax1.set_xticks(range(len(names)))
        ax1.set_xticklabels(names, rotation=60, ha="right", fontsize=7)
        ax1.set_title("qmax por combinación")
        ax1.set_ylabel("kPa")

        # FS sliding
        ax2 = fig.add_subplot(222)
        if self.stab_results:
            fs_vals = [sr.FS_sliding_x for sr in self.stab_results]
            fs_names = [sr.combo_name[:8] for sr in self.stab_results]
            min_fs = self.stability_params.FS_sliding_min
            ax2.bar(range(len(fs_vals)), fs_vals, color=["#2ca02c" if v >= min_fs else "#ff7f0e" for v in fs_vals])
            ax2.axhline(min_fs, color="#1f77b4", linestyle="--", linewidth=1.8)
            ax2.set_xticks(range(len(fs_names)))
            ax2.set_xticklabels(fs_names, rotation=60, ha="right", fontsize=7)
            ax2.set_title(f"FS deslizamiento X ({self.stability_source_label})")
        else:
            ax2.text(0.5, 0.5, "No hay resultados de estabilidad.", ha="center", va="center", transform=ax2.transAxes)
            ax2.set_title("Estabilidad")
            ax2.set_xticks([])
            ax2.set_yticks([])

        # Interaction Mu vs phiMn
        ax3 = fig.add_subplot(223)
        dr = self.design_result
        if dr is not None:
            labels = ["X", "Y"]
            Mu = [dr.Mu_x, dr.Mu_y]
            Mn = [dr.phi_Mn_x, dr.phi_Mn_y]
            x = np.arange(2)
            width = 0.35
            ax3.bar(x - width/2, Mu, width, label="Mu", color="#9467bd")
            ax3.bar(x + width/2, Mn, width, label="phiMn", color="#17becf")
            ax3.set_xticks(x)
            ax3.set_xticklabels(labels)
            ax3.set_title("Flexión: demanda vs capacidad")
            ax3.set_ylabel("kN.m/m")
            ax3.legend(fontsize=8)
        else:
            ax3.text(0.5, 0.5, "No hay diseño estructural\npara mostrar flexión.", ha="center", va="center", transform=ax3.transAxes)
            ax3.set_title("Flexión")
            ax3.set_xticks([])
            ax3.set_yticks([])

        # Cortante/punzonamiento
        ax4 = fig.add_subplot(224)
        if dr is not None:
            dem = [dr.Vu_x, dr.Vu_y, dr.Vu2way]
            cap = [dr.phi_Vc_x, dr.phi_Vc_y, dr.phi_Vc2way]
            labs = ["Vx", "Vy", "Punch"]
            x2 = np.arange(3)
            ax4.plot(x2, dem, "o-", label="Demanda", color="#d62728")
            ax4.plot(x2, cap, "s-", label="Capacidad", color="#2ca02c")
            ax4.set_xticks(x2)
            ax4.set_xticklabels(labs)
            ax4.set_title("Cortante y punzonamiento")
            ax4.legend(fontsize=8)
        else:
            ax4.text(0.5, 0.5, "No hay diseño estructural\npara mostrar cortante.", ha="center", va="center", transform=ax4.transAxes)
            ax4.set_title("Cortante")
            ax4.set_xticks([])
            ax4.set_yticks([])

        fig.tight_layout()
        self.canvas_results = FigureCanvasTkAgg(fig, master=self.frame_results_plot)
        self.canvas_results.draw()
        self.canvas_results.get_tk_widget().pack(fill="both", expand=True)

    def _draw_pressure_distribution(self):
        self._clear_plot_frame(self.frame_pressure_map)

        if not self.critical_ultimate_combo or not self.soil or not self.geom:
            lbl = tk.Label(self.frame_pressure_map, text="Ejecute análisis para ver distribución de presión.")
            lbl.pack(expand=True)
            return

        combo = self.critical_ultimate_combo
        N_total, Mx_total, My_total = compute_total_load(combo, self.geom, self.soil)

        B, L = self.geom.B, self.geom.L
        A = B * L
        Ix = B * (L ** 3) / 12.0
        Iy = L * (B ** 3) / 12.0

        nx = ny = 80
        xs = np.linspace(-B / 2.0, B / 2.0, nx)
        ys = np.linspace(-L / 2.0, L / 2.0, ny)
        X, Y = np.meshgrid(xs, ys)

        q_lin = (N_total / A) + (My_total / Iy) * X + (Mx_total / Ix) * Y
        q = np.maximum(q_lin, 0.0)
        no_contact_mask = q_lin <= 0.0
        has_uplift = bool(np.any(no_contact_mask))
        contact_ratio_map = float(np.mean(q_lin > 0.0))

        fig = Figure(figsize=(6.2, 5.2), dpi=80)
        ax = fig.add_subplot(111)
        cf = ax.contourf(X, Y, q, levels=20, cmap="RdYlGn_r")
        cbar = fig.colorbar(cf, ax=ax)
        cbar.set_label("q [kPa]")

        # Highlight area with no compression (uplift / no contact)
        if has_uplift:
            ax.contourf(
                X,
                Y,
                no_contact_mask.astype(float),
                levels=[0.5, 1.5],
                colors=["#666666"],
                alpha=0.28,
            )
            if float(np.min(q_lin)) < 0.0 < float(np.max(q_lin)):
                ax.contour(X, Y, q_lin, levels=[0.0], colors=["black"], linewidths=1.3, linestyles="--")

        # Contorno de zapata
        ax.plot([-B/2, B/2, B/2, -B/2, -B/2], [-L/2, -L/2, L/2, L/2, -L/2], "k-", linewidth=1.5)
        # Columna
        bx, by = self.geom.bx, self.geom.by
        ax.plot([-bx/2, bx/2, bx/2, -bx/2, -bx/2], [-by/2, -by/2, by/2, by/2, -by/2], "b-", linewidth=1.2)

        ax.set_title("Distribución de presión en planta q(x,y)")
        ax.set_xlabel("X [m]")
        ax.set_ylabel("Y [m]")
        ax.set_aspect("equal")
        ax.grid(alpha=0.25)

        qmax = float(np.max(q))
        qmin = float(np.min(q))
        qlin_min = float(np.min(q_lin))
        ax.text(
            0.02,
            0.02,
            (
                f"qmax mapa={qmax:.2f} kPa\n"
                f"qmin mapa (compresión)={qmin:.2f} kPa\n"
                f"qmin lineal={qlin_min:.2f} kPa\n"
                f"Levantamiento: {'SI' if has_uplift else 'NO'}\n"
                f"Contacto (mapa): {contact_ratio_map*100.0:.1f}%"
            ),
            transform=ax.transAxes,
            fontsize=8,
            bbox=dict(boxstyle="round", facecolor="white", alpha=0.8),
        )

        self.canvas_pressure_map = FigureCanvasTkAgg(fig, master=self.frame_pressure_map)
        self.canvas_pressure_map.draw()
        self.canvas_pressure_map.get_tk_widget().pack(fill="both", expand=True)

    def _draw_base_rotation_curve(self):
        self._clear_plot_frame(self.frame_base_rotation_plot)

        if self.base_rotation_result is None:
            lbl = tk.Label(self.frame_base_rotation_plot, text="Ejecute análisis para ver la curva M-θ de la base.")
            lbl.pack(expand=True)
            return

        br = self.base_rotation_result
        theta_total = [pt.theta_total * 1000.0 for pt in br.points]
        theta_soil = [pt.theta_soil * 1000.0 for pt in br.points]
        moments = [pt.moment for pt in br.points]
        contact_ratios = [pt.contact_ratio * 100.0 for pt in br.points]

        fig = Figure(figsize=(6.2, 5.2), dpi=80)
        ax1 = fig.add_subplot(211)
        ax1.plot(theta_total, moments, color="#1f77b4", linewidth=2.0, label="M-θ total")
        ax1.plot(theta_soil, moments, color="#ff7f0e", linestyle="--", linewidth=1.3, label="M-θ suelo")

        # Idealización lineal equivalente (secante de referencia)
        if br.linear_equivalent_stiffness > 0.0:
            t_max = max(theta_total) / 1000.0 if theta_total else 0.0
            theta_line = np.linspace(0.0, t_max, 40)
            m_line = br.linear_equivalent_stiffness * theta_line
            ax1.plot(theta_line * 1000.0, m_line, color="#2ca02c", linestyle="-.", linewidth=1.2, label="Lineal eq")

        # Idealización bilineal
        if br.bilinear_stiffness_1 > 0.0:
            t_break = max(br.bilinear_theta_break, 0.0)
            m_break = max(br.bilinear_moment_break, 0.0)
            t_end = max(theta_total) / 1000.0 if theta_total else t_break
            t1 = np.linspace(0.0, t_break, 20) if t_break > 1e-9 else np.array([0.0, 0.0])
            m1 = br.bilinear_stiffness_1 * t1
            t2 = np.linspace(t_break, t_end, 20) if t_end > t_break else np.array([t_break, t_break])
            m2 = m_break + br.bilinear_stiffness_2 * (t2 - t_break)
            ax1.plot(t1 * 1000.0, m1, color="#9467bd", linestyle=":", linewidth=1.4)
            ax1.plot(t2 * 1000.0, m2, color="#9467bd", linestyle=":", linewidth=1.4, label="Bilineal")
            ax1.scatter([t_break * 1000.0], [m_break], color="#9467bd", s=20, zorder=6)

        if br.uplift_theta is not None and br.uplift_moment is not None:
            ax1.axvline(br.uplift_theta * 1000.0, color="#d62728", linestyle=":", linewidth=1.4)
            ax1.scatter([br.uplift_theta * 1000.0], [br.uplift_moment], color="#d62728", zorder=5)
        if br.M_reference > 0.0:
            ax1.axhline(br.M_reference, color="#2ca02c", linestyle="--", linewidth=1.2, label="M referencia")
        if br.moment_capacity is not None:
            ax1.axhline(br.moment_capacity, color="#9467bd", linestyle="-.", linewidth=1.2, label="φMn transferencia")
        ax1.set_title(f"Curva Momento-Rotación de la base ({br.classification})")
        ax1.set_xlabel("θ [mrad]")
        ax1.set_ylabel("M [kN.m]")
        ax1.grid(alpha=0.25)
        ax1.legend(fontsize=8)

        ax2 = fig.add_subplot(212)
        ax2.plot(theta_total, contact_ratios, color="#2ca02c", linewidth=2.0)
        ax2.axhline(80.0, color="#ff7f0e", linestyle="--", linewidth=1.1)
        ax2.set_xlabel("θ [mrad]")
        ax2.set_ylabel("Contacto [%]")
        ax2.set_title("Evolución del área en contacto")
        ax2.grid(alpha=0.25)

        fig.tight_layout()
        self.canvas_base_rotation = FigureCanvasTkAgg(fig, master=self.frame_base_rotation_plot)
        self.canvas_base_rotation.draw()
        self.canvas_base_rotation.get_tk_widget().pack(fill="both", expand=True)

    def _export(self, fmt: str):
        if self.summary is None:
            messagebox.showwarning("Advertencia", "Ejecute el análisis primero.")
            return
        ext_map = {"xlsx": ("Excel", "*.xlsx"),
                   "pdf":  ("PDF",   "*.pdf"),
                   "docx": ("Word",  "*.docx")}
        desc, pat = ext_map[fmt]
        path = filedialog.asksaveasfilename(
            defaultextension=f".{fmt}",
            filetypes=[(desc, pat), ("Todos", "*.*")],
            initialfile=f"reporte_zapata.{fmt}",
        )
        if not path:
            return
        try:
            detailed_trace = self._build_export_trace()
            if fmt == "xlsx":
                from core.report import export_to_excel
                export_to_excel(self.summary, path, detailed_trace=detailed_trace)
            elif fmt == "pdf":
                from core.report import export_to_pdf
                export_to_pdf(self.summary, path, detailed_trace=detailed_trace)
            elif fmt == "docx":
                from core.report import export_to_docx
                export_to_docx(self.summary, path, detailed_trace=detailed_trace)
            messagebox.showinfo("Éxito", f"Guardado en:\n{path}")
        except Exception as ex:
            messagebox.showerror("Error", str(ex))

    def _build_export_trace(self) -> list[str]:
        if not self.design_result or not self.soil:
            return []
        dr = self.design_result
        lines = [
            "TRAZABILIDAD DE CALCULOS",
            f"q_max critico = {self.critical_ultimate_pressure.q_max:.2f} kPa" if self.critical_ultimate_pressure else "q_max critico = N/A",
            f"qa admisible = {self.soil.qa:.2f} kPa",
            f"Flexion X: Mu={dr.Mu_x:.2f} | phiMn={dr.phi_Mn_x:.2f} | {'CUMPLE' if dr.passes_flexure_x else 'NO CUMPLE'}",
            f"Flexion Y: Mu={dr.Mu_y:.2f} | phiMn={dr.phi_Mn_y:.2f} | {'CUMPLE' if dr.passes_flexure_y else 'NO CUMPLE'}",
            f"Cortante X: Vu={dr.Vu_x:.2f} | phiVc={dr.phi_Vc_x:.2f} | {'CUMPLE' if dr.passes_shear_x else 'NO CUMPLE'}",
            f"Cortante Y: Vu={dr.Vu_y:.2f} | phiVc={dr.phi_Vc_y:.2f} | {'CUMPLE' if dr.passes_shear_y else 'NO CUMPLE'}",
            f"Punzonamiento: Vu={dr.Vu2way:.2f} | phiVc={dr.phi_Vc2way:.2f} | {'CUMPLE' if dr.passes_punching else 'NO CUMPLE'}",
            f"Resultado global: {'PASA' if dr.passes_all else 'FALLA'}",
        ]
        if self.anch_result:
            lines.append(
                f"Anclaje: ld_req={self.anch_result.ld_required:.1f} | ld_avail={self.anch_result.ld_available:.1f} | {'CUMPLE' if self.anch_result.passes_development else 'NO CUMPLE'}"
            )
        return lines

    def _clear_plot_frame(self, frame: ttk.LabelFrame) -> None:
        for child in frame.winfo_children():
            child.destroy()

    # =========================================================
    # UTILIDADES
    # =========================================================
    def _lentry(self, parent, label: str, row: int, default: str = "") -> ttk.Entry:
        """Etiqueta + campo de texto usando grid."""
        tk.Label(parent, text=label, font=("Arial", 9)).grid(
            row=row, column=0, sticky="e", padx=5, pady=3)
        e = ttk.Entry(parent, width=12)
        e.insert(0, default)
        e.grid(row=row, column=1, sticky="w", padx=5, pady=3)
        return e

    def _set_entry_value(self, entry: ttk.Entry, value: str) -> None:
        entry.delete(0, tk.END)
        entry.insert(0, value)

    def _lentry_h(self, parent, label: str, default: str = "") -> ttk.Entry:
        """Etiqueta + campo de texto usando pack horizontal."""
        tk.Label(parent, text=label, font=("Arial", 9)).pack(side="left", padx=(10, 2))
        e = ttk.Entry(parent, width=8, font=("Arial", 9))
        e.insert(0, default)
        e.pack(side="left", padx=(0, 8))
        return e

    def _treeview(self, parent, columns: tuple) -> ttk.Treeview:
        tree = ttk.Treeview(parent, columns=columns, show="headings", height=6)
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=max(60, len(col) * 7), anchor="center")
        sby = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sby.set)
        sby.pack(side="right", fill="y")
        tree.pack(fill="both", expand=True)
        return tree

    def _scrolled_text(self, parent) -> tk.Text:
        txt = tk.Text(parent, font=("Courier", 9), state="disabled", wrap="none")
        sby = ttk.Scrollbar(parent, orient="vertical", command=txt.yview)
        txt.configure(yscrollcommand=sby.set)
        sby.pack(side="right", fill="y")
        txt.pack(fill="both", expand=True, padx=5, pady=5)
        return txt

    def _refresh_cases(self):
        self.tree_cases.delete(*self.tree_cases.get_children())
        for c in self.load_set.cases:
            self.tree_cases.insert("", "end", values=(
                c.name, c.load_type,
                f"{c.N:.1f}", f"{c.Vx:.1f}", f"{c.Vy:.1f}",
                f"{c.Mx:.1f}", f"{c.My:.1f}",
            ))

    def _refresh_combos(self):
        self.tree_combos.delete(*self.tree_combos.get_children())
        for c in self.load_set.combinations:
            self.tree_combos.insert("", "end", values=(
                c.name, c.combo_type,
                f"{c.N:.1f}", f"{c.Vx:.1f}", f"{c.Vy:.1f}",
                f"{c.Mx:.1f}", f"{c.My:.1f}",
            ))


if __name__ == "__main__":
    app = ZapataApp()
    app.mainloop()
