"""gravity_tides_demo.py — 조석-해양 탄소 펌프 검증 v1.1 (넷째날 순환 3)

v1.1 변경: C_surface ODE 추가 + 단위 정합(μmol/L) + 닫힌 루프 연결

V1: 조석력 + 단위 정합 — upwelling_uM 출력 확인
V2: C_surface 동역학 — 영양염이 실제로 갱신되는지 (열린 루프 버그 수정 검증)
V3: 닫힌 루프 — TidalField.C_surface ↔ OceanNutrients.C_surface 공유
V4: 사리-조금 주기 + CO₂ 격리 연간 누적
"""

import sys
import os
import math

# 실행 위치 자동 감지: CookiieBrain 패키지 or GaiaFire_Engine 독립 실행 둘 다 지원
_HERE   = os.path.dirname(__file__)                  # gravity_tides/
_PARENT = os.path.dirname(_HERE)                     # solar/ or GaiaFire_Engine/
_ROOT   = os.path.dirname(_PARENT)                   # CookiieBrain/ or 상위
sys.path.insert(0, _ROOT)   # CookiieBrain 루트 (solar 패키지 접근)
sys.path.insert(0, _PARENT) # GaiaFire_Engine 루트 (gravity_tides 직접 접근)

try:
    from solar.gravity_tides import (
        TidalField, make_tidal_field,
        OceanNutrients, make_ocean_nutrients,
    )
except ImportError:
    from gravity_tides import (                      # GaiaFire_Engine 독립 실행
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
    print("  중력-조석 순환 v1.1 — 단위 정합 + 닫힌 루프 (넷째날 순환 3)")
    print("  달+태양 조석 → 혼합 → C_surface ODE → phyto → CO₂ sink")
    print("=" * 65)
    all_pass = True

    # ──────────────────────────────────────────────────────────────
    print("\n  [V1] 조석력 + upwelling 단위 정합 검증")

    tf = make_tidal_field(C_surface_init=5.0)

    T_synodic = 29.53 / 365.25
    t_spring = 0.0
    t_neap   = T_synodic / 4.0

    s_spring = tf.compute(t_spring)
    s_neap   = tf.compute(t_neap)

    print(f"    사리: {s_spring.summary()}")
    print(f"    조금: {s_neap.summary()}")
    print(f"    upwelling 단위: μmol N/L/yr (C_deep=30, C_surf=5 → grad=25)")

    ok1 = check(
        s_spring.upwelling_uM > s_neap.upwelling_uM,
        f"사리 upwelling > 조금 ({s_spring.upwelling_uM:.4f} > {s_neap.upwelling_uM:.4f} μmol/L/yr)"
    )
    ok2 = check(
        s_spring.mixing_depth > s_neap.mixing_depth,
        f"사리 혼합깊이 > 조금 ({s_spring.mixing_depth:.1f}m > {s_neap.mixing_depth:.1f}m)"
    )
    all_pass = all_pass and ok1 and ok2

    # ──────────────────────────────────────────────────────────────
    print("\n  [V2] C_surface ODE 검증 — 영양염이 실제로 갱신됨")

    ocean = make_ocean_nutrients(C_surface_init=5.0, phyto_init=1.0)
    C_init = ocean.C_surface

    # 높은 upwelling → C_surface 증가해야 함
    s_high = ocean.step(dt=1.0, upwelling_uM=5.0, light_factor=0.1)   # 빛 약해 phyto 낮음
    C_after_high = ocean.C_surface

    # 빛 강하고 upwelling 없음 → C_surface 감소해야 함
    ocean2 = make_ocean_nutrients(C_surface_init=10.0, phyto_init=5.0)
    s_low = ocean2.step(dt=1.0, upwelling_uM=0.0, light_factor=0.9)
    C_after_low = ocean2.C_surface

    print(f"    높은 upwelling(5.0), 빛=0.1:  C_surf {C_init:.2f} → {C_after_high:.2f} μmol/L")
    print(f"    upwelling=0, 빛=0.9:           C_surf 10.0 → {C_after_low:.2f} μmol/L")

    ok3 = check(
        C_after_high > C_init,
        f"높은 upwelling → C_surface 증가 ({C_after_high:.2f} > {C_init:.2f})"
    )
    ok4 = check(
        C_after_low < 10.0,
        f"upwelling=0 → phyto 소비로 C_surface 감소 ({C_after_low:.2f} < 10.0)"
    )
    all_pass = all_pass and ok3 and ok4

    # ──────────────────────────────────────────────────────────────
    print("\n  [V3] 닫힌 루프 — TidalField ↔ OceanNutrients C_surface 공유")

    tf_loop  = make_tidal_field(C_surface_init=5.0)
    ocean_lp = make_ocean_nutrients(C_surface_init=5.0, phyto_init=0.5)

    records = []
    for yr in range(20):
        ts = tf_loop.compute(t_yr=float(yr))
        os_ = ocean_lp.step(dt=1.0, upwelling_uM=ts.upwelling_uM, light_factor=0.7)
        # 루프 연결: 표층 영양염 공유
        tf_loop.C_surface = os_.C_surface
        if yr % 5 == 0:
            records.append((yr, os_.C_surface, os_.phyto_biomass,
                            os_.f_nutrient, os_.CO2_sink_ppm))

    print(f"\n    {'yr':>4}  {'C_surf':>8}  {'phyto':>8}  {'f_N':>6}  {'CO2_sink':>10}")
    print("    " + "-" * 46)
    for yr, cs, ph, fn, co2 in records:
        print(f"    {yr:>4}  {cs:>8.2f}  {ph:>8.3f}  {fn:>6.3f}  {co2:>10.6f}")

    # 20yr 후 phyto와 C_surface가 초기값과 달라야 함 (동역학이 작동)
    final_phyto = ocean_lp.phyto
    final_C     = ocean_lp.C_surface
    ok5 = check(
        final_phyto != 0.5,
        f"phyto가 초기값(0.5)에서 변화 → 동역학 작동 ({final_phyto:.3f})"
    )
    ok6 = check(
        final_C != 5.0,
        f"C_surface가 초기값(5.0)에서 변화 → ODE 갱신 확인 ({final_C:.3f})"
    )
    all_pass = all_pass and ok5 and ok6

    # ──────────────────────────────────────────────────────────────
    print("\n  [V4] 1yr 일단위 적분 — 사리-조금 주기 + CO₂ 연간 격리")

    tf_yr  = make_tidal_field(C_surface_init=5.0)
    oc_yr  = make_ocean_nutrients(C_surface_init=5.0, phyto_init=2.0)

    dt_day    = 1.0 / 365.25
    n_steps   = int(1.0 / dt_day)
    mix_vals  = []
    co2_total = 0.0

    for i in range(n_steps):
        t = i * dt_day
        ts  = tf_yr.compute(t)
        os_ = oc_yr.step(dt=dt_day, upwelling_uM=ts.upwelling_uM)
        tf_yr.C_surface = os_.C_surface   # 루프 연결
        mix_vals.append(ts.mixing_depth)
        co2_total += os_.CO2_sink_ppm * dt_day

    mix_min = min(mix_vals)
    mix_max = max(mix_vals)

    print(f"    혼합 깊이: {mix_min:.1f}m ~ {mix_max:.1f}m")
    print(f"    연간 CO₂ 격리: {co2_total:.6f} ppm/yr")
    print(f"    최종 C_surface: {oc_yr.C_surface:.3f} μmol/L")
    print(f"    최종 phyto:     {oc_yr.phyto:.3f} gC/m²")

    ok7 = check(
        mix_max > mix_min * 1.3,
        f"사리-조금 혼합 진동 (max/min={mix_max/max(mix_min,0.1):.2f}×)"
    )
    ok8 = check(
        co2_total > 0.0,
        f"연간 CO₂ 격리 > 0 ({co2_total:.6f} ppm/yr)"
    )
    all_pass = all_pass and ok7 and ok8

    # ──────────────────────────────────────────────────────────────
    print("\n" + "=" * 65)
    print(f"  결과: {'ALL PASS ✅' if all_pass else 'SOME FAIL ❌'}")
    print("=" * 65)

    print("\n  ── 넷째날 순환 3 파이프라인 (v1.1 닫힌 루프) ──────────────")
    print("  TidalField(달+태양) → mixing_depth")
    print("  → nutrient_upwelling_uM [μmol N/L/yr]")
    print("  → OceanNutrients.step(upwelling_uM)")
    print("     dC_surface/dt = upwelling - phyto_uptake - mix_loss  ← 닫힘 ✓")
    print("     dphyto/dt     = K_phyto × f_N(C_surf) × light - loss")
    print("  → CO2_sink_ppm → [atmosphere.CO2 감소]")
    print("  → tf.C_surface = oc.C_surface  ← 루프 연결 ✓")

    return all_pass


if __name__ == "__main__":
    success = run_gravity_tides_demo()
    sys.exit(0 if success else 1)
