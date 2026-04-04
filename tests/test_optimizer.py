"""
tests/test_optimizer.py
Unit tests for core/optimizer.py
"""

import pytest

from core.combinations import CombinationFactors, generate_combinations
from core.loads import LoadCase, LoadSet
from core.optimizer import (
    OptimizationConstraints,
    OptimizationObjective,
    OptimizationResult,
    optimize_footing,
)
from core.rc_design import MaterialProperties
from core.soil_pressure import FootingGeometry, SoilProperties
from core.stability import StabilityParams


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def soil():
    return SoilProperties(qa=250.0, gamma_soil=18.0, Df=1.5)


@pytest.fixture
def mats():
    return MaterialProperties(fc=21.0, fy=420.0)


@pytest.fixture
def stab():
    return StabilityParams(mu_friction=0.45, FS_sliding_min=1.5, FS_overturning_min=1.5)


@pytest.fixture
def simple_load_set():
    """Moderate loads that should yield a feasible footing around 2 × 2 m."""
    ls = LoadSet()
    ls.add_case(LoadCase("Dead", N=600.0, Vx=15.0, Vy=10.0, Mx=30.0, My=20.0, load_type="dead"))
    ls.add_case(LoadCase("Live", N=300.0, Vx=8.0,  Vy=5.0,  Mx=15.0, My=10.0, load_type="live"))
    factors = CombinationFactors.aci_asce7()
    return generate_combinations(ls, factors)


@pytest.fixture
def initial_geom():
    return FootingGeometry(B=2.0, L=2.0, h=0.50, bx=0.4, by=0.4, cover=0.075)


@pytest.fixture
def tight_constraints():
    """Constraints that encompass a reasonable solution."""
    return OptimizationConstraints(
        B_min=1.5, B_max=3.0,
        L_min=1.5, L_max=3.0,
        h_min=0.40, h_max=0.80,
        step_B=0.25, step_L=0.25, step_h=0.20,
        force_square=True,
        allow_partial_contact=True,
    )


@pytest.fixture
def impossible_constraints():
    """Constraints so tight that no footing can satisfy qa=250."""
    return OptimizationConstraints(
        B_min=0.40, B_max=0.60,  # too small for the applied loads
        L_min=0.40, L_max=0.60,
        h_min=0.20, h_max=0.25,
        step_B=0.10, step_L=0.10, step_h=0.05,
        allow_partial_contact=False,
    )


# ---------------------------------------------------------------------------
# test_basic_optimization_finds_solution
# ---------------------------------------------------------------------------

class TestBasicOptimization:
    def test_converges_and_has_best_geometry(
        self, simple_load_set, soil, mats, stab, initial_geom, tight_constraints
    ):
        obj = OptimizationObjective(objective="min_area")
        result = optimize_footing(
            initial_geom, simple_load_set, soil, mats, stab, tight_constraints, obj
        )
        assert result.converged is True
        assert result.best_geometry is not None
        assert result.n_feasible > 0

    def test_best_geometry_within_constraints(
        self, simple_load_set, soil, mats, stab, initial_geom, tight_constraints
    ):
        obj = OptimizationObjective(objective="min_area")
        result = optimize_footing(
            initial_geom, simple_load_set, soil, mats, stab, tight_constraints, obj
        )
        if result.best_geometry:
            bg = result.best_geometry
            assert tight_constraints.B_min <= bg.B <= tight_constraints.B_max + 0.01
            assert tight_constraints.L_min <= bg.L <= tight_constraints.L_max + 0.01
            assert tight_constraints.h_min <= bg.h <= tight_constraints.h_max + 0.01

    def test_objective_value_is_finite(
        self, simple_load_set, soil, mats, stab, initial_geom, tight_constraints
    ):
        obj = OptimizationObjective(objective="min_volume")
        result = optimize_footing(
            initial_geom, simple_load_set, soil, mats, stab, tight_constraints, obj
        )
        assert result.objective_value < 1e17


# ---------------------------------------------------------------------------
# test_locked_B_respected
# ---------------------------------------------------------------------------

class TestLockedDimensions:
    def test_locked_B_gives_fixed_B(
        self, simple_load_set, soil, mats, stab, initial_geom
    ):
        constraints = OptimizationConstraints(
            B_min=1.0, B_max=4.0,
            L_min=1.0, L_max=4.0,
            h_min=0.30, h_max=0.90,
            step_B=0.25, step_L=0.25, step_h=0.20,
            lock_B=True,  # B fixed at initial_geom.B = 2.0
        )
        obj = OptimizationObjective(objective="min_area")
        result = optimize_footing(
            initial_geom, simple_load_set, soil, mats, stab, constraints, obj
        )
        for r in result.all_results:
            assert abs(r["B"] - initial_geom.B) < 1e-6

    def test_locked_h_gives_fixed_h(
        self, simple_load_set, soil, mats, stab, initial_geom
    ):
        constraints = OptimizationConstraints(
            B_min=1.5, B_max=3.0,
            L_min=1.5, L_max=3.0,
            h_min=0.40, h_max=0.80,
            step_B=0.25, step_L=0.25, step_h=0.20,
            lock_h=True,  # h fixed at initial_geom.h = 0.5
        )
        obj = OptimizationObjective(objective="min_area")
        result = optimize_footing(
            initial_geom, simple_load_set, soil, mats, stab, constraints, obj
        )
        for r in result.all_results:
            assert abs(r["h"] - initial_geom.h) < 1e-6

    def test_force_square_all_results_have_equal_BL(
        self, simple_load_set, soil, mats, stab, initial_geom
    ):
        constraints = OptimizationConstraints(
            B_min=1.5, B_max=2.5,
            L_min=1.5, L_max=2.5,
            h_min=0.4, h_max=0.7,
            step_B=0.25, step_L=0.25, step_h=0.15,
            force_square=True,
        )
        obj = OptimizationObjective(objective="min_area")
        result = optimize_footing(
            initial_geom, simple_load_set, soil, mats, stab, constraints, obj
        )
        for r in result.all_results:
            assert abs(r["B"] - r["L"]) < 1e-6


# ---------------------------------------------------------------------------
# test_no_solution_reports_reason
# ---------------------------------------------------------------------------

class TestNoSolution:
    def test_no_solution_converged_false(
        self, simple_load_set, soil, mats, stab, initial_geom, impossible_constraints
    ):
        obj = OptimizationObjective(objective="min_area")
        result = optimize_footing(
            initial_geom, simple_load_set, soil, mats, stab, impossible_constraints, obj
        )
        assert result.converged is False

    def test_no_solution_reason_nonempty(
        self, simple_load_set, soil, mats, stab, initial_geom, impossible_constraints
    ):
        obj = OptimizationObjective(objective="min_area")
        result = optimize_footing(
            initial_geom, simple_load_set, soil, mats, stab, impossible_constraints, obj
        )
        assert len(result.reason) > 0

    def test_no_solution_best_geometry_is_none(
        self, simple_load_set, soil, mats, stab, initial_geom, impossible_constraints
    ):
        obj = OptimizationObjective(objective="min_area")
        result = optimize_footing(
            initial_geom, simple_load_set, soil, mats, stab, impossible_constraints, obj
        )
        assert result.best_geometry is None

    def test_no_solution_iterations_greater_than_zero(
        self, simple_load_set, soil, mats, stab, initial_geom, impossible_constraints
    ):
        obj = OptimizationObjective(objective="min_area")
        result = optimize_footing(
            initial_geom, simple_load_set, soil, mats, stab, impossible_constraints, obj
        )
        assert result.n_iterations > 0
