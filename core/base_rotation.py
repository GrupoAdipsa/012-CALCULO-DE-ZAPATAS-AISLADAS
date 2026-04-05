from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import math
import numpy as np

from core.anchorage import AnchorageResult
from core.loads import LoadCombination
from core.rc_design import MaterialProperties
from core.soil_pressure import FootingGeometry, SoilProperties, compute_total_load


@dataclass
class BaseRotationPoint:
    theta_soil: float
    theta_total: float
    moment: float
    contact_ratio: float
    q_max: float
    q_min_linear: float


@dataclass
class BaseRotationResult:
    combo_name: str
    axis: str
    axis_label: str
    points: List[BaseRotationPoint] = field(default_factory=list)
    N_total: float = 0.0
    M_reference: float = 0.0
    ks_used: float = 0.0
    ks_source: str = ""
    joint_rotational_stiffness: float = 0.0
    rigid_connection_assumed: bool = True
    column_rotational_stiffness: float = 0.0
    initial_rotational_stiffness: float = 0.0
    tangent_stiffness_initial: float = 0.0
    tangent_stiffness_reference: float = 0.0
    secant_stiffness_reference: float = 0.0
    linear_equivalent_stiffness: float = 0.0
    bilinear_stiffness_1: float = 0.0
    bilinear_stiffness_2: float = 0.0
    bilinear_theta_break: float = 0.0
    bilinear_moment_break: float = 0.0
    stiffness_ratio: float = 0.0
    classification: str = "semirrígida"
    reference_moment_used: float = 0.0
    reference_theta: float = 0.0
    reference_contact_ratio: float = 1.0
    no_uplift_at_reference: bool = True
    uplift_theta: Optional[float] = None
    uplift_moment: Optional[float] = None
    moment_capacity: Optional[float] = None
    notes: List[str] = field(default_factory=list)


def _estimate_subgrade_modulus(
    soil: SoilProperties,
    settlement_reference: float = 0.025,
) -> Tuple[float, str]:
    if soil.ks is not None and soil.ks > 0.0:
        return soil.ks, "definido por usuario"

    settlement_reference = max(settlement_reference, 0.005)
    ks = soil.qa / settlement_reference
    return ks, f"estimado como qa/{settlement_reference:.3f} m"


def _axis_properties(geom: FootingGeometry, axis: str) -> Tuple[np.ndarray, float, float]:
    if axis == "y":
        coords = np.linspace(-geom.B / 2.0, geom.B / 2.0, 121)
        tributary_length = geom.L
        dimension = geom.B
    else:
        coords = np.linspace(-geom.L / 2.0, geom.L / 2.0, 121)
        tributary_length = geom.B
        dimension = geom.L
    return coords, tributary_length, dimension


def _solve_vertical_translation(
    N_total: float,
    coords: np.ndarray,
    theta_soil: float,
    ks: float,
    strip_width: float,
    tributary_length: float,
) -> np.ndarray:
    def total_force(w0: float) -> float:
        settlement = np.maximum(w0 + theta_soil * coords, 0.0)
        q = ks * settlement
        return float(np.sum(q * strip_width * tributary_length))

    low = -2.0
    high = 2.0
    for _ in range(60):
        if total_force(high) >= N_total:
            break
        high *= 2.0

    for _ in range(100):
        mid = 0.5 * (low + high)
        f_mid = total_force(mid)
        if abs(f_mid - N_total) <= max(1e-4 * max(N_total, 1.0), 1e-6):
            break
        if f_mid < N_total:
            low = mid
        else:
            high = mid

    return mid + theta_soil * coords


def _compute_soil_response(
    N_total: float,
    geom: FootingGeometry,
    ks: float,
    axis: str,
    theta_soil: float,
) -> Tuple[float, float, float, float]:
    coords, tributary_length, _ = _axis_properties(geom, axis)
    strip_width = abs(coords[1] - coords[0]) if len(coords) > 1 else 0.0
    settlement_raw = _solve_vertical_translation(N_total, coords, theta_soil, ks, strip_width, tributary_length)
    settlement = np.maximum(settlement_raw, 0.0)
    q = ks * settlement
    force = q * strip_width * tributary_length
    moment = float(np.sum(force * coords))
    contact_ratio = float(np.mean(q > 1e-9))
    q_max = float(np.max(q))
    q_min_linear = float(np.min(ks * settlement_raw))
    return abs(moment), contact_ratio, q_max, q_min_linear


def _joint_rotational_stiffness(
    geom: FootingGeometry,
    materials: MaterialProperties,
    axis: str,
) -> float:
    Ec = 4700.0 * math.sqrt(materials.fc) * 1000.0
    if axis == "y":
        I = geom.by * geom.bx ** 3 / 12.0
    else:
        I = geom.bx * geom.by ** 3 / 12.0
    I_eff = 0.35 * I
    length = max(geom.h, 0.05)
    return Ec * I_eff / length


def _column_rotational_stiffness(
    geom: FootingGeometry,
    materials: MaterialProperties,
    axis: str,
    column_effective_length: float,
) -> float:
    Ec = 4700.0 * math.sqrt(materials.fc) * 1000.0
    if axis == "y":
        I = geom.by * geom.bx ** 3 / 12.0
    else:
        I = geom.bx * geom.by ** 3 / 12.0
    length = max(column_effective_length, 0.10)
    return 4.0 * Ec * I / length


def _classify_base(stiffness_ratio: float) -> str:
    if stiffness_ratio <= 0.5:
        return "articulada"
    if stiffness_ratio >= 8.0:
        return "rígida"
    return "semirrígida"


def _local_tangent(theta: np.ndarray, moment: np.ndarray, idx: int) -> float:
    if len(theta) < 2:
        return 0.0

    idx = max(0, min(idx, len(theta) - 1))
    if idx == 0:
        d_theta = theta[1] - theta[0]
        return (moment[1] - moment[0]) / d_theta if d_theta > 0.0 else 0.0
    if idx == len(theta) - 1:
        d_theta = theta[-1] - theta[-2]
        return (moment[-1] - moment[-2]) / d_theta if d_theta > 0.0 else 0.0

    d_theta = theta[idx + 1] - theta[idx - 1]
    return (moment[idx + 1] - moment[idx - 1]) / d_theta if d_theta > 0.0 else 0.0


def _extract_linear_bilinear_stiffness(
    points: List[BaseRotationPoint],
    reference_moment: float,
    uplift_theta: Optional[float],
) -> dict:
    if len(points) < 2:
        return {
            "k_tangent_initial": 0.0,
            "k_tangent_reference": 0.0,
            "k_secant_reference": 0.0,
            "k_linear": 0.0,
            "k1": 0.0,
            "k2": 0.0,
            "theta_break": 0.0,
            "moment_break": 0.0,
            "idx_ref": 0,
            "idx_break": 0,
        }

    theta = np.array([p.theta_total for p in points], dtype=float)
    moment = np.array([p.moment for p in points], dtype=float)

    k_tangent_initial = _local_tangent(theta, moment, 0)

    m_max = float(np.max(moment)) if len(moment) else 0.0
    if reference_moment > 0.0:
        m_target = min(reference_moment, m_max)
    else:
        m_target = 0.6 * m_max

    idx_ref = int(np.argmin(np.abs(moment - m_target))) if len(moment) else 0
    theta_ref = theta[idx_ref] if idx_ref < len(theta) else 0.0
    m_ref = moment[idx_ref] if idx_ref < len(moment) else 0.0

    k_tangent_reference = _local_tangent(theta, moment, idx_ref)
    k_secant_reference = (m_ref / theta_ref) if theta_ref > 0.0 else 0.0
    k_linear = k_secant_reference if k_secant_reference > 0.0 else k_tangent_initial

    idx_break = 0
    if uplift_theta is not None:
        idx_break = int(np.argmin(np.abs(theta - uplift_theta)))
    else:
        m_break_target = 0.6 * m_max
        idx_break = int(np.argmin(np.abs(moment - m_break_target))) if len(moment) else 0

    idx_break = max(1, min(idx_break, len(theta) - 2))
    theta_break = theta[idx_break]
    moment_break = moment[idx_break]
    k1 = k_tangent_initial

    d_theta_2 = theta[-1] - theta_break
    k2 = (moment[-1] - moment_break) / d_theta_2 if d_theta_2 > 0.0 else 0.0
    if k2 < 0.0:
        k2 = 0.0

    return {
        "k_tangent_initial": float(k_tangent_initial),
        "k_tangent_reference": float(k_tangent_reference),
        "k_secant_reference": float(k_secant_reference),
        "k_linear": float(k_linear),
        "k1": float(k1),
        "k2": float(k2),
        "theta_break": float(theta_break),
        "moment_break": float(moment_break),
        "idx_ref": idx_ref,
        "idx_break": idx_break,
        "m_ref": float(m_ref),
        "theta_ref": float(theta_ref),
    }


def generate_base_moment_rotation_curve(
    combo: LoadCombination,
    geom: FootingGeometry,
    soil: SoilProperties,
    materials: MaterialProperties,
    anchorage_result: Optional[AnchorageResult] = None,
    column_effective_length: float = 3.0,
    theta_max: float = 0.02,
    n_points: int = 40,
    settlement_reference: float = 0.025,
    axis: Optional[str] = None,
    apply_anchorage_cap: bool = False,
    assume_rigid_connection: bool = True,
) -> BaseRotationResult:
    N_total, Mx_total, My_total = compute_total_load(combo, geom, soil, materials.gamma_concrete)

    if axis is None:
        axis = "y" if abs(My_total) >= abs(Mx_total) else "x"

    axis_label = "Rotación alrededor del eje Y" if axis == "y" else "Rotación alrededor del eje X"
    M_reference = abs(My_total) if axis == "y" else abs(Mx_total)

    ks_used, ks_source = _estimate_subgrade_modulus(soil, settlement_reference)
    joint_k = _joint_rotational_stiffness(geom, materials, axis)
    column_k = _column_rotational_stiffness(geom, materials, axis, column_effective_length)
    moment_capacity = anchorage_result.phi_Mn_transfer if anchorage_result is not None else None

    theta_soil_values = np.linspace(0.0, max(theta_max, 1e-4), max(n_points, 10))
    points: List[BaseRotationPoint] = []
    uplift_theta = None
    uplift_moment = None

    for theta_soil in theta_soil_values:
        moment_soil, contact_ratio, q_max, q_min_linear = _compute_soil_response(
            N_total=N_total,
            geom=geom,
            ks=ks_used,
            axis=axis,
            theta_soil=float(theta_soil),
        )
        if apply_anchorage_cap and moment_capacity is not None:
            moment = min(moment_soil, moment_capacity)
        else:
            moment = moment_soil
        if assume_rigid_connection:
            theta_joint = 0.0
        else:
            theta_joint = moment / joint_k if joint_k > 0.0 else 0.0
        theta_total = float(theta_soil) + theta_joint
        points.append(
            BaseRotationPoint(
                theta_soil=float(theta_soil),
                theta_total=theta_total,
                moment=moment,
                contact_ratio=contact_ratio,
                q_max=q_max,
                q_min_linear=q_min_linear,
            )
        )
        if uplift_theta is None and contact_ratio < 0.999:
            uplift_theta = theta_total
            uplift_moment = moment

    stiff = _extract_linear_bilinear_stiffness(
        points=points,
        reference_moment=M_reference,
        uplift_theta=uplift_theta,
    )

    initial_rotational_stiffness = stiff["k_tangent_initial"]
    stiffness_ratio = stiff["k_linear"] / column_k if column_k > 0.0 else 0.0
    classification = _classify_base(stiffness_ratio)
    idx_ref = int(stiff["idx_ref"]) if points else 0
    idx_ref = max(0, min(idx_ref, len(points) - 1)) if points else 0
    ref_point = points[idx_ref] if points else None
    reference_contact_ratio = ref_point.contact_ratio if ref_point is not None else 1.0
    no_uplift_at_reference = reference_contact_ratio >= 0.999

    notes = [
        f"ks usado = {ks_used:.1f} kN/m3 ({ks_source})",
        (
            "Conexión base-columna asumida RÍGIDA (theta_junta=0)"
            if assume_rigid_connection
            else f"Conexión base-columna flexible con k_junta={joint_k:.1f} kN.m/rad"
        ),
        f"k_tan,ini = {stiff['k_tangent_initial']:.1f} kN.m/rad",
        f"k_tan,ref = {stiff['k_tangent_reference']:.1f} kN.m/rad",
        f"k_sec,ref = {stiff['k_secant_reference']:.1f} kN.m/rad",
        f"k_lineal(eq) = {stiff['k_linear']:.1f} kN.m/rad",
        f"k_bilineal_1 = {stiff['k1']:.1f} kN.m/rad",
        f"k_bilineal_2 = {stiff['k2']:.1f} kN.m/rad",
        f"Rigidez rotacional columna = {column_k:.1f} kN.m/rad",
        f"Relación k_base/k_col = {stiffness_ratio:.3f}",
    ]
    if uplift_theta is not None and uplift_moment is not None:
        notes.append(f"Inicio de levantamiento cerca de M={uplift_moment:.2f} kN.m y θ={uplift_theta*1000.0:.3f} mrad")
    if moment_capacity is not None:
        if apply_anchorage_cap:
            notes.append(f"Capacidad de transferencia ACTIVA: φMn={moment_capacity:.2f} kN.m")
        else:
            notes.append(f"Capacidad de transferencia disponible (no activa en curva): φMn={moment_capacity:.2f} kN.m")

    return BaseRotationResult(
        combo_name=combo.name,
        axis=axis,
        axis_label=axis_label,
        points=points,
        N_total=N_total,
        M_reference=M_reference,
        ks_used=ks_used,
        ks_source=ks_source,
        joint_rotational_stiffness=joint_k,
        rigid_connection_assumed=assume_rigid_connection,
        column_rotational_stiffness=column_k,
        initial_rotational_stiffness=initial_rotational_stiffness,
        tangent_stiffness_initial=stiff["k_tangent_initial"],
        tangent_stiffness_reference=stiff["k_tangent_reference"],
        secant_stiffness_reference=stiff["k_secant_reference"],
        linear_equivalent_stiffness=stiff["k_linear"],
        bilinear_stiffness_1=stiff["k1"],
        bilinear_stiffness_2=stiff["k2"],
        bilinear_theta_break=stiff["theta_break"],
        bilinear_moment_break=stiff["moment_break"],
        stiffness_ratio=stiffness_ratio,
        classification=classification,
        reference_moment_used=stiff["m_ref"],
        reference_theta=stiff["theta_ref"],
        reference_contact_ratio=reference_contact_ratio,
        no_uplift_at_reference=no_uplift_at_reference,
        uplift_theta=uplift_theta,
        uplift_moment=uplift_moment,
        moment_capacity=moment_capacity,
        notes=notes,
    )