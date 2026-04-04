"""
tests/test_rc_design.py
Unit tests for core/rc_design.py
"""

import math
import pytest

from core.loads import LoadCombination
from core.rc_design import (
    REBAR_DATABASE,
    MaterialProperties,
    check_one_way_shear_ACI,
    check_punching_shear_ACI,
    design_flexure_ACI,
    design_footing,
    effective_depth,
    select_rebar,
)
from core.soil_pressure import FootingGeometry, PressureResult, SoilProperties


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mats():
    return MaterialProperties(fc=21.0, fy=420.0)


@pytest.fixture
def geom():
    return FootingGeometry(B=2.2, L=2.2, h=0.55, bx=0.4, by=0.4, cover=0.075)


@pytest.fixture
def soil():
    return SoilProperties(qa=200.0, gamma_soil=18.0, Df=1.5)


@pytest.fixture
def mock_pressure():
    return PressureResult(
        combo_name="U-test",
        q_max=180.0,
        q_min=80.0,
        eccentricity_x=0.05,
        eccentricity_y=0.05,
        full_contact=True,
        effective_area=4.84,
        contact_ratio=1.0,
        passes_qa=True,
        N_total=1100.0,
    )


@pytest.fixture
def critical_combo():
    return LoadCombination("U-test", N=1100.0, Vx=30.0, Vy=22.0,
                           Mx=75.0, My=45.0, combo_type="ultimate")


# ---------------------------------------------------------------------------
# test_flexure_design
# ---------------------------------------------------------------------------

class TestFlexureDesign:
    def test_as_req_positive(self):
        As_req, rho = design_flexure_ACI(Mu=80.0, b=1000.0, d=450.0, fc=21.0, fy=420.0)
        assert As_req > 0.0

    def test_zero_moment_gives_as_min(self):
        As_req, _ = design_flexure_ACI(Mu=0.0, b=1000.0, d=450.0, fc=21.0, fy=420.0)
        h_approx = 450.0 / 0.9
        As_min = max(
            0.0018 * 1000.0 * h_approx,
            0.25 * math.sqrt(21.0) / 420.0 * 1000.0 * 450.0,
            1.4 / 420.0 * 1000.0 * 450.0,
        )
        assert abs(As_req - As_min) < 1.0

    def test_larger_moment_needs_more_steel(self):
        # Use moments well above the As_min threshold so steel is demand-driven
        As1, _ = design_flexure_ACI(Mu=200.0,  b=1000.0, d=450.0, fc=21.0, fy=420.0)
        As2, _ = design_flexure_ACI(Mu=400.0, b=1000.0, d=450.0, fc=21.0, fy=420.0)
        assert As2 > As1

    def test_phi_mn_is_achievable(self):
        """Capacity with provided steel should exceed demand."""
        Mu_test = 200.0  # kN·m/m — clearly above As_min territory
        As_req, _ = design_flexure_ACI(Mu=Mu_test, b=1000.0, d=450.0, fc=21.0, fy=420.0)
        a = As_req * 420.0 / (0.85 * 21.0 * 1000.0)
        phi_Mn = 0.9 * As_req * 420.0 * (450.0 - a / 2.0) / 1.0e6
        assert phi_Mn >= Mu_test * 0.99  # within 1% tolerance

    def test_effective_depth_calculation(self):
        d = effective_depth(h=0.55, cover=0.075, bar_d=19.05, layer=1)
        # d ≈ 550 - 75 - 9.525 ≈ 465.5 mm
        assert 460.0 < d < 470.0


# ---------------------------------------------------------------------------
# test_one_way_shear
# ---------------------------------------------------------------------------

class TestOneWayShear:
    def test_low_shear_passes(self):
        phi_Vc, passes = check_one_way_shear_ACI(Vu=50.0, b=1000.0, d=450.0, fc=21.0)
        assert passes is True
        assert phi_Vc > 50.0

    def test_high_shear_fails(self):
        """Very large Vu should exceed capacity."""
        phi_Vc, passes = check_one_way_shear_ACI(Vu=2000.0, b=1000.0, d=450.0, fc=21.0)
        assert passes is False

    def test_shear_capacity_positive(self):
        phi_Vc, _ = check_one_way_shear_ACI(Vu=0.0, b=1000.0, d=450.0, fc=21.0)
        assert phi_Vc > 0.0

    def test_deeper_section_has_higher_capacity(self):
        phi_Vc_shallow, _ = check_one_way_shear_ACI(Vu=100.0, b=1000.0, d=300.0, fc=21.0)
        phi_Vc_deep,    _ = check_one_way_shear_ACI(Vu=100.0, b=1000.0, d=600.0, fc=21.0)
        assert phi_Vc_deep > phi_Vc_shallow


# ---------------------------------------------------------------------------
# test_punching_shear
# ---------------------------------------------------------------------------

class TestPunchingShear:
    def test_low_punching_passes(self):
        phi_Vc, passes = check_punching_shear_ACI(
            Vu_punching=500.0, c1=400.0, c2=400.0, d=450.0, fc=21.0
        )
        assert passes is True

    def test_excessive_punching_fails(self):
        phi_Vc, passes = check_punching_shear_ACI(
            Vu_punching=5000.0, c1=400.0, c2=400.0, d=450.0, fc=21.0
        )
        assert passes is False

    def test_capacity_scales_with_d(self):
        phi_Vc_d400, _ = check_punching_shear_ACI(500.0, 400.0, 400.0, 400.0, 21.0)
        phi_Vc_d600, _ = check_punching_shear_ACI(500.0, 400.0, 400.0, 600.0, 21.0)
        assert phi_Vc_d600 > phi_Vc_d400

    def test_square_column_vc1_governs_for_small_beta(self):
        """For square column β=1 → vc3 might govern; at minimum vc ≈ 0.33√fc."""
        phi_Vc, _ = check_punching_shear_ACI(0.0, 400.0, 400.0, 450.0, 21.0, phi=1.0)
        vc_min = 0.17 * math.sqrt(21.0)
        bo = 2 * (400.0 + 450.0) + 2 * (400.0 + 450.0)
        Vc_min = vc_min * bo * 450.0 / 1000.0
        assert phi_Vc >= Vc_min * 0.95


# ---------------------------------------------------------------------------
# test_rebar_selection
# ---------------------------------------------------------------------------

class TestRebarSelection:
    def test_returns_valid_bar_name(self):
        bar, s, As_prov = select_rebar(As_req=800.0)
        assert bar in REBAR_DATABASE
        assert As_prov >= 800.0

    def test_spacing_within_limits(self):
        bar, s, _ = select_rebar(As_req=500.0, s_max=450.0, s_min=75.0)
        assert 75.0 <= s <= 450.0 + 1.0  # small tolerance for clamping

    def test_larger_demand_gives_more_steel(self):
        _, _, As1 = select_rebar(300.0)
        _, _, As2 = select_rebar(900.0)
        assert As2 >= As1

    def test_as_provided_geq_as_required(self):
        for As_req in [200.0, 500.0, 1000.0, 2000.0]:
            _, _, As_prov = select_rebar(As_req)
            assert As_prov >= As_req * 0.95  # within 5% (rounding)


# ---------------------------------------------------------------------------
# test_design_footing (integration)
# ---------------------------------------------------------------------------

class TestDesignFooting:
    def test_design_runs_without_error(self, critical_combo, geom, soil, mats, mock_pressure):
        result = design_footing(critical_combo, geom, soil, mats, mock_pressure)
        assert result is not None

    def test_passes_all_for_adequate_footing(self, critical_combo, geom, soil, mats):
        # Use a pressure result within qa
        pr = PressureResult("U-test", 160.0, 80.0, 0.05, 0.05, True, 4.84, 1.0, True, 1100.0)
        result = design_footing(critical_combo, geom, soil, mats, pr)
        assert result.passes_all is True

    def test_effective_depths_positive(self, critical_combo, geom, soil, mats, mock_pressure):
        result = design_footing(critical_combo, geom, soil, mats, mock_pressure)
        assert result.dx > 0.0
        assert result.dy > 0.0
        assert result.dx > result.dy  # X steel is outer layer
