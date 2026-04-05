"""
tests/test_stability.py
Unit tests for core/stability.py
"""

import pytest

from core.loads import LoadCombination
from core.soil_pressure import FootingGeometry, SoilProperties
from core.stability import StabilityParams, StabilityResult, check_stability


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def soil():
    return SoilProperties(qa=200.0, gamma_soil=18.0, Df=1.5)


@pytest.fixture
def geom():
    return FootingGeometry(B=2.0, L=2.0, h=0.5, bx=0.4, by=0.4, cover=0.075)


@pytest.fixture
def params():
    return StabilityParams(
        mu_friction=0.45,
        FS_sliding_min=1.5,
        FS_overturning_min=1.5,
        FS_uplift_min=1.1,
    )


# ---------------------------------------------------------------------------
# test_sliding_adequate
# ---------------------------------------------------------------------------

class TestSlidingAdequate:
    def test_small_shear_passes(self, geom, soil, params):
        """Very small Vx → FS_sliding_x >> 1.5"""
        combo = LoadCombination("S-ok", N=1000.0, Vx=5.0, Vy=0.0,
                                Mx=0.0, My=0.0, combo_type="service")
        result = check_stability(combo, geom, soil, params)
        assert result.passes_sliding_x is True
        assert result.FS_sliding_x > params.FS_sliding_min

    def test_zero_shear_gives_inf_fs(self, geom, soil, params):
        combo = LoadCombination("S-0v", N=800.0, Vx=0.0, Vy=0.0,
                                Mx=0.0, My=0.0, combo_type="service")
        result = check_stability(combo, geom, soil, params)
        assert result.FS_sliding_x >= 999.0
        assert result.passes_sliding_x is True


# ---------------------------------------------------------------------------
# test_sliding_inadequate
# ---------------------------------------------------------------------------

class TestSlidingInadequate:
    def test_large_shear_fails(self, geom, soil, params):
        """
        N_total ≈ 800 + W_footing(96) + W_soil(72) = 968 kN
        Friction = 0.45 * 968 = 435.6 kN
        FS = 435.6 / 600 = 0.73 < 1.5  → FAIL
        """
        combo = LoadCombination("S-fail", N=800.0, Vx=600.0, Vy=0.0,
                                Mx=0.0, My=0.0, combo_type="service")
        result = check_stability(combo, geom, soil, params)
        assert result.passes_sliding_x is False
        assert result.FS_sliding_x < params.FS_sliding_min


# ---------------------------------------------------------------------------
# test_overturning_adequate
# ---------------------------------------------------------------------------

class TestOverturningAdequate:
    def test_large_N_small_M_passes(self, geom, soil, params):
        """
        Large vertical load, tiny moment → FS >> 1.5.
        N_total ≈ 968 kN.  M_dest_x = |Mx + Vy*h| = 10 kN·m
        M_stab = 968 * (L/2) = 968 kN·m  → FS >> 1.5
        """
        combo = LoadCombination("OT-ok", N=800.0, Vx=0.0, Vy=5.0,
                                Mx=10.0, My=0.0, combo_type="service")
        result = check_stability(combo, geom, soil, params)
        assert result.passes_overturning_x is True
        assert result.FS_overturning_x > params.FS_overturning_min


# ---------------------------------------------------------------------------
# test_overturning_inadequate
# ---------------------------------------------------------------------------

class TestOverturningInadequate:
    def test_large_moment_fails(self, geom, soil, params):
        """
        N_total ≈ 968 kN, huge Mx.
        M_dest_x = |Mx + Vy*h| = |2000 + 0| = 2000 kN·m
        M_stab   = 968 * 1.0 = 968 kN·m
        FS = 968/2000 = 0.48 < 1.5  → FAIL
        """
        combo = LoadCombination("OT-fail", N=800.0, Vx=0.0, Vy=0.0,
                                Mx=2000.0, My=0.0, combo_type="service")
        result = check_stability(combo, geom, soil, params)
        assert result.passes_overturning_x is False
        assert result.FS_overturning_x < params.FS_overturning_min


# ---------------------------------------------------------------------------
# Additional: passes_all flag
# ---------------------------------------------------------------------------

class TestPassesAll:
    def test_all_pass_when_adequate(self, geom, soil, params):
        combo = LoadCombination("ALL-ok", N=1000.0, Vx=10.0, Vy=10.0,
                                Mx=20.0, My=20.0, combo_type="service")
        result = check_stability(combo, geom, soil, params)
        # passes_all reflects the logical AND of all individual checks
        assert result.passes_all == (
            result.passes_sliding_x
            and result.passes_sliding_y
            and result.passes_overturning_x
            and result.passes_overturning_y
            and result.passes_uplift
        )

    def test_fields_are_floats(self, geom, soil, params):
        combo = LoadCombination("types", N=500.0, Vx=20.0, Vy=20.0,
                                Mx=30.0, My=30.0, combo_type="service")
        result = check_stability(combo, geom, soil, params)
        assert isinstance(result.FS_sliding_x, float)
        assert isinstance(result.FS_overturning_y, float)
