"""
tests/test_soil_pressure.py
Unit tests for core/soil_pressure.py
"""

import math
import pytest

from core.loads import LoadCombination
from core.soil_pressure import (
    FootingGeometry,
    PressureResult,
    SoilProperties,
    analyze_pressure,
    check_full_contact,
    compute_eccentricities,
    compute_pressures_full_contact,
    compute_pressures_partial_contact,
    compute_total_load,
    find_critical_pressures,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def simple_soil():
    return SoilProperties(qa=200.0, gamma_soil=18.0, Df=1.5)


@pytest.fixture
def square_geom():
    """2.0 × 2.0 m, 0.5 m thick, 40×40 cm column."""
    return FootingGeometry(B=2.0, L=2.0, h=0.5, bx=0.4, by=0.4, cover=0.075)


@pytest.fixture
def combo_centered():
    """Pure axial – no moment, no shear."""
    return LoadCombination("C-0", N=800.0, Vx=0.0, Vy=0.0, Mx=0.0, My=0.0, combo_type="service")


@pytest.fixture
def combo_moment():
    """Axial + bending in X only."""
    return LoadCombination("C-M", N=800.0, Vx=0.0, Vy=0.0, Mx=80.0, My=0.0, combo_type="service")


@pytest.fixture
def combo_large_moment():
    """Very large eccentricity → partial contact even after adding self-weight."""
    # N=200, Mx=600 → N_total≈320, ey=600/320=1.875 >> L/6=0.333 → partial
    return LoadCombination("C-BIG", N=200.0, Vx=0.0, Vy=0.0, Mx=600.0, My=0.0, combo_type="service")


# ---------------------------------------------------------------------------
# test_full_contact_detection
# ---------------------------------------------------------------------------

class TestFullContactDetection:
    def test_within_kern_is_full_contact(self):
        # |ex| = 0.1 ≤ B/6 = 0.333
        assert check_full_contact(0.1, 0.1, 2.0, 2.0) is True

    def test_at_kern_boundary_is_full_contact(self):
        B, L = 3.0, 3.0
        ex = B / 6.0
        ey = L / 6.0
        assert check_full_contact(ex, ey, B, L) is True

    def test_outside_kern_x_is_partial(self):
        B, L = 2.0, 2.0
        ex = B / 6.0 + 0.01  # just outside
        assert check_full_contact(ex, 0.0, B, L) is False

    def test_outside_kern_y_is_partial(self):
        B, L = 2.0, 3.0
        ey = L / 6.0 + 0.01
        assert check_full_contact(0.0, ey, B, L) is False

    def test_zero_eccentricity_is_full_contact(self):
        assert check_full_contact(0.0, 0.0, 2.0, 2.0) is True


# ---------------------------------------------------------------------------
# test_pressures_full_contact_symmetric
# ---------------------------------------------------------------------------

class TestPressuresFullContactSymmetric:
    def test_uniform_pressure_no_moment(self, combo_centered, square_geom, simple_soil):
        """Centered load → q_max = q_min = q_avg (uniform)."""
        N_total, Mx_total, My_total = compute_total_load(
            combo_centered, square_geom, simple_soil
        )
        q_max, q_min, q_avg, q_corner = compute_pressures_full_contact(
            N_total, Mx_total, My_total, square_geom.B, square_geom.L
        )
        assert abs(q_max - q_avg) < 0.1
        assert abs(q_min - q_avg) < 0.1
        assert q_avg > 0.0

    def test_pressure_equals_expected(self, simple_soil):
        """Manual calculation: N=1000 kN on 2×2 → q = 1000/4 = 250 kPa."""
        N, Mx, My = 1000.0, 0.0, 0.0
        B, L = 2.0, 2.0
        q_max, q_min, q_avg, _ = compute_pressures_full_contact(N, Mx, My, B, L)
        assert abs(q_avg - 250.0) < 0.01
        assert abs(q_max - 250.0) < 0.01

    def test_total_load_includes_self_weight(self, combo_centered, square_geom, simple_soil):
        N_total, _, _ = compute_total_load(combo_centered, square_geom, simple_soil)
        # W_footing = 2*2*0.5*24 = 48 kN; W_soil = 2*2*(1.5-0.5)*18 = 72 kN
        expected = 800.0 + 48.0 + 72.0
        assert abs(N_total - expected) < 0.5


# ---------------------------------------------------------------------------
# test_pressures_full_contact_with_moment
# ---------------------------------------------------------------------------

class TestPressuresFullContactWithMoment:
    def test_moment_increases_qmax(self, combo_moment, square_geom, simple_soil):
        N_t, Mx_t, My_t = compute_total_load(combo_moment, square_geom, simple_soil)
        q_max, q_min, q_avg, _ = compute_pressures_full_contact(
            N_t, Mx_t, My_t, square_geom.B, square_geom.L
        )
        assert q_max > q_avg
        assert q_min < q_avg

    def test_moment_formula_manually(self):
        """
        N=1000 kN, Mx=100 kN·m, My=0, B=2, L=2.
        A=4, Ix=B*L³/12=2*8/12=4/3, q_max=1000/4+100*(1)/(4/3)=250+75=325.
        """
        N, Mx, My = 1000.0, 100.0, 0.0
        B, L = 2.0, 2.0
        q_max, q_min, q_avg, _ = compute_pressures_full_contact(N, Mx, My, B, L)
        Ix = B * L ** 3 / 12.0
        dq = abs(Mx) * (L / 2.0) / Ix
        assert abs(q_max - (q_avg + dq)) < 0.1

    def test_eccentricity_calculation(self):
        N, Mx, My = 1000.0, 100.0, 50.0
        ex, ey = compute_eccentricities(N, Mx, My)
        assert abs(ex - 0.05) < 1e-9   # ex = My/N
        assert abs(ey - 0.10) < 1e-9   # ey = Mx/N


# ---------------------------------------------------------------------------
# test_partial_contact_detection
# ---------------------------------------------------------------------------

class TestPartialContactDetection:
    def test_large_eccentricity_triggers_partial(self, combo_large_moment, square_geom, simple_soil):
        result = analyze_pressure(
            combo_large_moment, square_geom, simple_soil, allow_partial_contact=True
        )
        assert result.full_contact is False

    def test_partial_contact_qmin_is_zero(self, combo_large_moment, square_geom, simple_soil):
        result = analyze_pressure(
            combo_large_moment, square_geom, simple_soil, allow_partial_contact=True
        )
        assert result.q_min == pytest.approx(0.0)

    def test_partial_contact_ratio_less_than_one(self, combo_large_moment, square_geom, simple_soil):
        result = analyze_pressure(
            combo_large_moment, square_geom, simple_soil, allow_partial_contact=True
        )
        assert result.contact_ratio < 1.0


# ---------------------------------------------------------------------------
# test_pressures_partial_contact
# ---------------------------------------------------------------------------

class TestPressuresPartialContact:
    def test_partial_qmax_positive(self):
        N, Mx, My = 500.0, 250.0, 0.0
        B, L = 2.0, 2.0
        q_max, eff_B, eff_L = compute_pressures_partial_contact(N, Mx, My, B, L)
        assert q_max > 0.0
        assert eff_B <= B
        assert eff_L <= L

    def test_partial_meyerhof_formula_1d(self):
        """
        1D eccentricity in Y only.
        N=500, Mx=200, My=0, B=L=2 → ey=0.4, eff_L=3*(1-0.4)=1.8, eff_B≈2
        q_max = 2*500/(2*1.8) = 277.8 kPa
        """
        N, Mx, My = 500.0, 200.0, 0.0
        B, L = 2.0, 2.0
        ey = Mx / N  # 0.4
        eff_L_expected = 3.0 * (L / 2.0 - abs(ey))  # 3*(1-0.4)=1.8
        q_max_expected = 2.0 * N / (B * eff_L_expected)

        q_max, eff_B, eff_L = compute_pressures_partial_contact(N, Mx, My, B, L)
        assert abs(q_max - q_max_expected) < 1.0  # allow 1 kPa tolerance

    def test_zero_N_returns_zero(self):
        q_max, eff_B, eff_L = compute_pressures_partial_contact(0.0, 0.0, 0.0, 2.0, 2.0)
        assert q_max == 0.0


# ---------------------------------------------------------------------------
# test_find_critical_pressures
# ---------------------------------------------------------------------------

class TestFindCriticalPressures:
    def test_finds_max_qmax(self, square_geom, simple_soil):
        combos = [
            LoadCombination(f"C{i}", N=500.0 + i * 100, Vx=0.0, Vy=0.0,
                            Mx=0.0, My=0.0, combo_type="service")
            for i in range(4)
        ]
        results = [analyze_pressure(c, square_geom, simple_soil) for c in combos]
        crit = find_critical_pressures(results)
        assert crit["max_qmax"].combo_name == "C3"

    def test_empty_list_raises(self):
        with pytest.raises(ValueError):
            find_critical_pressures([])
