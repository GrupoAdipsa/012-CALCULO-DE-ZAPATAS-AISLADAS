from core.base_rotation import generate_base_moment_rotation_curve
from core.loads import LoadCombination
from core.rc_design import MaterialProperties
from core.soil_pressure import FootingGeometry, SoilProperties


def test_generate_base_moment_rotation_curve_returns_monotonic_curve():
    combo = LoadCombination("U1", 900.0, 25.0, 0.0, 0.0, 180.0, "ultimate")
    geom = FootingGeometry(B=2.5, L=2.5, h=0.60, bx=0.45, by=0.45, cover=0.075)
    soil = SoilProperties(qa=220.0, gamma_soil=18.0, Df=1.5, ks=18000.0)
    mats = MaterialProperties(fc=28.0, fy=420.0)

    result = generate_base_moment_rotation_curve(
        combo=combo,
        geom=geom,
        soil=soil,
        materials=mats,
        column_effective_length=3.0,
        theta_max=0.015,
        n_points=25,
    )

    assert len(result.points) == 25
    assert result.initial_rotational_stiffness > 0.0
    assert result.tangent_stiffness_initial > 0.0
    assert result.secant_stiffness_reference > 0.0
    assert result.linear_equivalent_stiffness > 0.0
    assert result.bilinear_stiffness_1 > 0.0
    assert result.bilinear_theta_break >= 0.0
    assert result.bilinear_moment_break >= 0.0
    assert result.classification in {"articulada", "semirrígida", "rígida"}
    assert result.points[-1].theta_total >= result.points[1].theta_total
    assert result.points[-1].moment >= result.points[1].moment