"""
core/combinations.py
Automatic combination generation following ACI 318 / ASCE-7 load combinations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from core.loads import LoadCase, LoadCombination, LoadSet


# ---------------------------------------------------------------------------
# Factor table types
# ---------------------------------------------------------------------------

# A combo spec is a dict mapping load_type -> factor
_ComboSpec = Dict[str, float]


@dataclass
class CombinationFactors:
    """
    Holds factor tables for service and ultimate combinations.

    Each entry in *service_combos* / *ultimate_combos* is a tuple
    (combo_name, {load_type: factor}).
    """

    service_combos: List[Tuple[str, _ComboSpec]] = field(default_factory=list)
    ultimate_combos: List[Tuple[str, _ComboSpec]] = field(default_factory=list)

    # ------------------------------------------------------------------ #
    # Factory method: ACI 318-19 / ASCE-7-16 standard combinations
    # ------------------------------------------------------------------ #

    @classmethod
    def aci_asce7(cls) -> "CombinationFactors":
        """Return standard ACI 318 / ASCE-7 combination factors."""

        service: List[Tuple[str, _ComboSpec]] = [
            # ASCE-7 Table 4.3-1 (ASD / service combinations)
            ("S-1: D",          {"dead": 1.0}),
            ("S-2: D+L",        {"dead": 1.0, "live": 1.0}),
            ("S-3: D+Lr",       {"dead": 1.0, "roof_live": 1.0}),
            ("S-4: D+0.75L+0.75Lr",
                                {"dead": 1.0, "live": 0.75, "roof_live": 0.75}),
            ("S-5: D+0.6Wx",    {"dead": 1.0, "wind_x": 0.6}),
            ("S-6: D+0.6Wy",    {"dead": 1.0, "wind_y": 0.6}),
            ("S-7: D+0.7Ex",    {"dead": 1.0, "seismic_x": 0.7}),
            ("S-8: D+0.7Ey",    {"dead": 1.0, "seismic_y": 0.7}),
            ("S-9: D+0.75L+0.75(0.6Wx)",
                                {"dead": 1.0, "live": 0.75, "wind_x": 0.75 * 0.6}),
            ("S-10: D+0.75L+0.75(0.6Wy)",
                                {"dead": 1.0, "live": 0.75, "wind_y": 0.75 * 0.6}),
            ("S-11: 0.6D+0.6Wx",{"dead": 0.6, "wind_x": 0.6}),
            ("S-12: 0.6D+0.6Wy",{"dead": 0.6, "wind_y": 0.6}),
        ]

        ultimate: List[Tuple[str, _ComboSpec]] = [
            # ACI 318-19 Table 5.3.1 / ASCE-7-16 Table 2.3.6
            ("U-1: 1.4D",       {"dead": 1.4}),
            ("U-2: 1.2D+1.6L+0.5Lr",
                                {"dead": 1.2, "live": 1.6, "roof_live": 0.5}),
            ("U-3: 1.2D+1.6Lr+L",
                                {"dead": 1.2, "roof_live": 1.6, "live": 1.0}),
            ("U-4: 1.2D+1.0Wx+L+0.5Lr",
                                {"dead": 1.2, "wind_x": 1.0, "live": 1.0, "roof_live": 0.5}),
            ("U-5: 1.2D+1.0Wy+L+0.5Lr",
                                {"dead": 1.2, "wind_y": 1.0, "live": 1.0, "roof_live": 0.5}),
            ("U-6: 0.9D+1.0Wx", {"dead": 0.9, "wind_x": 1.0}),
            ("U-7: 0.9D+1.0Wy", {"dead": 0.9, "wind_y": 1.0}),
            ("U-8: 1.2D+1.0Ex+L",
                                {"dead": 1.2, "seismic_x": 1.0, "live": 1.0}),
            ("U-9: 1.2D+1.0Ey+L",
                                {"dead": 1.2, "seismic_y": 1.0, "live": 1.0}),
            ("U-10: 0.9D+1.0Ex",{"dead": 0.9, "seismic_x": 1.0}),
            ("U-11: 0.9D+1.0Ey",{"dead": 0.9, "seismic_y": 1.0}),
        ]

        return cls(service_combos=service, ultimate_combos=ultimate)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _apply_combo(
    cases_by_type: Dict[str, List[LoadCase]],
    spec: _ComboSpec,
    combo_name: str,
    combo_type: str,
) -> LoadCombination:
    """
    Multiply each group of cases by its factor and accumulate into one combination.

    If multiple cases share the same load_type (e.g. two dead-load patterns)
    all of them are included (factored and summed).
    """
    N_total = Vx_total = Vy_total = Mx_total = My_total = 0.0

    for load_type, factor in spec.items():
        for case in cases_by_type.get(load_type, []):
            N_total  += case.N  * factor
            Vx_total += case.Vx * factor
            Vy_total += case.Vy * factor
            Mx_total += case.Mx * factor
            My_total += case.My * factor

    return LoadCombination(
        name=combo_name,
        N=N_total,
        Vx=Vx_total,
        Vy=Vy_total,
        Mx=Mx_total,
        My=My_total,
        combo_type=combo_type,
    )


def generate_combinations(
    load_set: LoadSet,
    factors: CombinationFactors,
) -> LoadSet:
    """
    Generate combinations from basic load cases already stored in *load_set*.

    The function creates a **new** LoadSet that contains:
    - All original load cases (copied)
    - All pre-existing combinations (copied)
    - The newly generated combinations from the factor tables

    Parameters
    ----------
    load_set:
        Source LoadSet with at minimum the basic LoadCase objects.
    factors:
        CombinationFactors instance (use ``CombinationFactors.aci_asce7()``
        for standard ACI/ASCE-7 combinations).

    Returns
    -------
    LoadSet
        New LoadSet populated with generated combinations.
    """
    # Group cases by type for fast lookup
    cases_by_type: Dict[str, List[LoadCase]] = {}
    for case in load_set.cases:
        cases_by_type.setdefault(case.load_type, []).append(case)

    result = LoadSet()

    # Copy original cases
    for case in load_set.cases:
        result.add_case(case)

    # Copy pre-existing combinations
    for combo in load_set.combinations:
        result.add_combination(combo)

    # Generate service combinations
    for name, spec in factors.service_combos:
        # Only generate if at least one load type in the spec is present
        if any(lt in cases_by_type for lt in spec):
            combo = _apply_combo(cases_by_type, spec, name, "service")
            result.add_combination(combo)

    # Generate ultimate combinations
    for name, spec in factors.ultimate_combos:
        if any(lt in cases_by_type for lt in spec):
            combo = _apply_combo(cases_by_type, spec, name, "ultimate")
            result.add_combination(combo)

    return result
