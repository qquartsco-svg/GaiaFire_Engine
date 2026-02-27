"""gravity_tides_demo.py — 조석-해양 탄소 펌프 검증 (넷째날 순환 3)

V1: 조석력 계산 — 달+태양, 사리-조금 변동
V2: 혼합 깊이 — 조석력에 비례, 사리 > 조금
V3: 탄소 펌프 — 강한 조석 → 높은 탄소 격리
V4: 1yr 시계열 — 사리-조금 주기 (29.5일) 변동
"""

import sys
import os
import math

_ENGINE_ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, _ENGINE_ROOT)

from gravity_tides import (
    TidalField, make_tidal_field,
    OceanNutrients, make_ocean_nutrients,
)

PASS = "✅ PASS"
FAIL = "❌ FAIL"


def check(cond: bool, label: str) -> bool:
    s = PASS if cond else FAIL
    print(f"    {s}  {label}")
    return cond


def run_gravity_tides_demo():
    print("=" * 65)
    print("  중력-조석 순환 — 넷째날 순환 3 검증")
    print("  달+태양 조석 → 해양 혼합 → 탄소 펌프 → CO₂ 격리")
    print("=" * 65)
    all_pass = True

    # ──────────────────────────────────────────────────────────────
    print("\n  [V1] 조석력 계산 — 달+태양, 사리-조금")

    tf = make_tidal_field()

    # 사리 시점 (spring tide: 달-지구-태양 직선)
    # 시노딕 주기 29.53일 중 0일 = 사리
    t_spring = 0.0
    t_neap   = (29.53 / 4) / 365.25  # 사분기 = 조금

    s_spring = tf.compute(t_spring)
    s_neap   = tf.compute(t_neap)

    print(f"    사리:  {s_spring.summary()}")
    print(f"    조금:  {s_neap.summary()}")

    ok1 = check(
        s_spring.F_total > s_neap.F_total,
        f"사리 조석력 > 조금 ({s_spring.F_total:.3f} > {s_neap.F_total:.3f})"
    )
    ok2 = check(
        s_spring.mixing_depth > s_neap.mixing_depth,
        f"사리 혼합 깊이 > 조금 ({s_spring.mixing_depth:.1f}m > {s_neap.mixing_depth:.1f}m)"
    )
    ok3 = check(
        s_spring.spring_neap > 0.8,
        f"사리 위상 > 0.8 ({s_spring.spring_neap:.2f})"
    )
    all_pass = all_pass and ok1 and ok2 and ok3

    # ──────────────────────────────────────────────────────────────
    print("\n  [V2] 조석력 강도 비교 — 강한 달 vs 약한 달")

    tf_strong = make_tidal_field(F_moon_ref=1.5)   # 달이 가까운 (먼 과거)
    tf_weak   = make_tidal_field(F_moon_ref=0.6)   # 달이 먼 (먼 미래)

    s_strong = tf_strong.compute(0.0)
    s_weak   = tf_weak.compute(0.0)

    print(f"    강한 달(1.5×):  mix={s_strong.mixing_depth:.1f}m  "
          f"nutrient={s_strong.nutrient_flux:.4f} g/m²/yr")
    print(f"    약한 달(0.6×):  mix={s_weak.mixing_depth:.1f}m    "
          f"nutrient={s_weak.nutrient_flux:.4f} g/m²/yr")

    ok4 = check(
        s_strong.mixing_depth > s_weak.mixing_depth * 1.5,
        f"강한 달 혼합 > 약한 달 × 1.5 ({s_strong.mixing_depth:.1f} > {s_weak.mixing_depth*1.5:.1f})"
    )
    ok5 = check(
        s_strong.nutrient_flux > s_weak.nutrient_flux,
        f"강한 달 영양염 > 약한 달 ({s_strong.nutrient_flux:.4f} > {s_weak.nutrient_flux:.4f})"
    )
    all_pass = all_pass and ok4 and ok5

    # ──────────────────────────────────────────────────────────────
    print("\n  [V3] 탄소 펌프 — 강한 조석 → 높은 탄소 격리")

    # 강한 조석 시나리오
    ocean_strong = make_ocean_nutrients(phyto_init=2.0)
    ocean_weak   = make_ocean_nutrients(phyto_init=2.0)

    # 10yr 진화
    nutrient_strong = 0.8   # 강한 조석 영양염 flux
    nutrient_weak   = 0.1   # 약한 조석 영양염 flux

    for _ in range(10):
        s_str = ocean_strong.step(dt=1.0, nutrient_flux=nutrient_strong)
        s_wk  = ocean_weak.step(dt=1.0, nutrient_flux=nutrient_weak)

    print(f"    강한 조석:  phyto={ocean_strong.phyto:.3f} gC/m²  "
          f"export={s_str.carbon_export:.4f} gC/m²/yr  "
          f"CO2_sink={s_str.CO2_sink_ppm:.6f} ppm/yr")
    print(f"    약한 조석:  phyto={ocean_weak.phyto:.3f} gC/m²  "
          f"export={s_wk.carbon_export:.4f} gC/m²/yr  "
          f"CO2_sink={s_wk.CO2_sink_ppm:.6f} ppm/yr")

    ok6 = check(
        ocean_strong.phyto > ocean_weak.phyto,
        f"강한 조석 → 더 많은 식물플랑크톤 ({ocean_strong.phyto:.3f} > {ocean_weak.phyto:.3f})"
    )
    ok7 = check(
        s_str.CO2_sink_ppm > s_wk.CO2_sink_ppm,
        f"강한 조석 → 더 큰 CO₂ 격리 ({s_str.CO2_sink_ppm:.6f} > {s_wk.CO2_sink_ppm:.6f})"
    )
    all_pass = all_pass and ok6 and ok7

    # ──────────────────────────────────────────────────────────────
    print("\n  [V4] 1yr 시계열 — 사리-조금 주기 (29.5일) 변동")

    tf_ref = make_tidal_field()
    ocean  = make_ocean_nutrients(phyto_init=1.0)

    T_synodic = 29.53 / 365.25  # [yr]
    dt_day    = 1.0 / 365.25     # 1일 스텝
    n_steps   = int(1.0 / dt_day)  # 1yr

    mix_vals     = []
    nutrient_vals = []
    co2_sink_yr  = 0.0

    for i in range(n_steps):
        t = i * dt_day
        ts = tf_ref.compute(t)
        os_ = ocean.step(dt=dt_day, nutrient_flux=ts.nutrient_flux)
        mix_vals.append(ts.mixing_depth)
        nutrient_vals.append(ts.nutrient_flux)
        co2_sink_yr += os_.CO2_sink_ppm * dt_day

    mix_min   = min(mix_vals)
    mix_max   = max(mix_vals)
    nut_min   = min(nutrient_vals)
    nut_max   = max(nutrient_vals)

    print(f"    혼합 깊이 범위:  {mix_min:.1f}m ~ {mix_max:.1f}m")
    print(f"    영양염 flux:     {nut_min:.4f} ~ {nut_max:.4f} g/m²/yr")
    print(f"    연간 CO₂ 격리:   {co2_sink_yr:.6f} ppm/yr")
    print(f"    식물플랑크톤:    {ocean.phyto:.3f} gC/m²")

    ok8 = check(
        mix_max > mix_min * 1.3,
        f"사리-조금 혼합 깊이 진동 (max/min={mix_max/max(mix_min,0.1):.2f}×)"
    )
    ok9 = check(
        co2_sink_yr > 0.0,
        f"연간 CO₂ 격리 > 0 ({co2_sink_yr:.6f} ppm/yr)"
    )
    all_pass = all_pass and ok8 and ok9

    # ──────────────────────────────────────────────────────────────
    print("\n" + "=" * 65)
    print(f"  결과: {'ALL PASS ✅' if all_pass else 'SOME FAIL ❌'}")
    print("=" * 65)

    print("\n  ── 넷째날 순환 3 파이프라인 ────────────────────────────────")
    print("  TidalField(달+태양) → mixing_depth → nutrient_flux")
    print("  → OceanNutrients → phyto_biomass → carbon_export")
    print("  → CO₂_sink_ppm → [atmosphere.CO2 감소 — GaiaLoopConnector]")
    print()
    print(f"  사리 혼합 깊이={s_spring.mixing_depth:.1f}m  "
          f"조금={s_neap.mixing_depth:.1f}m")
    print(f"  연간 CO₂ 격리={co2_sink_yr:.6f} ppm/yr  "
          f"식물플랑크톤={ocean.phyto:.3f} gC/m²")

    return all_pass


if __name__ == "__main__":
    success = run_gravity_tides_demo()
    sys.exit(0 if success else 1)
